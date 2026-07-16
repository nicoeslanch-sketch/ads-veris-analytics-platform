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

from .mapping import (
    detect_column_roles,
    resolve_mapping,
    strip_accents_lower,
)
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
# Fase 13 (P0.5): TODAS las monedas cuyo token elimina el estandarizador —
# antes UF/ARS/PEN/COP/MXN perdían su token y el dashboard las mostraba
# como pesos chilenos sin aviso.
_CURRENCY_SIGNALS = {
    "USD": re.compile(r"(?i)(us\$|usd)"),
    "EUR": re.compile(r"(?i)(€|eur)"),
    "CLP": re.compile(r"(?i)(clp)"),
    "UF": re.compile(r"(?i)\buf\b"),
    "ARS": re.compile(r"(?i)\bars\b"),
    "PEN": re.compile(r"(?i)(\bpen\b|s/\.?\s?\d)"),
    "COP": re.compile(r"(?i)\bcop\b"),
    "MXN": re.compile(r"(?i)\bmxn\b"),
    "GBP": re.compile(r"(?i)(£|gbp)"),
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
    groups: pd.Series, amounts: pd.Series, costs: pd.Series | None
) -> list[dict]:
    """Ingresos por grupo; con costos, utilidad y margen SOLO sobre filas
    pareadas (ingreso Y costo) — misma regla que el KPI global (Fase 12: antes
    el margen por grupo dividía por los ingresos totales del grupo, y con
    cobertura parcial de costos quedaba subestimado)."""
    frame = pd.DataFrame({"grupo": groups, "monto": amounts})
    has_costs = costs is not None
    if has_costs:
        frame["costo"] = costs
    frame = frame.dropna(subset=["monto"])
    if frame.empty:
        return []
    # Fase 13 (P0.3): la participación se calcula sobre las ventas BRUTAS
    # positivas — con devoluciones, dividir por el neto disparaba porcentajes
    # absurdos (100.000 sobre un neto de 10.000 = "1.000%").
    positivos = float(frame.loc[frame["monto"] > 0, "monto"].sum())
    total = positivos if positivos > 0 else (abs(float(frame["monto"].sum())) or 1.0)
    rows: list[dict] = []
    for name, g in frame.groupby("grupo", dropna=False):
        ingresos = float(g["monto"].sum())
        # Fase 14b: participación BRUTA por grupo — una distribución real que
        # suma ≈100%. `porcentaje` (neto del grupo / brutas totales) se
        # conserva para mostrar el efecto de las devoluciones, pero las
        # afirmaciones de CONCENTRACIÓN ("X concentra el N% de tus ventas")
        # usan participacion_bruta_pct: con devoluciones, el neto no es una
        # distribución (A:+100.000 y B:-90.000 daban 100% y -90%).
        brutas = float(g.loc[g["monto"] > 0, "monto"].sum())
        devoluciones_grupo = float(g.loc[g["monto"] < 0, "monto"].sum())
        item = {
            "nombre": str(name) if str(name).strip() else "Sin clasificar",
            "ingresos": round(ingresos, 2),
            "porcentaje": round(ingresos / total * 100, 1),
            "ventas_brutas": round(brutas, 2),
            "devoluciones": round(devoluciones_grupo, 2),
            "ventas_netas": round(ingresos, 2),
            "participacion_bruta_pct": (
                round(brutas / positivos * 100, 1) if positivos > 0 else None
            ),
        }
        # Fase 12b §22: cada grupo expone su base de cálculo — sin esto, una
        # categoría con UNA fila con costo competía en "rentabilidad" contra
        # otra con mil, y nadie podía notarlo.
        item["filas"] = int(len(g))
        if has_costs:
            paired = g.dropna(subset=["costo"])
            item["filas_pareadas"] = int(len(paired))
            item["cobertura_costos_pct"] = round(len(paired) / len(g) * 100, 1)
            if len(paired):
                ing_par = float(paired["monto"].sum())
                utilidad = ing_par - float(paired["costo"].sum())
                item["utilidad"] = round(utilidad, 2)
                item["margen_pct"] = (
                    round(utilidad / ing_par * 100, 1) if ing_par else None
                )
            # Grupo sin ninguna fila pareada: sin utilidad/margen (la UI
            # muestra "—" en vez de un 0 falso).
        rows.append(item)
    rows.sort(key=lambda r: r["ingresos"], reverse=True)
    return rows


def _projection(monthly: pd.DataFrame, first_month: pd.Period | None = None) -> dict | None:
    """Proyección simple a 3 meses por crecimiento promedio mensual.

    Fase 14: cuando el último mes de la serie real está PARCIAL, se pasa aquí
    la serie SIN ese mes (la tasa y la base usan solo meses completos — el mes
    a medio llenar deprimía el crecimiento con una caída ficticia) y
    `first_month` fija el primer mes proyectado DESPUÉS del final real, para
    que la proyección jamás se superponga con un mes que sí tiene datos.
    """
    series = monthly["ingresos"].astype(float)
    if len(series) < 2 or series.iloc[:-1].le(0).any():
        return None
    growth_rates = series.pct_change().dropna()
    # Acotar tasas extremas para que un mes atípico no dispare la proyección.
    growth = float(growth_rates.clip(-0.5, 0.5).mean())
    last_month = pd.Period(monthly.index[-1], freq="M")
    start = first_month if first_month is not None else last_month + 1
    projected = []
    value = float(series.iloc[-1])
    month = last_month
    # Puente silencioso hasta el mes previo al primero proyectado (cubre el
    # mes parcial excluido de la serie).
    while month + 1 < start:
        month += 1
        value = value * (1 + growth)
    for _ in range(3):
        month += 1
        value = value * (1 + growth)
        projected.append({"mes": str(month), "ingresos": round(max(value, 0.0), 2)})
    base = float(series.tail(3).sum())
    total_projected = sum(item["ingresos"] for item in projected)
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
    else:
        # Fase 12: transparencia — ninguna fila se pierde en silencio. Las
        # ventas sin fecha legible SÍ suman al total del periodo completo,
        # pero no pueden ubicarse en la evolución mensual ni en filtros por mes.
        sin_fecha = int((amounts_all.notna() & dates_all.isna()).sum())
        if sin_fecha:
            warnings.append(
                f"{sin_fecha} venta(s) no tienen fecha válida: se incluyen en los "
                "totales del periodo completo, pero no aparecen en la evolución "
                "mensual ni al filtrar por mes."
            )

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
            paired_all = amounts_all.notna() & costs_all.notna()
            frame["gastos"] = costs_all
            frame["utilidad"] = profits_all
            # Fase 12b §13: el margen MENSUAL debe usar el mismo denominador
            # pareado que el KPI global — el frontend calculaba utilidad/
            # ingresos del mes (con ventas sin costo en el denominador) y el
            # sparkline quedaba subestimado con cobertura parcial.
            frame["ingresos_pareados"] = amounts_all.where(paired_all)
            frame["_filas_con_ingreso"] = amounts_all.notna().astype(int)
            frame["_filas_pareadas"] = paired_all.astype(int)
        # Fase 12: solo se exige la fecha — una fila con costo legible pero
        # monto ilegible aportaba su gasto al KPI total y DESAPARECÍA del
        # gráfico mensual (el gráfico y el KPI no cuadraban).
        monthly = (
            frame.dropna(subset=["mes"]).groupby("mes").sum(numeric_only=True).sort_index()
        )

    # ── Parcialidad por mes (Fase 14) ──
    # Cada mes de la evolución declara hasta qué día tiene datos. El flag
    # `parcial` solo marca el ÚLTIMO mes de la serie (un hueco al final es
    # cobertura incompleta; un hueco al medio son días sin ventas reales).
    # Consumidores: la proyección lo excluye, Alertas no compara parcial vs
    # completo, la IA recibe la marca y el gráfico lo identifica.
    cobertura_dias: dict[str, int] = {}
    if has_dates and len(monthly):
        dias_frame = pd.DataFrame(
            {
                "mes": dates_all.map(lambda d: d.strftime("%Y-%m") if pd.notna(d) else None),
                "dia": dates_all.map(lambda d: int(d.day) if pd.notna(d) else None),
            }
        ).dropna(subset=["mes", "dia"])
        cobertura_dias = dias_frame.groupby("mes")["dia"].max().astype(int).to_dict()
    ultimo_mes = str(monthly.index[-1]) if len(monthly) else None

    def _mes_meta(mes: str) -> dict:
        dias_del_mes = int(pd.Period(mes).days_in_month)
        hasta = int(cobertura_dias.get(mes, dias_del_mes))
        return {
            "parcial": bool(mes == ultimo_mes and hasta < dias_del_mes),
            "cobertura_hasta_dia": hasta,
            "dias_del_mes": dias_del_mes,
        }

    def _month_extra(row) -> dict:
        if not has_costs:
            return {}
        ing_par = float(row.get("ingresos_pareados", 0.0) or 0.0)
        con_ingreso = int(row.get("_filas_con_ingreso", 0) or 0)
        pareadas = int(row.get("_filas_pareadas", 0) or 0)
        # Fase 13: un mes SIN filas pareadas no tiene utilidad conocida — la
        # suma de puros NaN daba 0.0 y "sin costos" se veía como "utilidad $0".
        if not pareadas:
            return {
                "gastos": round(float(row["gastos"]), 2),
                "utilidad": None,
                "margen_pareado_pct": None,
                "cobertura_costos_pct": 0.0 if con_ingreso else None,
            }
        utilidad_mes = float(row["utilidad"])
        return {
            "gastos": round(float(row["gastos"]), 2),
            "utilidad": round(utilidad_mes, 2),
            "margen_pareado_pct": (
                round(utilidad_mes / ing_par * 100, 1) if ing_par else None
            ),
            "cobertura_costos_pct": (
                round(pareadas / con_ingreso * 100, 1) if con_ingreso else None
            ),
        }

    evolucion = [
        {
            "mes": str(month),
            "ingresos": round(float(row["ingresos"]), 2),
            **_mes_meta(str(month)),
            **_month_extra(row),
        }
        for month, row in monthly.iterrows()
    ]

    if evolucion and evolucion[-1]["parcial"]:
        ult = evolucion[-1]
        # Fase 14b: el copy NO afirma una causa — el archivo no permite saber
        # si faltan datos, no hubo ventas o el periodo terminó a propósito.
        # Solo se declara el hecho (último registro) y la regla conservadora.
        warnings.append(
            f"El último registro disponible de {ult['mes']} corresponde al día "
            f"{ult['cobertura_hasta_dia']} de {ult['dias_del_mes']}. Para no "
            "comparar periodos con distinta cantidad de días registrados, este "
            "mes no se usa como mes completo: la proyección lo excluye y las "
            "alertas comparan meses completos."
        )

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
            # Fase 13 (P0.4): si el mes seleccionado está INCOMPLETO (el último
            # dato del archivo cae dentro de este mes antes de fin de mes), se
            # compara contra los DÍAS EQUIVALENTES del mes anterior — comparar
            # 15 días contra 30 mostraba caídas falsas.
            max_data = dates_all.max()
            prev_end_full = start - pd.Timedelta(days=1)
            prev_start = prev_end_full.replace(day=1)
            mes_parcial_sel = bool(
                pd.notna(max_data)
                and start <= max_data < month_end.normalize()
                and max_data.strftime("%Y-%m") == start.strftime("%Y-%m")
            )
            if mes_parcial_sel:
                eq_day = min(int(max_data.day), int(prev_end_full.day))
                prev_end = prev_start + pd.Timedelta(days=eq_day - 1)
                warnings.append(
                    f"El mes seleccionado está incompleto (datos hasta el "
                    f"{max_data.strftime('%d/%m/%Y')}): la variación se compara "
                    f"con los primeros {eq_day} días del mes anterior, no con el "
                    "mes completo."
                )
            else:
                prev_end = prev_end_full
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

    # ── Devoluciones/ajustes (Fase 12b §16) ──
    # Los montos negativos (reversas, notas de crédito) restan del total: los
    # "ingresos" son NETOS y el usuario debe verlo, no descubrirlo.
    negativos = amounts[amounts.notna() & (amounts < 0)]
    devoluciones = (
        {"monto": round(float(negativos.sum()), 2), "filas": int(len(negativos))}
        if len(negativos)
        else None
    )
    if devoluciones:
        warnings.append(
            f"Los ingresos mostrados son NETOS: incluyen {devoluciones['filas']} "
            f"monto(s) negativo(s) que restan {abs(devoluciones['monto']):,.0f} "
            "(devoluciones, reversas o ajustes).".replace(",", ".")
        )

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
        # Semántica honesta (Fase 12b §11): esto cuenta FILAS del archivo, no
        # ventas confirmadas — la UI lo rotula "Registros". Sin una clave de
        # transacción declarada no se puede afirmar más.
        "transacciones": int(len(selection)),
        "ticket_promedio": round(float(amounts.dropna().mean()), 2) if amounts.notna().any() else 0.0,
        # §12: el ticket se calcula sobre las filas CON monto — si difiere del
        # total de registros, la UI muestra la base de cálculo.
        "registros_con_monto": filas_con_ingreso,
    }
    if devoluciones:
        kpis["devoluciones"] = devoluciones
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
            # Fase 12: "monto" exige montos LEGIBLES, no solo texto en la
            # columna — si nada parsea, el frontend debe mostrar la guía de
            # mapeo, no un dashboard en $0.
            "monto": bool(amounts_all.notna().any()),
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
            "mes_parcial": bool(locals().get("mes_parcial_sel", False)),
            "meses_disponibles": [str(m) for m in monthly.index] if has_dates else [],
        },
        "kpis": kpis,
        "evolucion_mensual": evolucion,
    }

    group_costs = costs if has_costs else None
    if roles.get("categoria"):
        result["por_categoria"] = _group_sum(
            selection[roles["categoria"]], amounts, group_costs
        )
    canal_role = "canal" if roles.get("canal") else ("sucursal" if roles.get("sucursal") else None)
    result["agrupado_por_canal"] = canal_role
    if canal_role:
        # Fase 12: canal y producto también reciben utilidad/margen pareados
        # cuando hay costos — "qué canal/producto deja margen" es una de las
        # decisiones más citadas para una PyME.
        result["ventas_por_canal"] = _group_sum(
            selection[roles[canal_role]], amounts, group_costs
        )
    if roles.get("producto"):
        # Fase 12b §24: 12 productos — el Resumen muestra 5 y Explorar hasta
        # 8+; cortar en 5 dejaba a "Explorar" sin nada que explorar.
        result["top_productos"] = _group_sum(
            selection[roles["producto"]], amounts, group_costs
        )[:12]

    # ── Fase 12: clientes (unicidad y concentración) ──
    # Riesgo clásico de PyME: depender de un cliente. Solo con columna cliente.
    if roles.get("cliente"):
        clientes_raw = selection[roles["cliente"]]
        no_identificado = {"sin nombre", "sin identificar", "cliente desconocido", "no informa"}
        valid_mask = clientes_raw.map(
            lambda v: not is_missing(v)
            and strip_accents_lower(str(v).strip()) not in no_identificado
        )
        if valid_mask.any():
            top = _group_sum(clientes_raw[valid_mask], amounts[valid_mask], None)
            # Fase 12b §21: el % del cliente principal es sobre las ventas CON
            # cliente identificado — si la mitad de las ventas no tiene
            # cliente, ese % NO es sobre el total y la UI debe decirlo.
            # Fase 13 (P0.3): la cobertura se mide sobre ventas BRUTAS
            # positivas — con devoluciones, el neto daba coberturas >100% o
            # negativas, ambas sin sentido.
            brutos_total = float(amounts[amounts > 0].sum())
            brutos_ident = float(amounts[valid_mask & (amounts > 0)].sum())
            result["clientes"] = {
                "unicos": int(clientes_raw[valid_mask].nunique()),
                "top": top[:5],
                # Fase 14b: la concentración es una afirmación de DISTRIBUCIÓN
                # → usa la participación bruta (suma 100%), no el % neto.
                "concentracion_top_pct": (
                    (top[0].get("participacion_bruta_pct") or top[0]["porcentaje"])
                    if top
                    else None
                ),
                "cobertura_identificacion_pct": (
                    round(brutos_ident / brutos_total * 100, 1) if brutos_total else None
                ),
            }

    # ── Fase 12: ventas por día de la semana ──
    # Con qué días se concentra la venta se decide dotación y horarios.
    if has_dates:
        dias_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        sel_dates = dates_all[mask]
        wd = pd.DataFrame(
            {
                "dia": sel_dates.map(lambda d: d.weekday() if pd.notna(d) else None),
                "monto": amounts,
            }
        ).dropna(subset=["dia"])
        if not wd.empty:
            agg = wd.groupby("dia").agg(ingresos=("monto", "sum"), transacciones=("monto", "size"))
            result["por_dia_semana"] = [
                {
                    "dia": dias_semana[int(idx)],
                    "ingresos": round(float(row["ingresos"]), 2),
                    "transacciones": int(row["transacciones"]),
                }
                for idx, row in agg.sort_index().iterrows()
            ]

    # Fase 14: la proyección se calcula SOLO sobre meses completos — un mes
    # parcial al final deprimía la tasa de crecimiento con una caída ficticia.
    # Los meses proyectados siguen siendo los 3 POSTERIORES al final real de
    # la serie: la proyección nunca se superpone con un mes que tiene datos.
    monthly_completos = (
        monthly.iloc[:-1] if evolucion and evolucion[-1]["parcial"] else monthly
    )
    primer_mes_proyectado = (
        pd.Period(monthly.index[-1], freq="M") + 1 if len(monthly) else None
    )
    result["proyeccion"] = (
        _projection(monthly_completos, first_month=primer_mes_proyectado)
        if has_dates and not monthly_completos.empty
        else None
    )
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
