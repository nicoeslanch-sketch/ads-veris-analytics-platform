"""Mapeo automático de columnas al esquema normalizado del negocio (SPEC §5).

Detecta por nombre de encabezado qué columna cumple cada rol
(fecha, cliente, producto, categoría, monto, cantidad, canal, sucursal, vendedor).
"""

import re
import unicodedata


def strip_accents_lower(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


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
