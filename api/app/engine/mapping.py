"""Mapeo automatico de columnas al esquema normalizado del negocio (SPEC §5).

Detecta por nombre de encabezado que columna cumple cada rol
(fecha, cliente, producto, categoria, monto, cantidad, canal, sucursal, vendedor).
"""

import re
import unicodedata


def strip_accents_lower(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


def norm_key(value: str) -> str:
    """Clave de comparacion agresiva: solo letras y digitos, sin acentos, minusculas."""
    return re.sub(r"[^a-z0-9]", "", strip_accents_lower(str(value)))


# Abreviaciones societarias chilenas: mapeo DESPUES de norm_key.
_ENTITY_ABBREVS: tuple[tuple[str, str], ...] = (
    ("limitada", "ltda"),
    ("sociedadanonima", "sa"),
    ("socanon", "sa"),
    ("sociedadporacciones", "spa"),
    ("empresaindividual", "eirl"),
)


def dedup_norm_key(value: str) -> str:
    """norm_key + normalizacion de abreviaciones societarias chilenas.
    Hace que 'Santiago Limitada' y 'SANTIAGO LTDA' produzcan la misma clave."""
    key = norm_key(value)
    for full, abbrev in _ENTITY_ABBREVS:
        key = key.replace(full, abbrev)
    return key


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


def detect_column_roles(columns: list[str]) -> dict[str, str]:
    """Devuelve {rol: nombre_de_columna} para las columnas reconocidas."""
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    normalized = {col: re.sub(r"\s+", " ", strip_accents_lower(col)) for col in columns}
    for role, keywords in ROLE_KEYWORDS:
        for col in columns:
            if col in taken:
                continue
            if any(keyword in normalized[col] for keyword in keywords):
                mapping[role] = col
                taken.add(col)
                break
    return mapping
