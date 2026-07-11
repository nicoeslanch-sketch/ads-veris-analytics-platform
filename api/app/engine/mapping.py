"""Mapeo automático de columnas al esquema normalizado del negocio (SPEC §5 + Fase 9).

Detecta por nombre de encabezado qué columna cumple cada rol del MOTOR
(fecha, monto, costo, cantidad, producto, categoria, cliente, canal,
sucursal, vendedor) — los 10 roles que alimentan métricas y limpieza.

Fase 9 — mapeo universal en dos pasadas:
1. **Diccionario** (`engine/dictionary.py`, ≈15.600 claves, 64 roles): cada
   columna se matchea (exacto → contención → prefijo → fuzzy) y, si su rol
   extendido tiene equivalencia segura con un rol del motor (`rol_motor` del
   CSV), esa columna gana el rol. Es mucho más preciso: "Total Neto Factura",
   "qty shipped" o "Fec_Emision" se reconocen sin tocar código.
2. **Compatibilidad legacy**: para los roles del motor que queden vacíos se
   corre la lista original de palabras clave sobre las columnas aún libres.
   Esto preserva el comportamiento histórico (ej: un archivo cuyo único campo
   de dinero es "Precio" sigue alimentando `monto`; "Región" sigue cayendo en
   `sucursal` si no hay una sucursal real), y el diccionario solo mejora la
   precisión cuando existe una columna mejor.

`detect_columns_extended` expone además el rol EXTENDIDO por columna (64
roles: rut, email, saldo, precio_unitario, etc.) con el método y la confianza
del match — visible en el reporte de calidad y en /standardize, e insumo del
clasificador IA (costura Fase 9) y de la biblioteca de prompts.
"""

import re
import unicodedata

from . import dictionary
from .dictionary import DictMatch


def strip_accents_lower(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


def norm_key(value: str) -> str:
    """Clave de comparación agresiva: solo letras y dígitos, sin acentos, minúsculas."""
    return re.sub(r"[^a-z0-9]", "", strip_accents_lower(str(value)))


# Abreviaciones societarias chilenas: mapeo DESPUÉS de norm_key.
_ENTITY_ABBREVS: tuple[tuple[str, str], ...] = (
    ("limitada", "ltda"),
    ("sociedadanonima", "sa"),
    ("socanon", "sa"),
    ("sociedadporacciones", "spa"),
    ("empresaindividual", "eirl"),
)


def dedup_norm_key(value: str) -> str:
    """norm_key + normalización de abreviaciones societarias chilenas.
    Hace que 'Santiago Limitada' y 'SANTIAGO LTDA' produzcan la misma clave."""
    key = norm_key(value)
    for full, abbrev in _ENTITY_ABBREVS:
        key = key.replace(full, abbrev)
    return key


# Palabras clave LEGACY (red de compatibilidad, segunda pasada).
# El orden importa: el primer rol que matchea se queda con la columna.
ROLE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("fecha", ["fecha", "date", "periodo", "emision"]),
    ("monto", ["venta", "monto", "total", "importe", "ingreso", "facturacion", "valor", "precio"]),
    ("costo", ["costo", "cost", "compra", "gasto"]),
    ("cantidad", ["cantidad", "unidades", "qty", "cant."]),
    ("producto", ["producto", "servicio", "articulo", "item", "sku"]),
    ("categoria", ["categoria", "rubro", "linea", "familia", "tipo de producto"]),
    ("cliente", ["cliente", "razon social", "customer", "comprador"]),
    ("canal", ["canal", "channel", "medio de venta"]),
    ("sucursal", ["sucursal", "tienda", "local", "sede", "region"]),
    ("vendedor", ["vendedor", "ejecutivo", "seller", "representante"]),
]

ENGINE_ROLES: tuple[str, ...] = tuple(role for role, _ in ROLE_KEYWORDS)

_METHOD_RANK = {"exacto": 4, "contencion": 3, "prefijo": 2, "fuzzy": 1, "ia": 1}


def detect_columns_extended(columns: list[str]) -> dict[str, DictMatch]:
    """Rol extendido (64 roles) por columna, según el diccionario Fase 9."""
    return dictionary.match_columns([str(c) for c in columns])


def detect_column_roles(columns: list[str]) -> dict[str, str]:
    """Devuelve {rol_del_motor: nombre_de_columna} para las columnas reconocidas."""
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    matches = detect_columns_extended(columns)

    # ── Pasada 1: diccionario (rol_motor con equivalencia segura) ──
    for role in ENGINE_ROLES:
        best: tuple[tuple[int, int, int], str] | None = None
        for index, col in enumerate(columns):
            if col in taken:
                continue
            match = matches.get(col)
            if not match or match.rol_motor != role:
                continue
            rank = (_METHOD_RANK.get(match.metodo, 0), match.prioridad, -index)
            if best is None or rank > best[0]:
                best = (rank, col)
        if best:
            mapping[role] = best[1]
            taken.add(best[1])

    # ── Pasada 2: compatibilidad legacy para roles aún vacíos ──
    normalized = {col: re.sub(r"\s+", " ", strip_accents_lower(col)) for col in columns}
    for role, keywords in ROLE_KEYWORDS:
        if role in mapping:
            continue
        for col in columns:
            if col in taken:
                continue
            if any(keyword in normalized[col] for keyword in keywords):
                mapping[role] = col
                taken.add(col)
                break
    return mapping

# Roles que consume el motor de métricas (equivale a clean.VALID_ROLES).
ENGINE_ROLES = (
    "fecha", "monto", "costo", "cantidad", "producto", "categoria",
    "cliente", "canal", "sucursal", "vendedor",
)


def resolve_mapping(columns: list[str], override: dict | None) -> dict[str, str]:
    """Mapeo automático FUSIONADO con las correcciones del usuario (Fase 11).

    Única fuente de verdad para /clean, /metrics, descargas e historial: un
    override parcial jamás borra los roles detectados automáticamente."""
    detected = detect_column_roles(columns)
    if not override:
        return detected
    resolved = dict(detected)
    for role, col in override.items():
        role_key = str(role).strip().lower()
        if role_key not in ENGINE_ROLES:
            continue
        if not col:
            resolved.pop(role_key, None)
            continue
        if col in columns:
            # Un mismo nombre de columna no puede cumplir dos roles.
            for other_role, other_col in list(resolved.items()):
                if other_col == col and other_role != role_key:
                    resolved.pop(other_role)
            resolved[role_key] = col
    return resolved
