"""Estandarización del dataset (SPEC §6, POST /standardize) — motor Fase 7.

Unifica nombres y textos duplicados, estandariza fechas (DD/MM/YYYY) y números
(formato chileno: $ y punto de miles → número plano), y normaliza
mayúsculas/minúsculas/tildes. Opera sobre DataFrames de solo texto.

Mejoras profesionales Fase 7 (§5):
- Detección de tipo con **muestra aleatoria determinista** (no las primeras
  200 filas: un archivo ordenado ya no misclasifica) y **confianza por columna**.
- Números ambiguos ("850.000" ¿miles o decimal?) se deciden por **consistencia
  de toda la columna**, no celda a celda.
- Fechas: **formato dominante por columna** (dayfirst detectado, no fijo) y
  soporte de **meses en texto** ("01 mayo 2026", "1 de mayo de 2026").
- **Fuzzy matching** de typos ("Santigo" → "Santiago") con distancia de
  Levenshtein acotada, además de la unificación por frecuencia.
"""

import math
import random
import re
import warnings

import pandas as pd

from .mapping import norm_key, resolve_mapping, strip_accents_lower

# Valores que se consideran "sin dato" además del string vacío.
MISSING_TOKENS = {"", "-", "--", "n/a", "na", "null", "none", "s/i", "sin dato"}

# Placeholders dependientes del significado de la columna. Se conservan en el
# DataFrame para distinguirlos de una celda físicamente vacía.
PLACEHOLDERS_BY_ROLE = {
    "cliente": {
        "sin nombre", "cliente desconocido", "sin identificar", "no informa",
    },
}

DATE_HINTS = ("fecha", "date", "periodo", "emision", "vencimiento")
_DATE_SHAPE = re.compile(r"^\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\s*$")
_NUMBER_SHAPE = re.compile(r"^\s*-?\s*\$?\s*-?[\d.,]+\s*$")

# Fase 8 §5.14: símbolos/códigos de moneda y decoraciones frecuentes en
# planillas reales de Chile/LatAm: "$ 1.200.000", "CLP 850.000", "US$1.500",
# "1.200 USD", "€200", "12%", y negativos contables "(1.500)".
_CURRENCY_TOKEN_RE = re.compile(r"(?i)(us\$|s/\.?|clp|usd|eur|ars|pen|cop|mxn|uf|[$€£])")
_BARE_NUMBER_RE = re.compile(r"^-?[\d.,]+$")


def _strip_number_decorations(value: str) -> tuple[str, bool]:
    """Quita moneda/%/espacios y detecta negativo contable entre paréntesis.
    Devuelve (texto_limpio, es_negativo_por_parentesis)."""
    text = str(value).strip().replace("\xa0", " ")
    negative = False
    if len(text) > 2 and text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = _CURRENCY_TOKEN_RE.sub("", text)
    return text.replace("%", "").replace(" ", "").strip(), negative


def _looks_like_number(value: str) -> bool:
    text, _ = _strip_number_decorations(value)
    return bool(text and _BARE_NUMBER_RE.match(text))

# Fechas con mes en texto: "01 mayo 2026", "1 de mayo de 2026", "3-ene-26".
_DATE_TEXT_SHAPE = re.compile(
    r"^\s*(\d{1,2})[\s\-/]*(?:de\s+)?([a-z]{3,12})\.?[\s\-/]*(?:de(?:l)?\s+)?(\d{2,4})\s*$"
)
_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

_TYPE_SAMPLE_SIZE = 300
_TYPE_SAMPLE_SEED = 20260706  # determinista: mismos datos → misma clasificación


def is_missing(value: str) -> bool:
    return str(value).strip().lower() in MISSING_TOKENS


def missing_mask(series: pd.Series) -> pd.Series:
    """Máscara vectorizada de valores 'sin dato' (mucho más rápida que .map)."""
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.isin(MISSING_TOKENS)


def physical_missing_mask(series: pd.Series) -> pd.Series:
    """Celdas realmente vacías; no incluye placeholders ni tokens como N/A."""
    return series.astype(str).str.strip().eq("")


def is_semantic_placeholder(value: str, role: str | None) -> bool:
    placeholders = PLACEHOLDERS_BY_ROLE.get(role or "", set())
    normalized = " ".join(strip_accents_lower(value).split())
    return normalized in placeholders


def semantic_missing_mask(series: pd.Series, role: str | None) -> pd.Series:
    """Placeholders válidos solo para un rol, sin modificar su valor original."""
    placeholders = PLACEHOLDERS_BY_ROLE.get(role or "", set())
    if not placeholders:
        return pd.Series(False, index=series.index)
    return map_unique(
        series.astype(str), lambda value: is_semantic_placeholder(value, role)
    ).astype(bool)


def map_unique(series: pd.Series, func) -> pd.Series:
    """`series.map(func)` calculando func UNA vez por valor único (Fase 11).

    En datos reales las columnas repiten muchísimo (fechas, categorías,
    estados, montos típicos): 50.000 filas suelen tener menos de 2.000
    valores únicos — parsear cada celda era el mayor costo del motor."""
    uniques = series.unique()
    if len(uniques) >= len(series) * 0.9:
        return series.map(func)  # casi todo único: el índice no ayuda
    return series.map({value: func(value) for value in uniques})


def normalize_headers(df: pd.DataFrame) -> int:
    """Limpia encabezados in-place. Devuelve cuántos cambiaron."""
    changes = 0
    seen: dict[str, int] = {}
    new_columns: list[str] = []
    for index, col in enumerate(df.columns):
        name = re.sub(r"\s+", " ", str(col)).strip()
        if not name or name.lower().startswith("unnamed"):
            name = f"columna_{index + 1}"
        if name != str(col):
            changes += 1
        key = strip_accents_lower(name)
        count = seen.get(key, 0)
        seen[key] = count + 1
        if count:
            name = f"{name}_{count + 1}"
            changes += 1
        new_columns.append(name)
    df.columns = new_columns
    return changes


def _sample_values(series: pd.Series) -> list[str]:
    """Muestra aleatoria determinista de valores con dato (§5.4)."""
    values = [str(v) for v in series if not is_missing(v)]
    if len(values) <= _TYPE_SAMPLE_SIZE:
        return values
    rng = random.Random(_TYPE_SAMPLE_SEED)
    return rng.sample(values, _TYPE_SAMPLE_SIZE)


def _looks_like_date(value: str) -> bool:
    if _DATE_SHAPE.match(value) or _DATE_TEXT_SHAPE.match(strip_accents_lower(value)):
        return True
    # Fase 13: "2026-05-01 00:00:00" (datetime de Excel) también ES una fecha —
    # antes estas columnas quedaban clasificadas como texto y jamás se
    # estandarizaban, aunque las métricas sí las parseaban por rol.
    head = str(value).strip().split(" ")[0]
    return bool(head != str(value).strip() and _DATE_SHAPE.match(head))


def detect_value_type_confidence(series: pd.Series, column_name: str) -> tuple[str, float]:
    """Clasifica una columna como 'fecha', 'numero' o 'texto' + confianza 0–1."""
    values = _sample_values(series)
    if not values:
        return "texto", 0.0
    date_like = sum(_looks_like_date(v) for v in values)
    number_like = sum(_looks_like_number(v) for v in values)
    name = strip_accents_lower(column_name)
    date_ratio = date_like / len(values)
    number_ratio = number_like / len(values)
    # Fase 12b: el nombre "fecha" ya no basta con UNA celda con forma de fecha
    # — una columna de texto con encabezado engañoso quedaba clasificada
    # completa como fecha. Con pista de nombre se exige al menos 30% real.
    if date_ratio >= 0.6 or (any(h in name for h in DATE_HINTS) and date_ratio >= 0.3):
        return "fecha", round(max(date_ratio, 0.6 if date_like else 0.0), 2)
    if number_ratio >= 0.6:
        return "numero", round(number_ratio, 2)
    return "texto", round(1 - max(date_ratio, number_ratio), 2)


def detect_value_type(series: pd.Series, column_name: str) -> str:
    """Compatibilidad: solo el tipo (la confianza vive en el reporte)."""
    return detect_value_type_confidence(series, column_name)[0]


# ── Fechas ────────────────────────────────────────────────────────────────────


def _value_dayfirst_evidence(text: str) -> bool | None:
    """Evidencia de orientación de UN valor: True=día/mes, False=mes/día,
    None=ambiguo o ISO (Fase 11 §7)."""
    parts = re.split(r"[-/.]", text)
    if len(parts) != 3:
        return None
    try:
        first, second = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if first > 31:  # ISO yyyy-mm-dd: el orden lo resuelve pandas
        return None
    if 12 < first <= 31:
        return True
    if 12 < second <= 31:
        return False
    return None

def column_date_profile(series: pd.Series) -> dict:
    """Perfil de formato de fecha de la columna (Fase 11 §7).

    {dayfirst, dmy, mdy, ambiguas, mixta}: si conviven evidencias DD/MM y
    MM/DD la columna es MIXTA — cada valor inequívoco se interpreta por su
    propia evidencia y las ambiguas usan la convención dominante, con aviso."""
    dmy = mdy = ambiguous = 0
    for value in _sample_values(series):
        text = str(value).strip().split(" ")[0]
        if not _DATE_SHAPE.match(text):
            continue
        evidence = _value_dayfirst_evidence(text)
        if evidence is True:
            dmy += 1
        elif evidence is False:
            mdy += 1
        else:
            parts = re.split(r"[-/.]", text)
            # Ambigua: tres partes numéricas y la primera NO es un año ISO.
            if len(parts) == 3 and parts[0].isdigit() and len(parts[0]) <= 2:
                ambiguous += 1
    if dmy and not mdy:
        dayfirst = True
    elif mdy and not dmy:
        dayfirst = False
    else:
        dayfirst = dmy >= mdy  # empate/sin evidencia → convención chilena
    return {
        "dayfirst": dayfirst,
        "dmy": dmy,
        "mdy": mdy,
        "ambiguas": ambiguous,
        "mixta": bool(dmy and mdy),
    }


def column_dayfirst(series: pd.Series) -> bool:
    """Compatibilidad: solo la orientación dominante (§5.6)."""
    return column_date_profile(series)["dayfirst"]


def _parse_text_month_date(text: str) -> pd.Timestamp | None:
    match = _DATE_TEXT_SHAPE.match(strip_accents_lower(text))
    if not match:
        return None
    day_raw, month_raw, year_raw = match.groups()
    month = _MONTHS_ES.get(month_raw)
    if month is None:
        return None
    year = int(year_raw)
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return pd.Timestamp(year=year, month=month, day=int(day_raw))
    except ValueError:
        return None


def parse_date(value: str, dayfirst: bool = True) -> pd.Timestamp | None:
    text = str(value).strip()
    if is_missing(text):
        return None
    text_month = _parse_text_month_date(text)
    if text_month is not None:
        return text_month
    if not _DATE_SHAPE.match(text):
        # También aceptar fechas ya ISO con hora ("2026-05-01 00:00:00")
        text = text.split(" ")[0]
        if is_missing(text) or not _DATE_SHAPE.match(text):
            return None
    # Fase 11 §7: la evidencia del PROPIO valor manda sobre la convención de
    # la columna — en una columna DD/MM, "05/22/2026" es inequívocamente
    # MM/DD y ya no se descarta ni se interpreta al revés.
    evidence = _value_dayfirst_evidence(text)
    effective_dayfirst = dayfirst if evidence is None else evidence
    # Fase 13: una fecha AÑO-primero ("2026-05-01", ISO) es SIEMPRE
    # año-mes-día — pandas con dayfirst=True la volteaba a año-DÍA-mes y
    # el 1 de mayo se convertía en 5 de enero.
    if re.match(r"^\d{4}[-/.]", text):
        effective_dayfirst = False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(text, dayfirst=effective_dayfirst, errors="coerce")
    return None if pd.isna(parsed) else parsed


# ── Números ───────────────────────────────────────────────────────────────────


def column_dot3_convention(series: pd.Series) -> str:
    """Convención de la columna para el caso ambiguo "###.###" (§5.5).

    Devuelve 'miles' (es-CL: 850.000 = ochocientos cincuenta mil) o 'decimal'
    (850.000 = 850 con tres decimales). Se decide por consistencia:
    - Si la columna usa coma decimal o puntos múltiples → el punto es de miles.
    - Si la columna tiene valores con 1–2 decimales tras un único punto y
      ningún indicio de miles → el punto es decimal en toda la columna.
    - Sin evidencia → 'miles' (convención chilena)."""
    decimal_votes = miles_votes = 0
    for value in _sample_values(series):
        text, _ = _strip_number_decorations(value)
        text = text.lstrip("-")
        if not re.match(r"^[\d.,]+$", text):
            continue
        if "," in text or text.count(".") > 1:
            miles_votes += 1
            continue
        if "." in text:
            right = text.split(".")[1]
            if len(right) in (1, 2):
                decimal_votes += 1
    if decimal_votes and not miles_votes:
        return "decimal"
    return "miles"


def column_comma3_convention(series: pd.Series) -> tuple[str, int]:
    """Convención para el caso ambiguo "#,###" (Fase 12b §P0.4).

    "1,234" puede ser 1.234 (decimal es-CL) o mil doscientos treinta y cuatro
    (miles US). Se decide por evidencia de la MISMA columna:
    - valores con coma y 1–2 decimales ("12,5") o formato "1.234,56" → decimal;
    - valores con comas múltiples ("1,234,567") o formato "1,234.56" → miles.
    Devuelve (convención, cantidad_de_valores_ambiguos). Sin evidencia se
    mantiene 'decimal' (convención es-CL) y el llamador AVISA la ambigüedad."""
    decimal_votes = miles_votes = ambiguous = 0
    for value in _sample_values(series):
        text, _ = _strip_number_decorations(value)
        text = text.lstrip("-")
        if not re.match(r"^[\d.,]+$", text) or "," not in text:
            continue
        if "." in text:
            if text.rfind(",") > text.rfind("."):
                decimal_votes += 1  # 1.234,56
            else:
                miles_votes += 1  # 1,234.56
            continue
        if text.count(",") > 1:
            miles_votes += 1  # 1,234,567
            continue
        right = text.split(",")[1]
        if len(right) in (1, 2):
            decimal_votes += 1  # 12,5
        elif len(right) == 3:
            ambiguous += 1  # 1,234 — el caso en disputa
    if miles_votes and not decimal_votes:
        return "miles", ambiguous
    return "decimal", ambiguous


def parse_number(
    value: str, dot3_convention: str = "miles", comma3_convention: str = "decimal"
) -> float | None:
    text, paren_negative = _strip_number_decorations(value)
    if not text or not _BARE_NUMBER_RE.match(text):
        return None
    negative = paren_negative or text.startswith("-")
    text = text.lstrip("-")
    if "," in text and "." in text:
        # Fase 11 §10.2: con AMBOS separadores, el que aparece AL FINAL es el
        # decimal — regla universal que cubre el formato chileno/europeo
        # ("1.234.567,89") y el estadounidense ("1,234.56") sin adivinar.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if text.count(",") > 1:
            # Solo comas múltiples: separador de miles US (1,234,567).
            text = text.replace(",", "")
        else:
            left, right = text.split(",")
            # "1,234": ambiguo — decide la convención de la COLUMNA (Fase 12b);
            # sin evidencia se mantiene decimal (es-CL) y la columna avisa.
            if len(right) == 3 and len(left) >= 1 and comma3_convention == "miles":
                text = left + right
            else:
                # Coma como separador decimal (es-CL)
                text = text.replace(",", ".")
    elif text.count(".") > 1:
        # Solo puntos de miles: 1.234.567
        text = text.replace(".", "")
    elif "." in text:
        left, right = text.split(".")
        # "850.000": ambiguo → decide la convención de la columna (§5.5)
        if len(right) == 3 and len(left) >= 1 and dot3_convention == "miles":
            text = left + right
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def format_number(number: float) -> str:
    # Fase 14: repr() es el texto MÁS CORTO que reconstruye exactamente el
    # mismo float64 — no trunca nada que el motor conozca (el ".9f" de la Fase
    # 13 aún cortaba colas legítimas). La promesa es "no truncar más allá de
    # la precisión disponible en float64", no preservar el texto original.
    # Solo aplica a valores que vienen DIRECTO del parseo (aquí el float nació
    # de un texto corto y repr lo devuelve tal cual); los agregados calculados
    # de metrics.py mantienen sus round() — la aritmética binaria produce
    # artefactos (0.30000000000000004) que repr mostraría tal cual.
    if not math.isfinite(number):
        return str(number)
    if number == int(number):
        return str(int(number))
    return repr(number)


# ── Textos: unificación por frecuencia + fuzzy matching ──────────────────────


def _levenshtein_leq(a: str, b: str, max_distance: int) -> bool:
    """¿distancia de Levenshtein(a, b) ≤ max_distance? DP con corte temprano."""
    if abs(len(a) - len(b)) > max_distance:
        return False
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
            return False
        previous = current
    return previous[-1] <= max_distance


_FUZZY_MAX_UNIQUE_KEYS = 400
_FUZZY_MIN_KEY_LEN = 4

_MOJIBAKE_MARKERS = ("Ã", "Â", "�", "â€", "ð")
_UNEXPECTED_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_MOJIBAKE_SEGMENT_RE = re.compile(r"(?:Ã.|Â.|â..|ð...)")


def _mojibake_score(value: str) -> int:
    text = str(value)
    return sum(text.count(marker) for marker in _MOJIBAKE_MARKERS) + len(
        _UNEXPECTED_CONTROL_RE.findall(text)
    )


def _repair_mojibake(value: str) -> tuple[str, dict | None]:
    """Propone una reparación solo cuando una conversión strict es inequívoca.

    Nunca descarta bytes ni caracteres. Si latin-1 y cp1252 producen propuestas
    distintas con la misma evidencia, se conserva el original y se audita como
    ambiguo.
    """
    original = str(value)
    original_score = _mojibake_score(original)
    if original_score == 0:
        return original, None

    proposals: dict[str, list[str]] = {}
    for encoding in ("latin-1", "cp1252"):
        candidates: list[str] = []
        try:
            candidates.append(original.encode(encoding, errors="strict").decode(
                "utf-8", errors="strict"
            ))
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        # Una cadena puede mezclar un segmento dañado con Unicode legítimo
        # ("Lâ€™Oréal"). Se repara solo cada secuencia sospechosa, siempre strict.
        repaired_segment = False

        def _replace_segment(match: re.Match) -> str:
            nonlocal repaired_segment
            segment = match.group(0)
            try:
                proposed_segment = segment.encode(encoding, errors="strict").decode(
                    "utf-8", errors="strict"
                )
            except (UnicodeEncodeError, UnicodeDecodeError):
                return segment
            if _mojibake_score(proposed_segment) < _mojibake_score(segment):
                repaired_segment = True
                return proposed_segment
            return segment

        segmented = _MOJIBAKE_SEGMENT_RE.sub(_replace_segment, original)
        if repaired_segment:
            candidates.append(segmented)

        for proposed in candidates:
            if proposed != original and _mojibake_score(proposed) < original_score:
                proposals.setdefault(proposed, []).append(encoding)

    if not proposals:
        return original, {
            "valor_original": original,
            "valor_propuesto": None,
            "metodo": None,
            "confianza": 0.0,
            "aplicado": False,
            "motivo": "No existe una reparación strict inequívoca.",
        }

    best_score = min(_mojibake_score(proposed) for proposed in proposals)
    best = [proposed for proposed in proposals if _mojibake_score(proposed) == best_score]
    if len(best) != 1:
        return original, {
            "valor_original": original,
            "valor_propuesto": None,
            "metodo": "ambiguo",
            "confianza": 0.0,
            "aplicado": False,
            "motivo": "latin-1 y cp1252 producen propuestas distintas equivalentes.",
        }

    proposed = best[0]
    methods = proposals[proposed]
    return proposed, {
        "valor_original": original,
        "valor_propuesto": proposed,
        "metodo": methods[0] if len(methods) == 1 else "+".join(methods),
        "confianza": 0.98 if best_score == 0 else 0.8,
        "aplicado": True,
        "motivo": "La propuesta reduce las secuencias sospechosas sin descartar caracteres.",
    }

# Fase 10 §6.1: la fusión fuzzy JAMÁS se aplica a identificadores — un typo de
# distancia 1 puede ser un SKU/folio/RUT legítimamente distinto ("SKU-1001" vs
# "SKU-100I"). La normalización segura (espacios/mayúsculas/tildes) sí aplica.
_ID_COLUMN_TOKENS = {
    "id", "folio", "boleta", "factura", "documento", "doc", "sku", "numero",
    "num", "nro", "correlativo", "ticket", "orden", "codigo", "cod", "rut",
    "telefono", "fono", "celular", "email", "correo", "mail", "patente",
    "serie", "guia", "dte", "cuenta", "tarjeta",
}


def is_identifier_column(name: str, series: pd.Series | None = None) -> bool:
    """¿La columna parece un identificador (por nombre o por contenido)?

    Contenido: si >30% de la muestra trae dígitos o '@', son códigos/contactos
    — las categorías, ciudades y canales casi nunca contienen dígitos."""
    tokens = set(re.sub(r"[^a-z0-9]+", " ", strip_accents_lower(name)).split())
    if tokens & _ID_COLUMN_TOKENS:
        return True
    if series is not None:
        sample = _sample_values(series)[:200]
        if sample:
            with_digits = sum(1 for v in sample if any(c.isdigit() for c in v))
            with_at = sum(1 for v in sample if "@" in v)
            if with_at / len(sample) > 0.3 or with_digits / len(sample) > 0.3:
                return True
    return False


# Bug: "Santiago Centro"/"Stgo Centro" o "Concepción"/"conce" no se
# unificaban — el fuzzy por distancia de edición solo cubre typos (1-2
# caracteres), no abreviaciones ("stgo" vs "santiago" difieren en 5). Estas
# son abreviaciones chilenas de uso común y no ambiguas: se expanden ANTES de
# comparar, con confianza alta (fusión directa, no solo sugerencia).
_CL_PLACE_ABBREVIATIONS: dict[str, str] = {
    "stgo": "santiago",
    "valpo": "valparaiso",
    "conce": "concepcion",
    "concep": "concepcion",
    "provi": "providencia",
    "pto": "puerto",
    "pta": "punta",
    "antofa": "antofagasta",
}


def _expand_abbreviations_key(value: str) -> str:
    """norm_key, pero expandiendo antes cada palabra conocida del diccionario
    de abreviaciones chilenas ("Stgo Centro" → "santiago centro" → misma
    clave que "Santiago Centro")."""
    words = strip_accents_lower(value).split()
    expanded = " ".join(_CL_PLACE_ABBREVIATIONS.get(w, w) for w in words)
    return norm_key(expanded)


def _fuzzy_merge_keys(frequencies: dict[str, dict[str, int]]) -> dict[str, str]:
    """Fusiona claves raras con typos hacia claves frecuentes cercanas (§5.11).

    Guardas para no fusionar valores legítimamente distintos:
    - Solo columnas con ≤ 400 claves únicas y claves de ≥ 4 caracteres con letras.
    - La variante debe ser rara RELATIVA a la canónica (≤ 1/2 de su total) y la
      canónica frecuente (≥ 3) — una variante también "frecuente" en términos
      absolutos (ej. "pagada" con 12 apariciones) igual puede ser un typo de
      una canónica mucho más frecuente (ej. "pagado" con 38) (Bug #4: antes
      cualquier clave con total ≥ 3 quedaba excluida de por vida del lado
      "raro", sin llegar siquiera a evaluar la cercanía con la canónica).
    - Distancia ≤ 1 para claves cortas (≤ 6), ≤ 2 para más largas.
    - Misma letra inicial (evita fusionar "gasto"/"pasto")."""
    if not (2 <= len(frequencies) <= _FUZZY_MAX_UNIQUE_KEYS):
        return {}
    totals = {key: sum(variants.values()) for key, variants in frequencies.items()}
    frequent = [k for k, t in totals.items() if t >= 3]
    merges: dict[str, str] = {}
    for key, total in totals.items():
        if len(key) < _FUZZY_MIN_KEY_LEN or not any(c.isalpha() for c in key):
            continue
        max_distance = 1 if len(key) <= 6 else 2
        for canon in frequent:
            if canon == key or canon[0] != key[0] or len(canon) < _FUZZY_MIN_KEY_LEN:
                continue
            if total > max(2, totals[canon] // 2):
                continue
            if _levenshtein_leq(key, canon, max_distance):
                merges[key] = canon
                break
    return merges


def _normalize_text_column(
    series: pd.Series, allow_fuzzy: bool = True, role: str | None = None
) -> tuple[pd.Series, dict[str, int], list[list[str]], list[dict], list[tuple[str, str, int]]]:
    """Recorta espacios, limpia placeholders y unifica variantes de un mismo texto.

    Devuelve (serie, desglose, ejemplos_de_fusiones_fuzzy, auditoría_mojibake,
    sugerencias_de_fusión). Las variantes que solo difieren en mayúsculas/
    tildes/espacios se reemplazan por la forma más frecuente; los typos
    cercanos se fusionan con Levenshtein acotado — SOLO si `allow_fuzzy`
    (jamás en columnas identificadoras, Fase 10 §6.1). Las sugerencias son
    truncamientos genéricos (ej. "conce" de "Concepción") que NO se fusionan
    solos por no ser una abreviación conocida — se avisan para que el
    usuario confirme, en vez de fusionar a ciegas o dejarlas pasar calladas."""
    original = series.map(str)
    semantic_mask = semantic_missing_mask(original, role)

    value_counts = original.value_counts(dropna=False)
    repaired_values: dict[str, str] = {}
    mojibake_audit: list[dict] = []
    mojibake_detected = mojibake_repaired = 0
    for value, count in value_counts.items():
        text = str(value)
        if is_semantic_placeholder(text, role):
            repaired_values[text] = text
            continue
        repaired, audit = _repair_mojibake(text)
        repaired_values[text] = repaired
        if audit:
            occurrences = int(count)
            mojibake_detected += occurrences
            if audit["aplicado"]:
                mojibake_repaired += occurrences
            if len(mojibake_audit) < 100:
                mojibake_audit.append({**audit, "ocurrencias": occurrences})

    repaired = original.map(repaired_values)
    stripped = map_unique(
        repaired,
        lambda v: "" if is_missing(v) else re.sub(r"\s+", " ", str(v)).strip(),
    )
    # Un placeholder semántico conserva exactamente el texto entregado.
    stripped = stripped.where(~semantic_mask, original)
    spacing_changes = int((stripped != original).sum())

    frequencies: dict[str, dict[str, int]] = {}
    # La frecuencia contiene la misma informacion que recorrer cada fila,
    # pero permite normalizar cada variante una sola vez.
    for value, count in stripped.value_counts(dropna=False).items():
        if not value or is_semantic_placeholder(value, role):
            continue
        # norm_key agrupa variantes que solo difieren en mayúsculas, tildes
        # o puntuación de formato (ej: "76.123.456-7" y "76123456-7").
        key = norm_key(value)
        bucket = frequencies.setdefault(key, {})
        bucket[value] = int(count)

    def _pick_canonical(variants: dict[str, int]) -> str:
        # Más frecuente; ante empate, prefiere la forma con mayúscula inicial.
        return max(variants.items(), key=lambda kv: (kv[1], kv[0][:1].isupper(), kv[0]))[0]

    canonical = {key: _pick_canonical(variants) for key, variants in frequencies.items()}

    # Fuzzy: claves raras que son typos de una clave frecuente (§5.11).
    fuzzy_examples: list[list[str]] = []
    fuzzy_merges = 0  # Fase 13: conteo REAL (los ejemplos van capados a 5)
    suggestions: list[tuple[str, str, int]] = []
    if allow_fuzzy:
        for rare_key, canon_key in _fuzzy_merge_keys(frequencies).items():
            if len(fuzzy_examples) < 5:
                fuzzy_examples.append([canonical[rare_key], canonical[canon_key]])
            canonical[rare_key] = canonical[canon_key]
            fuzzy_merges += 1

        totals = {key: sum(v.values()) for key, v in frequencies.items()}
        ordered = sorted(totals, key=lambda k: totals[k], reverse=True)

        # Fase 11 §8: variantes MORFOLÓGICAS en categóricas de baja
        # cardinalidad — "pagada" (5) → "pagado" (55). El fuzzy clásico no las
        # toca porque ambas son "frecuentes" (≥3). Guardas: ≤30 categorías,
        # misma raíz, solo vocal final a/o o plural con "s", y la minoritaria
        # es ≤ 1/4 de la dominante (categorías equilibradas jamás se fusionan).
        if 2 <= len(totals) <= 30:
            for minor in list(ordered):
                if canonical[minor] != _pick_canonical(frequencies[minor]):
                    continue  # ya fusionada por el fuzzy
                for major in ordered:
                    if major == minor or totals[major] < max(totals[minor] * 4, 3):
                        continue
                    if len(minor) < 4 or minor[:3] != major[:3]:
                        continue
                    vowel_swap = (
                        len(minor) == len(major)
                        and minor[:-1] == major[:-1]
                        and {minor[-1], major[-1]} <= {"a", "o"}
                        and not minor[-2] in "aeiou "
                    )
                    plural = minor == major + "s" or major == minor + "s"
                    if vowel_swap or plural:
                        if len(fuzzy_examples) < 5:
                            fuzzy_examples.append([canonical[minor], canonical[major]])
                        canonical[minor] = canonical[major]
                        fuzzy_merges += 1
                        break

        # Abreviaciones chilenas conocidas (Bug): "Stgo Centro" no se
        # fusionaba con "Santiago Centro" porque la distancia de edición
        # entre "stgocentro" y "santiagocentro" es demasiado grande para el
        # fuzzy clásico. Confianza alta — es un diccionario curado, no una
        # adivinanza — así que se fusiona directo, sin tope de cardinalidad.
        for minor in list(ordered):
            if canonical[minor] != _pick_canonical(frequencies[minor]):
                continue  # ya fusionada por una pasada anterior
            sample_value = next(iter(frequencies[minor]))
            expanded_key = _expand_abbreviations_key(sample_value)
            if expanded_key == minor or expanded_key not in frequencies:
                continue
            major = expanded_key
            if totals[minor] > totals[major]:
                continue  # la forma abreviada no puede ser más frecuente que la completa
            if len(fuzzy_examples) < 5:
                fuzzy_examples.append([canonical[minor], canonical[major]])
            canonical[minor] = canonical[major]
            fuzzy_merges += 1

        # Truncamientos genéricos (Bug): "conce" de "Concepción" no está en
        # ningún diccionario y podría ser una categoría real distinta (mismo
        # espíritu que "Ruta" vs "Ruta terreno") — confianza media, así que
        # NO se fusiona sola: se suma como sugerencia para que el usuario la
        # confirme, en vez de fusionar a ciegas o dejarla pasar callada.
        for minor in list(ordered):
            if canonical[minor] != _pick_canonical(frequencies[minor]):
                continue  # ya fusionada por una pasada anterior
            if len(minor) < 4:
                continue
            for major in ordered:
                if major == minor or len(major) <= len(minor):
                    continue
                if totals[minor] > max(2, totals[major] // 2):
                    continue
                if major.startswith(minor):
                    suggestions.append((canonical[minor], canonical[major], totals[minor]))
                    break

    unified = map_unique(
        stripped,
        lambda v: (
            v
            if not v or is_semantic_placeholder(v, role)
            else canonical[norm_key(v)]
        ),
    )
    unified = unified.where(~semantic_mask, original)
    variant_changes = int((unified != stripped).sum())
    # Una celda puede pasar por ambas etapas. El contador visible compara
    # únicamente el resultado final con el original para no contarla dos veces.
    unique_changes = int((unified != original).sum())
    return unified, {
        "celdas_con_espacios_normalizados": spacing_changes,
        "celdas_con_variantes_unificadas": variant_changes,
        "celdas_textuales_unicas_modificadas": unique_changes,
        "placeholders_detectados": int(semantic_mask.sum()),
        "mojibake_detectado": mojibake_detected,
        "mojibake_reparado": mojibake_repaired,
        "fusiones_fuzzy": fuzzy_merges,
    }, fuzzy_examples, mojibake_audit, suggestions


# ── Pipeline de estandarización ──────────────────────────────────────────────


def standardize_dataframe(
    df: pd.DataFrame, mapping: dict | None = None
) -> tuple[pd.DataFrame, dict]:
    """Devuelve (df_estandarizado, reporte de cambios, tipos y confianza)."""
    result = df.copy()
    # SOURCE_ROWS_ATTR puede contener cientos de miles de enteros. pandas
    # copia attrs al crear Series/resultados; lo guardamos una vez y lo
    # restauramos al final para mantener trazabilidad sin ese costo repetido.
    source_attrs = dict(result.attrs)
    result.attrs = {}
    renamed_headers = normalize_headers(result)
    roles = resolve_mapping(list(result.columns), mapping)
    roles_by_col = {column: role for role, column in roles.items()}

    column_types: dict[str, str] = {}
    column_confidence: dict[str, float] = {}
    numeric_conventions: dict[str, str] = {}
    date_dayfirst: dict[str, bool] = {}
    fuzzy_total = 0
    fuzzy_examples: list[list[str]] = []
    date_avisos: list[str] = []
    mojibake_audit: list[dict] = []
    text_changes = date_changes = number_changes = 0
    text_detail = {
        "celdas_con_espacios_normalizados": 0,
        "celdas_con_variantes_unificadas": 0,
        "celdas_textuales_unicas_modificadas": 0,
        "placeholders_detectados": 0,
        "mojibake_detectado": 0,
        "mojibake_reparado": 0,
        "fusiones_fuzzy": 0,
    }

    for col in result.columns:
        ctype, confidence = detect_value_type_confidence(result[col], col)
        column_types[col] = ctype
        column_confidence[col] = confidence

        if ctype == "texto":
            # Fase 10 §6.1: nada de fuzzy sobre identificadores (SKU, folio,
            # RUT, email…) — un typo de distancia 1 puede ser otro código real.
            allow_fuzzy = not is_identifier_column(col, result[col])
            result[col], detail, examples, column_mojibake, suggestions = _normalize_text_column(
                result[col], allow_fuzzy=allow_fuzzy, role=roles_by_col.get(col)
            )
            for key in text_detail:
                text_detail[key] += detail[key]
            text_changes += detail["celdas_textuales_unicas_modificadas"]
            if examples:
                # Conteo real de variantes fusionadas (no los ejemplos capados)
                fuzzy_total += detail["fusiones_fuzzy"]
                fuzzy_examples.extend(examples[: max(0, 5 - len(fuzzy_examples))])
            for audit in column_mojibake:
                if len(mojibake_audit) >= 5000:
                    break
                mojibake_audit.append({"columna": col, **audit})
            # Bug: truncamientos como "conce"/"Concepción" no son una
            # abreviación conocida — se avisan en vez de fusionarse solos o
            # pasar calladas, para que el usuario confirme manualmente.
            for rare_display, canon_display, rare_count in suggestions[:3]:
                date_avisos.append(
                    f"En '{col}': \"{rare_display}\" ({rare_count} fila(s)) podría ser una "
                    f"forma abreviada de \"{canon_display}\" — revísalo y corrígelo a mano "
                    "si corresponde a la misma sucursal o categoría."
                )
        elif ctype == "fecha":
            profile = column_date_profile(result[col])
            dayfirst = profile["dayfirst"]
            date_dayfirst[col] = dayfirst
            if profile["mixta"]:
                # Fase 11 §7: DD/MM y MM/DD conviven en la misma columna.
                # Los valores inequívocos se resuelven por su propia evidencia
                # (parse_date); los ambiguos usan la convención dominante y el
                # usuario queda AVISADO en vez de una conversión silenciosa.
                dominante = "día/mes (es-CL)" if dayfirst else "mes/día (US)"
                date_avisos.append(
                    f"La columna '{col}' mezcla formatos de fecha día/mes y mes/día "
                    f"({profile['dmy']} y {profile['mdy']} valores inequívocos). "
                    f"{profile['ambiguas']} fecha(s) ambiguas se interpretaron como "
                    f"{dominante} — revísalas antes de confiar en los meses."
                )

            def _standardize_date(value: str) -> str:
                if is_missing(value):
                    return ""
                parsed = parse_date(value, dayfirst=dayfirst)
                if parsed is None:
                    return str(value).strip()
                # Fase 13 (P0.7): si el valor original traía HORA distinta de
                # medianoche, se conserva — dos eventos del mismo día no deben
                # volverse indistinguibles (Excel serializa fechas puras como
                # "00:00:00": esa medianoche NO se conserva).
                time_match = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", str(value))
                if time_match and time_match.group(1) not in ("0:00", "00:00", "00:00:00", "0:00:00"):
                    return f"{parsed.strftime('%d/%m/%Y')} {time_match.group(1)}"
                return parsed.strftime("%d/%m/%Y")

            new = map_unique(result[col], _standardize_date)
            date_changes += int((new != result[col].map(str)).sum())
            result[col] = new
        else:
            convention = column_dot3_convention(result[col])
            numeric_conventions[col] = convention
            comma_convention, ambiguous_commas = column_comma3_convention(result[col])
            if ambiguous_commas and comma_convention == "decimal":
                # Fase 12b: sin evidencia en la columna, "1,234" se interpreta
                # como decimal (es-CL) — pero el usuario DEBE saberlo, porque
                # en formato US significaría mil doscientos treinta y cuatro.
                date_avisos.append(
                    f"La columna '{col}' tiene {ambiguous_commas} valor(es) como "
                    "'1,234', ambiguos entre decimal (es-CL) y miles (US). Se "
                    "interpretaron como DECIMAL por convención chilena; si tus "
                    "datos vienen en formato estadounidense, corrígelo en el "
                    "origen o revisa esos montos."
                )

            def _standardize_number(value: str) -> str:
                if is_missing(value):
                    return ""
                number = parse_number(
                    value,
                    dot3_convention=convention,
                    comma3_convention=comma_convention,
                )
                return str(value).strip() if number is None else format_number(number)

            new = map_unique(result[col], _standardize_number)
            number_changes += int((new != result[col].map(str)).sum())
            result[col] = new

    if text_detail["mojibake_detectado"]:
        pending = text_detail["mojibake_detectado"] - text_detail["mojibake_reparado"]
        date_avisos.append(
            f"Se detectaron {text_detail['mojibake_detectado']} celda(s) con texto "
            f"posiblemente mal codificado; {text_detail['mojibake_reparado']} se "
            f"repararon con conversión strict y {pending} quedaron para revisión."
        )

    report = {
        "column_types": column_types,
        "column_confidence": column_confidence,
        "convenciones_numericas": numeric_conventions,
        "fechas_dayfirst": date_dayfirst,
        "avisos": date_avisos,
        "fusiones_texto": {"total": fuzzy_total, "ejemplos": fuzzy_examples},
        "mojibake_auditoria": mojibake_audit,
        "cambios": {
            "encabezados_normalizados": renamed_headers,
            "textos_normalizados": text_changes,
            "fechas_estandarizadas": date_changes,
            "numeros_estandarizados": number_changes,
            **text_detail,
        },
    }
    result.attrs.update(source_attrs)
    return result, report
