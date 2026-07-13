"""Indicadores del dashboard a partir del dataset limpio (SPEC §7, POST /metrics).

Fase 2: KPIs con variación vs periodo anterior, evolución mensual de ingresos/
gastos/utilidad, análisis por categoría, ventas por canal, top productos y
proyección a 3 meses. Todo filtrable por rango de fechas.

Gastos y utilidad se calculan solo si el archivo trae una columna de costo.
Los ratios financieros que requieren balance (ROA, ROE, liquidez, prueba ácida,
rotación de inventario, días de cobro/pago) quedan declarados pero sin valor:
se habilitan cuando el usuario conecte sus datos financieros.
"""

import re

import pandas as pd

from .mapping import detect_column_roles, resolve_mapping
from .standardize import (
    is_missing,
    map_unique,
    missing_mask,
    parse_date,
    parse_number,
    semantic_missing_mask,
)

FINANCIAL_RATIOS = [
    "roa",
    "roe",
    "liquidez_corriente",
    "prueba_acida",
    "rotacion_inventario",
    "dias_cobro",
    "dias_pago",
]


def _numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None or column not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype=float)
    return map_unique(
        df[column], lambda v: parse_number(v) if not is_missing(v) else None
    ).astype(float)


# ── Moneda (Fase 10 §4.4): detección por tokens en la columna de montos ─────
# El parser acepta "$ 1.200", "US$1.500", "€200"… pero el dashboard debe saber
# QUÉ moneda está mostrando, y jamás sumar monedas distintas en silencio.
_CURRENCY_SIGNALS = {
    "USD": re.compile(r"(?i)(us\$|usd)"),
    "EUR": re.compile(r"(?i)(€|eur)"),
    "CLP": re.compile(r"(?i)(clp)"),
}


def detect_currency(raw: pd.Series | None) -> tuple[str, str | None]:
    """(moneda_dominante, advertencia_o_None) a partir de los valores crudos.

    '$' a secas se asume CLP (convención es-CL); solo tokens explícitos
    (US$, USD, €, EUR, CLP) cambian o mezclan la moneda."""
    if raw is None:
        return "CLP", None
    counts = {code: 0 for code in _CURRENCY_SIGNALS}
    sample = [str(v) for v in raw.head(1000) if not is_missing(v)]
    for value in sample:
        for code, pattern in _CURRENCY_SIGNALS.items():
            if pattern.search(value):
                counts[code] += 1
                break
    explicit = {code: n for code, n in counts.items() if n > 0}
    if not explicit:
        return "CLP", None
    dominant = max(explicit, key=lambda c: explicit[c])
    others = [c for c in explicit if c != dominant]
    # Sin token explícito la fila se asume en la moneda dominante; si hay más
    # de un token explícito distinto, los totales estarían mezclando monedas.
    if others:
        detalle = ", ".join(sorted(explicit))
        return dominant, (
            f"Se detectaron montos en más de una moneda ({detalle}). Los totales "
            "suman los valores SIN convertir: revisa la columna de montos o "
            "sepárala por moneda antes de comparar."
        )
    if dominant != "CLP":
        return dominant, (
            f"Los montos parecen estar en {dominant}: los indicadores se muestran "
            "en esa moneda, sin conversión a pesos chilenos."
        )
    return dominant, None


def _pct_change(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def _kpi(value: float, previous: float | None) -> dict:
    return {"valor": round(value, 2), "variacion_pct": _pct_change(value, previous)}


def _group_sum(
    groups: pd.Series, amounts: pd.Series, profits: pd.Series | None
) -> list[dict]:
    frame = pd.DataFrame({"grupo": groups, "monto": amounts})
    if profits is not None:
        frame["utilidad"] = profits
    frame = frame.dropna(subset=["monto"])
    if frame.empty:
        return []
    aggregated = frame.groupby("grupo", dropna=False).sum(numeric_only=True)
    aggregated = aggregated.sort_values("monto", ascending=False)
    total = float(aggregated["monto"].sum()) or 1.0
    rows: list[dict] = []
    for name, row in aggregated.iterrows():
        item = {
            "nombre": str(name) if str(name).strip() else "Sin clasificar",
            "ingresos": round(float(row["monto"]), 2),
            "porcentaje": round(float(row["monto"]) / total * 100, 1),
        }
        if profits is not None:
            utilidad = float(row["utilidad"]) if pd.notna(row["utilidad"]) else 0.0
            item["utilidad"] = round(utilidad, 2)
            item["margen_pct"] = (
                round(utilidad / float(row["monto"]) * 100, 1) if row["monto"] else None
            )
        rows.append(item)
    return rows


def _projection(monthly: pd.DataFrame) -> dict | None:
    """Proyección simple a 3 meses por crecimiento promedio mensual."""
    series = monthly["ingresos"].astype(float)
    if len(series) < 2 or series.iloc[:-1].le(0).any():
        return None
    growth_rates = series.pct_change().dropna()
    # Acotar tasas extremas para que un mes atípico no dispare la proyección.
    growth = float(growth_rates.clip(-0.5, 0.5).mean())
    last_month = pd.Period(monthly.index[-1], freq="M")
    last_value = float(series.iloc[-1])
    projected = []
    value = last_value
    for step in range(1, 4):
        value = value * (1 + growth)
        projected.append(
            {"mes": str(last_month + step), "ingresos": round(max(value, 0.0), 2)}
        )
    base = float(series.tail(3).sum())
    total_projected = sum(month["ingresos"] for month in projected)
    return {
        "crecimiento_pct": round(growth * 100, 1),
        "crecimiento_trimestre_pct": _pct_change(total_projected, base if base else None),
        "meses": projected,
    }


def compute_metrics(
    df: pd.DataFrame,
    mapping: dict[str, str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    currency_hint: tuple[str, str | None] | None = None,
) -> dict:
    """`currency_hint` viene del pipeline (detección sobre los valores CRUDOS,
    antes de que la estandarización quite los símbolos de moneda)."""
    # Fase 11 §9.2: el mapeo manual se FUSIONA con el automático. Antes un
    # override parcial (ej: solo "monto") reemplazaba el mapeo completo y
    # hacía desaparecer fecha/categoría/canal detectados → dashboard vacío.
    roles = resolve_mapping(list(df.columns), mapping)
    roles = {role: col for role, col in roles.items() if col in df.columns}
    warnings: list[str] = []

    amounts_all = _numeric_series(df, roles.get("monto"))
    costs_all = _numeric_series(df, roles.get("costo"))
    has_costs = roles.get("costo") is not None and costs_all.notna().any()
    profits_all = (amounts_all - costs_all) if has_costs else None

    if roles.get("monto") is None:
        warnings.append(
            "No se detectó una columna de monto/ventas; los indicadores monetarios quedan en 0."
        )
    if not has_costs:
        warnings.append(
            "No se detectó una columna de costos; gastos, utilidad y margen requieren esa columna."
        )

    dates_all = (
        map_unique(df[roles["fecha"]], parse_date)
        if roles.get("fecha")
        else pd.Series([None] * len(df))
    )
    has_dates = roles.get("fecha") is not None and dates_all.notna().any()
    if not has_dates:
        warnings.append("No se detectó una columna de fecha; sin evolución mensual ni proyección.")

    # ── Evolución mensual (siempre sobre el periodo completo) ──
    monthly = pd.DataFrame()
    if has_dates:
        frame = pd.DataFrame(
            {
                "mes": dates_all.map(lambda d: d.strftime("%Y-%m") if pd.notna(d) else None),
                "ingresos": amounts_all,
            }
        )
        if has_costs:
            frame["gastos"] = costs_all
            frame["utilidad"] = profits_all
        monthly = (
            frame.dropna(subset=["mes", "ingresos"]).groupby("mes").sum(numeric_only=True).sort_index()
        )

    evolucion = [
        {
            "mes": str(month),
            "ingresos": round(float(row["ingresos"]), 2),
            **(
                {
                    "gastos": round(float(row["gastos"]), 2),
                    "utilidad": round(float(row["utilidad"]), 2),
                }
                if has_costs
                else {}
            ),
        }
        for month, row in monthly.iterrows()
    ]

    # ── Selección por rango de fechas ──
    start = pd.to_datetime(date_from) if date_from else None
    end = pd.to_datetime(date_to) if date_to else None
    if has_dates and (start is not None or end is not None):
        mask = dates_all.map(
            lambda d: bool(
                pd.notna(d)
                and (start is None or d >= start)
                and (end is None or d <= end)
            )
        )
    else:
        mask = pd.Series([True] * len(df), index=df.index)

    selection = df[mask]
    amounts = amounts_all[mask]
    costs = costs_all[mask]
    profits = profits_all[mask] if profits_all is not None else None

    # ── Periodo anterior para las variaciones (Fase 10 §4.5) ──
    # Si la selección es un mes calendario completo, el periodo anterior es el
    # MES CALENDARIO anterior (mayo se compara con abril, no con una ventana de
    # 31 días que arrastra el 31 de marzo). Para rangos arbitrarios se mantiene
    # la ventana equivalente de días.
    prev_amounts = prev_costs = None
    prev_mask = None
    if has_dates and start is not None and end is not None:
        month_end = start + pd.offsets.MonthEnd(0)
        is_full_month = start.day == 1 and end.normalize() == month_end.normalize()
        if is_full_month:
            prev_end = start - pd.Timedelta(days=1)
            prev_start = prev_end.replace(day=1)
            prev_mask = dates_all.map(
                lambda d: bool(pd.notna(d) and prev_start <= d <= prev_end)
            )
        else:
            window = end - start
            prev_mask = dates_all.map(
                lambda d: bool(pd.notna(d) and (start - window - pd.Timedelta(days=1)) <= d < start)
            )
        if not prev_mask.any():
            prev_mask = None
    # Sin rango seleccionado ("todo el periodo") no hay periodo anterior
    # comparable: las variaciones quedan en null y la UI muestra "—".

    ingresos = float(amounts.dropna().sum())

    # ── Cobertura de costos (Fase 10 §4.1) ──
    # Utilidad y margen se calculan SOLO sobre las filas que tienen ingreso Y
    # costo. Antes se restaban los costos conocidos del total de ingresos, lo
    # que trataba los costos faltantes como $0 e inflaba la utilidad.
    filas_con_ingreso = int(amounts.notna().sum())
    paired_mask = amounts.notna() & costs.notna() if has_costs else None
    filas_pareadas = int(paired_mask.sum()) if paired_mask is not None else 0
    cobertura_pct = (
        round(filas_pareadas / filas_con_ingreso * 100, 1) if filas_con_ingreso else 0.0
    )

    gastos = float(costs.dropna().sum()) if has_costs else None
    if has_costs and filas_pareadas:
        ingresos_pareados = float(amounts[paired_mask].sum())
        utilidad = ingresos_pareados - float(costs[paired_mask].sum())
        margen = round(utilidad / ingresos_pareados * 100, 1) if ingresos_pareados else None
    else:
        ingresos_pareados = 0.0
        utilidad = None
        margen = None

    prev_utilidad = prev_margen = None
    if prev_mask is not None:
        prev_amounts = float(amounts_all[prev_mask].dropna().sum())
        prev_costs = float(costs_all[prev_mask].dropna().sum())
        if has_costs:
            prev_paired = amounts_all.notna() & costs_all.notna() & prev_mask
            if prev_paired.any():
                prev_ing_par = float(amounts_all[prev_paired].sum())
                prev_utilidad = prev_ing_par - float(costs_all[prev_paired].sum())
                prev_margen = (
                    round(prev_utilidad / prev_ing_par * 100, 1) if prev_ing_par else None
                )

    if has_costs and filas_con_ingreso and cobertura_pct < 99.5:
        warnings.append(
            f"{filas_con_ingreso - filas_pareadas} de {filas_con_ingreso} ventas no "
            f"tienen costo asociado (cobertura {cobertura_pct}%): la utilidad y el "
            "margen se calculan solo sobre las ventas con costo — son resultados "
            "PARCIALES, no el total del negocio."
        )

    kpis: dict = {
        "ingresos_totales": _kpi(ingresos, prev_amounts),
        "transacciones": int(len(selection)),
        "ticket_promedio": round(float(amounts.dropna().mean()), 2) if amounts.notna().any() else 0.0,
    }
    if roles.get("cantidad"):
        kpis["unidades_totales"] = round(
            float(_numeric_series(selection, roles["cantidad"]).dropna().sum()), 2
        )
    if has_costs and utilidad is not None:
        kpis["gastos_totales"] = _kpi(gastos, prev_costs)
        # Nota Fase 10 §4.2: esto es UTILIDAD BRUTA (venta − costo directo),
        # no ganancia neta — faltan gastos operacionales, sueldos, impuestos…
        # La clave JSON se mantiene por compatibilidad; la UI la rotula
        # "Utilidad Bruta" y "Resultado del Periodo".
        kpis["ganancia_neta"] = _kpi(utilidad, prev_utilidad)
        kpis["margen_utilidad_pct"] = {
            "valor": margen,
            "variacion_puntos": round(margen - prev_margen, 1)
            if margen is not None and prev_margen is not None
            else None,
        }
        kpis["flujo_caja"] = _kpi(utilidad, prev_utilidad)
        kpis["cobertura_costos"] = {
            "filas_con_ingreso": filas_con_ingreso,
            "filas_con_ingreso_y_costo": filas_pareadas,
            "pct": cobertura_pct,
        }
    else:
        kpis["gastos_totales"] = None
        kpis["ganancia_neta"] = None
        kpis["margen_utilidad_pct"] = None
        kpis["flujo_caja"] = None

    # ── Agrupaciones sobre la selección ──
    def _has_data(role: str) -> bool:
        col = roles.get(role)
        if col is None:
            return False
        semantic = semantic_missing_mask(df[col], role)
        return bool((~missing_mask(df[col]) & ~semantic).any())

    moneda, aviso_moneda = (
        currency_hint
        if currency_hint is not None
        else detect_currency(df[roles["monto"]] if roles.get("monto") else None)
    )
    if aviso_moneda:
        warnings.insert(0, aviso_moneda)

    result: dict = {
        "moneda": moneda,
        "mapeo": roles,
        # Fase 8: qué dimensiones REALES trae este dataset. El frontend adapta
        # Explorar y Resumen a esto (sin tarjetas vacías ni análisis imposibles).
        "dimensiones": {
            "fecha": bool(has_dates),
            "monto": _has_data("monto"),
            "costo": bool(has_costs),
            "cantidad": _has_data("cantidad"),
            "categoria": _has_data("categoria"),
            "producto": _has_data("producto"),
            "canal": _has_data("canal"),
            "sucursal": _has_data("sucursal"),
            "cliente": _has_data("cliente"),
            "vendedor": _has_data("vendedor"),
        },
        "periodo": {
            "desde": date_from,
            "hasta": date_to,
            "meses_disponibles": [str(m) for m in monthly.index] if has_dates else [],
        },
        "kpis": kpis,
        "evolucion_mensual": evolucion,
    }

    if roles.get("categoria"):
        result["por_categoria"] = _group_sum(
            selection[roles["categoria"]], amounts, profits
        )
    canal_role = "canal" if roles.get("canal") else ("sucursal" if roles.get("sucursal") else None)
    result["agrupado_por_canal"] = canal_role
    if canal_role:
        result["ventas_por_canal"] = _group_sum(selection[roles[canal_role]], amounts, None)
    if roles.get("producto"):
        result["top_productos"] = _group_sum(selection[roles["producto"]], amounts, None)[:5]

    result["proyeccion"] = _projection(monthly) if has_dates and not monthly.empty else None
    result["indicadores_financieros"] = {
        "disponible": False,
        "nota": (
            "ROA, ROE, liquidez, prueba ácida, rotación de inventario y días de "
            "cobro/pago requieren datos de balance (activos, pasivos, inventario, "
            "cuentas por cobrar/pagar). Se habilitan al conectar esos datos."
        ),
        "items": {ratio: None for ratio in FINANCIAL_RATIOS},
    }
    result["advertencias"] = warnings
    return result
