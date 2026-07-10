"""Diccionario universal de roles de columnas (Fase 9).

Carga `api/app/data/palabras_clave_roles.csv` (≈15.600 claves normalizadas
únicas, 64 roles en 12 grupos, es-CL + inglés) y hace match del encabezado de
una columna contra el diccionario en cuatro etapas, de más a menos confiable:

1. **exacto**      — la clave normalizada del encabezado está en el diccionario.
2. **contencion**  — una clave del diccionario aparece como secuencia contigua
                     de tokens dentro del encabezado ("fecha de emision" dentro
                     de "Fecha de Emisión DTE"). Se compara por TOKENS para no
                     producir falsos positivos por substring ("id" jamás
                     matchea dentro de "salida").
3. **prefijo**     — el encabezado normalizado empieza o termina con una clave
                     larga (≥5 caracteres): "fechaventa2026" → "fechaventa".
4. **fuzzy**       — Levenshtein acotado (≤1 para claves cortas, ≤2 para
                     largas), misma inicial y largo similar: "Montto" → "monto".

Empates: gana la clave más larga; luego la de mayor `prioridad` del CSV.

El resultado incluye el rol extendido (64 roles), su grupo, el `tipo_dato`
esperado y `rol_motor` — el rol del motor actual de métricas (10 roles) cuando
la equivalencia es semánticamente segura. `mapping.detect_column_roles` usa
esto como primera pasada y conserva las palabras clave legacy como red de
compatibilidad (ver mapping.py).

Rendimiento: el CSV se carga UNA vez (lazy, con lock) y los matches por nombre
de columna se memoizan (lru_cache), así que el costo por request es ~0.
"""

import csv
import re
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "palabras_clave_roles.csv"

_METHOD_RANK = {"exacto": 4, "contencion": 3, "prefijo": 2, "fuzzy": 1}
_CONFIDENCE = {"exacto": 1.0, "contencion": 0.85, "prefijo": 0.75, "fuzzy": 0.6}

_MIN_PREFIX_KEY_LEN = 5
_MIN_FUZZY_COLUMN_LEN = 4


@dataclass(frozen=True)
class DictEntry:
    palabra: str
    rol: str
    grupo: str
    tipo_dato: str
    idioma: str
    prioridad: int
    rol_motor: str  # "" cuando el rol extendido no alimenta el motor actual


@dataclass(frozen=True)
class DictMatch:
    rol: str
    grupo: str
    tipo_dato: str
    rol_motor: str
    palabra_clave: str
    prioridad: int
    metodo: str      # exacto | contencion | prefijo | fuzzy | ia (clasificador)
    confianza: float

    def to_dict(self) -> dict:
        return {
            "rol": self.rol,
            "grupo": self.grupo,
            "tipo_dato": self.tipo_dato,
            "rol_motor": self.rol_motor or None,
            "palabra_clave": self.palabra_clave,
            "metodo": self.metodo,
            "confianza": self.confianza,
        }


def _tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", str(value).lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return [t for t in re.split(r"[^a-z0-9]+", normalized) if t]


# ── Índices (se construyen una sola vez) ─────────────────────────────────────

_LOCK = threading.Lock()
_LOADED = False
_EXACT: dict[str, DictEntry] = {}
_TOKENED: list[tuple[str, int, DictEntry]] = []      # (" fecha de emision ", len_norm, entry)
_LONG_KEYS: list[tuple[str, DictEntry]] = []         # claves ≥ 5 chars para prefijo/sufijo
_BY_FIRST: dict[str, list[tuple[str, DictEntry]]] = {}  # inicial → [(norm, entry)] para fuzzy
_ROLE_GROUP: dict[str, str] = {}                     # rol → grupo (para prompt_library)


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:
            return
        if not _CSV_PATH.exists():
            # Sin diccionario, mapping.py cae a las palabras clave legacy.
            print(f"[dictionary] No se encontró {_CSV_PATH}; se usará solo el mapeo legacy.")
            _LOADED = True
            return
        with open(_CSV_PATH, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                toks = _tokens(row["palabra_clave"])
                norm = "".join(toks)
                if not norm:
                    continue
                entry = DictEntry(
                    palabra=row["palabra_clave"],
                    rol=row["rol"],
                    grupo=row["grupo"],
                    tipo_dato=row["tipo_dato"],
                    idioma=row["idioma"],
                    prioridad=int(row["prioridad"] or 0),
                    rol_motor=(row.get("rol_motor_actual") or "").strip(),
                )
                previous = _EXACT.get(norm)
                if previous is None or entry.prioridad > previous.prioridad:
                    _EXACT[norm] = entry
                _TOKENED.append((" " + " ".join(toks) + " ", len(norm), entry))
                if len(norm) >= _MIN_PREFIX_KEY_LEN:
                    _LONG_KEYS.append((norm, entry))
                _BY_FIRST.setdefault(norm[0], []).append((norm, entry))
                _ROLE_GROUP.setdefault(entry.rol, entry.grupo)
        _LOADED = True


def dictionary_size() -> int:
    _load()
    return len(_EXACT)


def role_group(rol: str) -> str | None:
    _load()
    return _ROLE_GROUP.get(rol)


def _bounded_levenshtein(a: str, b: str, max_distance: int) -> int | None:
    """Distancia de Levenshtein si ≤ max_distance; None si la excede."""
    if abs(len(a) - len(b)) > max_distance:
        return None
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return None
        previous = current
    return previous[-1] if previous[-1] <= max_distance else None


def _best(candidates: list[tuple[tuple, DictEntry]]) -> DictEntry | None:
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


@lru_cache(maxsize=4096)
def match_column(column_name: str) -> DictMatch | None:
    """Match del encabezado contra el diccionario. None si nada es confiable."""
    _load()
    if not _EXACT:
        return None
    toks = _tokens(column_name)
    norm = "".join(toks)
    if len(norm) < 2:
        return None

    # 1) Exacto
    entry = _EXACT.get(norm)
    if entry:
        return _to_match(entry, "exacto")

    # 2) Contención por tokens (secuencia contigua)
    padded = " " + " ".join(toks) + " "
    contained = [
        ((length, e.prioridad), e)
        for token_str, length, e in _TOKENED
        if length < len(norm) and token_str in padded
    ]
    entry = _best(contained)
    if entry:
        return _to_match(entry, "contencion")

    # 3) Prefijo / sufijo sobre la clave normalizada (claves largas)
    affixed = [
        ((len(key), e.prioridad), e)
        for key, e in _LONG_KEYS
        if len(key) < len(norm) and (norm.startswith(key) or norm.endswith(key))
    ]
    entry = _best(affixed)
    if entry:
        return _to_match(entry, "prefijo")

    # 4) Fuzzy (typos): misma inicial, largo similar, distancia acotada
    if len(norm) >= _MIN_FUZZY_COLUMN_LEN:
        max_distance = 1 if len(norm) <= 6 else 2
        fuzzy: list[tuple[tuple, DictEntry]] = []
        for key, e in _BY_FIRST.get(norm[0], []):
            if abs(len(key) - len(norm)) > max_distance:
                continue
            distance = _bounded_levenshtein(norm, key, max_distance)
            if distance is not None and distance > 0:
                fuzzy.append(((-distance, len(key), e.prioridad), e))
        entry = _best(fuzzy)
        if entry:
            return _to_match(entry, "fuzzy")
    return None


def _to_match(entry: DictEntry, metodo: str) -> DictMatch:
    return DictMatch(
        rol=entry.rol,
        grupo=entry.grupo,
        tipo_dato=entry.tipo_dato,
        rol_motor=entry.rol_motor,
        palabra_clave=entry.palabra,
        prioridad=entry.prioridad,
        metodo=metodo,
        confianza=_CONFIDENCE[metodo],
    )


def match_columns(columns: list[str]) -> dict[str, DictMatch]:
    """Match de todos los encabezados. Solo incluye columnas reconocidas."""
    result: dict[str, DictMatch] = {}
    for col in columns:
        match = match_column(str(col))
        if match:
            result[col] = match
    return result
