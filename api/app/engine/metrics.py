"""Indicadores básicos a partir del dataset limpio (SPEC §6, POST /metrics).

Fase 1: métricas derivables de un archivo de ventas (ingresos, evolución
mensual, por categoría/canal, top productos). Los ratios financieros que
requieren balance (ROA, ROE, liquidez) llegan con el dashboard de la Fase 2.
"""

import pandas as pd

from .mapping import detect_column_roles
from .standardize import is_missing, parse_date, parse_number


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].map(lambda v: parse_number(v) if not is_missing(v) else None).astype(float)


def _group_sum(df: pd.DataFrame, by_column: str, amounts: pd.Series) -> list[dict]:
    grouped = (
        pd.DataFrame({"grupo": df[by_column], "monto": amounts})
        .dropna(subset=["monto"])
        .groupby("grupo", dropna=False)["monto"]
        .sum()
        .sort_values(ascending=False)
    )
    total = float(grouped.sum()) or 1.0
    return [
        {
            "nombre": str(name) if str(name).strip() else "Sin clasificar",
            "monto": round(float(value), 2),
            "porcentaje": round(float(value) / total * 100, 1),
        }
        for name, value in grouped.items()
    ]


def compute_metrics(df: pd.DataFrame, mapping: dict[str, str] | None = None) -> dict:
    roles = mapping or detect_column_roles(list(df.columns))
    roles = {role: col for role, col in roles.items() if col in df.columns}
    warnings: list[str] = []

    result: dict = {
        "moneda": "CLP",
        "mapeo": roles,
        "transacciones": len(df),
    }

    amount_col = roles.get("monto")
    if amount_col is None:
        warnings.append(
            "No se detectó una columna de monto/ventas; los indicadores monetarios quedan en 0."
        )
        amounts = pd.Series([None] * len(df), dtype=float)
    else:
        amounts = _numeric_series(df, amount_col)

    result["ingresos_totales"] = round(float(amounts.dropna().sum()), 2)
    result["ticket_promedio"] = (
        round(float(amounts.dropna().mean()), 2) if amounts.notna().any() else 0.0
    )

    quantity_col = roles.get("cantidad")
    if quantity_col is not None:
        quantities = _numeric_series(df, quantity_col)
        result["unidades_totales"] = round(float(quantities.dropna().sum()), 2)

    date_col = roles.get("fecha")
    if date_col is not None:
        months = df[date_col].map(
            lambda v: parsed.strftime("%Y-%m") if (parsed := parse_date(v)) else None
        )
        monthly = (
            pd.DataFrame({"mes": months, "monto": amounts})
            .dropna(subset=["mes", "monto"])
            .groupby("mes")["monto"]
            .sum()
            .sort_index()
        )
        result["evolucion_mensual"] = [
            {"mes": str(month), "ingresos": round(float(value), 2)}
            for month, value in monthly.items()
        ]
    else:
        warnings.append("No se detectó una columna de fecha; sin evolución mensual.")

    if amount_col is not None:
        for role, key, limit in (
            ("categoria", "por_categoria", None),
            ("canal", "ventas_por_canal", None),
            ("producto", "top_productos", 5),
            ("sucursal", "por_sucursal", None),
        ):
            col = roles.get(role)
            if col is not None:
                groups = _group_sum(df, col, amounts)
                result[key] = groups[:limit] if limit else groups

    result["advertencias"] = warnings
    return result
