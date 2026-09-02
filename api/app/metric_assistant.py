"""Respuestas deterministas sobre los indicadores visibles del dashboard.

El asistente rapido no necesita un modelo para contestar cifras verificables.
Este modulo transforma el contrato ``MetricsResult`` en respuestas breves,
auditables y prudentes: nunca calcula un indicador que el motor no publico y
nunca mezcla monedas o confunde ventas con caja o utilidad.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


_CURRENCY_PREFIX = {
    "CLP": "$",
    "UF": "UF ",
    "USD": "US$",
    "EUR": "EUR ",
    "ARS": "ARS ",
    "PEN": "PEN ",
    "COP": "COP ",
    "MXN": "MXN ",
    "GBP": "GBP ",
}


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text).casefold())
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _es_number(value: Any, *, decimals: int = 2) -> str:
    parsed = _number(value)
    if parsed is None:
        return "N/D"
    places = 0 if parsed.is_integer() else decimals
    raw = f"{parsed:,.{places}f}"
    return raw.replace(",", "_").replace(".", ",").replace("_", ".")


def format_amount(value: Any, currency: str) -> str:
    code = str(currency or "CLP").upper()
    prefix = _CURRENCY_PREFIX.get(code, f"{code} ")
    decimals = 2 if code == "UF" else 0
    return f"{prefix}{_es_number(value, decimals=decimals)}"


def _percent(value: Any, *, decimals: int = 1) -> str:
    parsed = _number(value)
    if parsed is None:
        return "N/D"
    return f"{_es_number(parsed, decimals=decimals)}%"


def _kpi_value(value: Any) -> float | None:
    if isinstance(value, dict):
        return _number(value.get("valor"))
    return _number(value)


def _contains(text: str, *phrases: str) -> bool:
    return any(_normalize(phrase) in text for phrase in phrases)


def _period(metrics: dict[str, Any]) -> str:
    period = metrics.get("periodo") or {}
    since = period.get("desde")
    until = period.get("hasta")
    if since and until:
        return f" entre {since} y {until}"
    if since:
        return f" desde {since}"
    if until:
        return f" hasta {until}"
    return " en el periodo visible"


def _variation_sentence(kpi: Any) -> str:
    if not isinstance(kpi, dict):
        return "No hay un periodo anterior comparable en el indicador."
    variation = _number(kpi.get("variacion_pct"))
    if variation is None:
        return "No hay un periodo anterior comparable en el indicador."
    direction = "subio" if variation > 0 else "bajo" if variation < 0 else "no cambio"
    return f"Frente al periodo comparable {direction} {_percent(abs(variation))}."


def _partial_period_note(metrics: dict[str, Any]) -> str:
    period = metrics.get("periodo") or {}
    if not period.get("mes_parcial"):
        return ""
    return (
        " El ultimo mes tiene cobertura parcial, por lo que no conviene "
        "compararlo como si estuviera completo."
    )


def _currency_note(metrics: dict[str, Any]) -> str:
    currency = str(metrics.get("moneda") or "CLP").upper()
    if currency == "UF":
        return " La cifra esta expresada en UF y no fue convertida a pesos."
    if currency == "CLP":
        return " La cifra esta expresada en pesos chilenos."
    return f" La cifra esta expresada en {currency} y no fue convertida a CLP."


def _result(
    answer: str,
    key: str,
    suggestions: list[str],
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "answer": answer,
        "matched_key": key,
        "confidence": confidence,
        "suggestions": suggestions[:4],
    }


def metric_suggestions(metrics: dict[str, Any]) -> list[str]:
    collection = _collection_dashboard(metrics)
    if collection is not None:
        return [
            "¿Cuánto recaudo de cobranza y cuánto queda fuera?",
            "¿Qué equipo aporta más a la cobranza?",
            f"¿Cuál fue el mejor {collection.get('grano_temporal') or 'periodo'}?",
            "¿Qué problemas de calidad debo revisar?",
        ]
    kpis = metrics.get("kpis") or {}
    suggestions: list[str] = []
    if _kpi_value(kpis.get("ingresos_totales")) is not None:
        suggestions.append("¿Cuáles son mis ingresos totales?")
    if metrics.get("evolucion_mensual"):
        suggestions.append("¿Cuál fue mi mejor mes y qué tendencia hay?")
    if metrics.get("top_productos") or metrics.get("por_categoria"):
        suggestions.append("¿Qué producto o categoría lidera?")
    if kpis.get("ganancia_neta") or kpis.get("margen_utilidad_pct"):
        suggestions.append("¿Cuál es mi utilidad y margen?")
    suggestions.append("¿Qué conclusión general sacas de mis datos?")
    suggestions.append("¿Qué problemas de calidad debo revisar?")
    return list(dict.fromkeys(suggestions))[:4]


def _collection_dashboard(metrics: dict[str, Any]) -> dict[str, Any] | None:
    business = metrics.get("analisis_negocio") or {}
    collection = business.get("cobranza")
    if business.get("perfil") != "cobranza_nominal" or not isinstance(collection, dict):
        return None
    return collection


def _collection_scope(metrics: dict[str, Any], collection: dict[str, Any]) -> str:
    business = metrics.get("analisis_negocio") or {}
    applied = (business.get("filtros") or {}).get("aplicados") or {}
    if applied:
        labels = {
            "periodo_cotizado": "periodo cotizado",
            "equipo": "equipo",
            "subgrupo": "subgrupo",
            "agencia_pago": "agencia",
            "forma_pago": "forma de pago",
        }
        filters = ", ".join(
            f"{labels.get(str(key), str(key))}: {value}"
            for key, value in applied.items()
        )
        return f" con los filtros visibles ({filters})"
    period = collection.get("periodo") or {}
    since = period.get("desde")
    until = period.get("hasta")
    if since and until:
        return f" entre {since} y {until}"
    return " en el alcance visible"


def _collection_parent_rows(collection: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in (collection.get("equipos") or [])
        if isinstance(row, dict) and row.get("subgrupo") is None
    ]


def _collection_top(
    rows: list[dict[str, Any]],
    value_key: str,
) -> dict[str, Any] | None:
    candidates = [row for row in rows if _number(row.get(value_key)) is not None]
    return max(candidates, key=lambda row: float(row.get(value_key) or 0)) if candidates else None


def _collection_named_row(
    rows: list[dict[str, Any]],
    question: str,
    name_key: str,
) -> dict[str, Any] | None:
    haystack = f" {question} "
    return next(
        (
            row
            for row in rows
            if len(_normalize(row.get(name_key) or "")) >= 3
            and f" {_normalize(row.get(name_key) or '')} " in haystack
        ),
        None,
    )


def _collection_overview(
    metrics: dict[str, Any],
    collection: dict[str, Any],
) -> dict[str, Any]:
    kpis = collection.get("kpis") or {}
    currency = str(collection.get("moneda") or metrics.get("moneda") or "CLP")
    collected = _number(kpis.get("recaudacion_cobranza"))
    total = _number(kpis.get("recaudacion_total"))
    outside = _number(kpis.get("diferencia"))
    share = _number(kpis.get("participacion_cobranza_pct"))
    leader = _collection_top(_collection_parent_rows(collection), "recaudacion_cobranza")
    answer = (
        f"El dashboard de cobranza{_collection_scope(metrics, collection)} muestra "
        f"{format_amount(collected, currency)} de cobranza sobre "
        f"{format_amount(total, currency)} de recaudación total. "
    )
    if outside is not None and share is not None:
        answer += (
            f"Quedan {format_amount(outside, currency)} fuera de la condición Lote ≤ 300; "
            f"la cobertura de cobranza es {_percent(share, decimals=2)}. "
        )
    if leader is not None:
        answer += (
            f"El equipo líder es {leader.get('equipo')}, con "
            f"{format_amount(leader.get('recaudacion_cobranza'), currency)} "
            f"({_percent(leader.get('participacion_pct'), decimals=2)}). "
        )
    answer += (
        "Estas cifras describen recaudación, no ventas, utilidad ni rentabilidad. "
        "La prioridad es explicar el monto fuera de cobranza y validar los duplicados antes de eliminarlos."
    )
    return _result(answer, "metric_collection_overview", metric_suggestions(metrics))


def _answer_collection_question(
    metrics: dict[str, Any],
    collection: dict[str, Any],
    question: str,
) -> dict[str, Any] | None:
    kpis = collection.get("kpis") or {}
    currency = str(collection.get("moneda") or metrics.get("moneda") or "CLP")
    suggestions = metric_suggestions(metrics)
    scope = _collection_scope(metrics, collection)

    if _contains(
        question,
        "conclusion",
        "recomendacion",
        "como esta mi negocio",
        "resume mis datos",
        "que opinas",
        "analiza mi negocio",
        "que deberia hacer",
        "que muestran los graficos",
    ):
        return _collection_overview(metrics, collection)

    if _contains(question, "sin duplicados", "quitar duplicados", "eliminar duplicados"):
        duplicates = metrics.get("duplicados") or {}
        conserved = int(_number(duplicates.get("conservados")) or 0)
        answer = (
            f"El dashboard actual incluye {conserved} duplicados conservados. "
            "No puedo afirmar el nuevo total sin volver a procesar el archivo con eliminación confirmada: "
            "no existe un ID único de pago y dos filas iguales podrían representar operaciones reales distintas."
        )
        return _result(answer, "metric_collection_duplicates_what_if", suggestions)

    team_rows = _collection_parent_rows(collection)
    requested_team = _collection_named_row(team_rows, question, "equipo")
    if requested_team is not None or _contains(question, "equipo", "grupo"):
        row = requested_team or _collection_top(team_rows, "recaudacion_cobranza")
        if row is not None:
            subject = (
                f"El equipo consultado{scope}"
                if requested_team is not None
                else f"El equipo que más aporta a la cobranza{scope}"
            )
            answer = (
                f"{subject} es {row.get('equipo')}, "
                f"con {format_amount(row.get('recaudacion_cobranza'), currency)} "
                f"({_percent(row.get('participacion_pct'), decimals=2)} del total de cobranza)."
            )
            return _result(answer, "metric_collection_team", suggestions)

    agency_rows = [row for row in (collection.get("agencias") or []) if isinstance(row, dict)]
    requested_agency = _collection_named_row(agency_rows, question, "nombre")
    if requested_agency is not None or _contains(
        question, "agencia", "sucursal", "donde se recauda", "punto de pago"
    ):
        row = requested_agency or _collection_top(agency_rows, "valor")
        if row is not None:
            subject = "La agencia consultada" if requested_agency is not None else "La agencia líder"
            answer = (
                f"{subject}{scope} es {row.get('nombre')}, con "
                f"{format_amount(row.get('valor'), currency)} "
                f"({_percent(row.get('participacion_pct'), decimals=2)} de la cobranza identificada)."
            )
            return _result(answer, "metric_collection_agency", suggestions)

    payment_rows = [row for row in (collection.get("formas_pago") or []) if isinstance(row, dict)]
    requested_payment = _collection_named_row(payment_rows, question, "nombre")
    if requested_payment is not None or _contains(
        question, "forma de pago", "medio de pago", "como pagan", "metodo de pago"
    ):
        row = requested_payment or _collection_top(payment_rows, "valor")
        if row is not None:
            subject = (
                "La forma de pago consultada"
                if requested_payment is not None
                else "La principal forma de pago"
            )
            answer = (
                f"{subject}{scope} es {row.get('nombre')}, con "
                f"{format_amount(row.get('valor'), currency)} "
                f"({_percent(row.get('participacion_pct'), decimals=2)} de la cobranza identificada)."
            )
            return _result(answer, "metric_collection_payment_method", suggestions)

    wants_total = _contains(
        question,
        "ingresos totales",
        "recaudacion total",
        "total recaudado",
        "total de ingresos",
        "cuanto ingrese",
    )
    wants_collection = _contains(
        question,
        "recaudo de cobranza",
        "recaudacion de cobranza",
        "cobranza total",
        "cuanto recaudo",
        "cuanto cobre",
        "cobrado",
    )
    wants_difference = _contains(
        question,
        "diferencia",
        "queda fuera",
        "fuera de cobranza",
        "lote mayor",
        "lote > 300",
        "lote 300",
    )
    if wants_difference or (wants_total and wants_collection):
        collected = kpis.get("recaudacion_cobranza")
        total = kpis.get("recaudacion_total")
        outside = kpis.get("diferencia")
        answer = (
            f"La recaudación de cobranza{scope} es {format_amount(collected, currency)} "
            f"y la recaudación total es {format_amount(total, currency)}. "
            f"La diferencia fuera de Lote ≤ 300 es {format_amount(outside, currency)} "
            f"({_percent(kpis.get('diferencia_pct'), decimals=2)} del total); "
            f"{_percent(kpis.get('participacion_cobranza_pct'), decimals=2)} sí corresponde a cobranza."
        )
        return _result(answer, "metric_collection_difference", suggestions)
    if wants_total or _contains(question, "ingresos", "facturacion", "cuanto vendi"):
        answer = (
            f"La recaudación total{scope} es "
            f"{format_amount(kpis.get('recaudacion_total'), currency)}. "
            "En este archivo el indicador suma Valor Nominal de todos los lotes; "
            "no debe interpretarse como ventas, utilidad ni caja disponible."
        )
        return _result(answer, "metric_collection_total", suggestions)
    if (
        wants_collection or _contains(question, "recaudacion", "cobranza")
    ) and not _contains(
        question,
        "equipo",
        "agencia",
        "semana",
        "mes",
        "periodo",
        "ticket",
        "tendencia",
        "evolucion",
    ):
        answer = (
            f"La recaudación de cobranza{scope} es "
            f"{format_amount(kpis.get('recaudacion_cobranza'), currency)}. "
            f"Equivale a {_percent(kpis.get('participacion_cobranza_pct'), decimals=2)} de la recaudación total "
            "y aplica únicamente a registros con Lote ≤ 300."
        )
        return _result(answer, "metric_collection_collected", suggestions)

    if _contains(question, "ticket", "promedio por pago", "promedio cobranza"):
        answer = (
            f"El ticket promedio de cobranza{scope} es "
            f"{format_amount(kpis.get('ticket_promedio_cobranza'), currency)}. "
            f"Se calcula dividiendo la cobranza por {_es_number(kpis.get('registros_cobranza'))} "
            "registros con Lote ≤ 300; no representa utilidad."
        )
        return _result(answer, "metric_collection_ticket", suggestions)

    if _contains(
        question,
        "pagos en cero",
        "pagos estan en cero",
        "pagos con cero",
        "monto cero",
        "sin monto positivo",
    ):
        records = int(_number(kpis.get("registros")) or 0)
        positive = int(_number(kpis.get("pagos_positivos")) or 0)
        zero_or_non_positive = max(records - positive, 0)
        answer = (
            f"Hay {_es_number(zero_or_non_positive)} pagos sin Valor Nominal positivo{scope}. "
            "El dashboard no publica valores negativos en este KPI; revisa esas filas antes de tratarlas como pagos efectivos."
        )
        return _result(answer, "metric_collection_zero_payments", suggestions)

    if _contains(question, "pagos", "registros", "cuantas filas", "cuantos cobros"):
        answer = (
            f"Hay {_es_number(kpis.get('registros'))} pagos o filas{scope}; "
            f"{_es_number(kpis.get('pagos_positivos'))} tienen Valor Nominal positivo y "
            f"{_es_number(kpis.get('registros_cobranza'))} cumplen Lote ≤ 300. "
            "El conteo es de filas porque el archivo no contiene un ID único de pago."
        )
        return _result(answer, "metric_collection_payments", suggestions)

    if _contains(
        question,
        "mejor semana",
        "mayor semana",
        "semana con mayor",
        "mejor mes",
        "mejor periodo",
        "periodo con mayor",
        "pico",
        "evolucion",
        "tendencia",
        "peor semana",
        "menor semana",
        "semana con menor",
        "peor mes",
        "peor periodo",
        "periodo con menor",
    ):
        timeline = [row for row in (collection.get("evolucion") or []) if isinstance(row, dict)]
        key = "recaudacion_total" if _contains(question, "total") else "recaudacion_cobranza"
        wants_lowest = _contains(question, "peor", "menor")
        candidates = [row for row in timeline if _number(row.get(key)) is not None]
        selected = (
            min(candidates, key=lambda row: float(row.get(key) or 0))
            if wants_lowest and candidates
            else _collection_top(candidates, key)
        )
        if selected is not None:
            label = str(selected.get("periodo") or "periodo visible").replace("/", " a ")
            answer = (
                f"El {collection.get('grano_temporal') or 'periodo'} con {'menor' if wants_lowest else 'mayor'} "
                f"{'recaudación total' if key == 'recaudacion_total' else 'recaudación de cobranza'} "
                f"fue {label}, con {format_amount(selected.get(key), currency)}. "
                "Es un valor observado en el alcance filtrado, no una proyección."
            )
            return _result(
                answer,
                "metric_collection_worst_period" if wants_lowest else "metric_collection_best_period",
                suggestions,
            )

    if _contains(question, "periodo cotizado", "cotizacion", "mes cotizado"):
        rows = [
            row
            for row in (collection.get("periodos_cotizados") or [])
            if isinstance(row, dict)
        ]
        selected = _collection_top(rows, "valor")
        if selected is not None:
            answer = (
                f"Entre los periodos cotizados mostrados, el mayor aporte corresponde a "
                f"{selected.get('periodo')}, con {format_amount(selected.get('valor'), currency)} de cobranza. "
                "Esta serie puede limitarse a los últimos periodos visibles del gráfico."
            )
            return _result(answer, "metric_collection_quoted_period", suggestions)

    if _contains(question, "periodo anterior", "comparacion anterior", "versus anterior", "variacion"):
        comparison = collection.get("comparacion") or {}
        if not comparison.get("base_comparable"):
            answer = (
                "No hay una base anterior comparable con recaudación para el alcance visible. "
                "El dashboard evita fabricar una variación porcentual cuando el periodo anterior es cero."
            )
        else:
            answer = (
                f"La cobranza actual es {format_amount(comparison.get('recaudacion_actual'), currency)} "
                f"frente a {format_amount(comparison.get('recaudacion_anterior'), currency)} del periodo anterior: "
                f"una variación de {_percent(comparison.get('variacion_pct'))}."
            )
        return _result(answer, "metric_collection_comparison", suggestions)
    return None


def _answer_currency(metrics: dict[str, Any]) -> dict[str, Any]:
    currency = str(metrics.get("moneda") or "CLP").upper()
    if metrics.get("moneda_mixta") or metrics.get("datos_monetarios_disponibles") is False:
        detail = metrics.get("moneda_detalle") or {}
        detected = ", ".join(detail.get("detectadas") or []) or "mas de una moneda"
        answer = (
            f"El archivo contiene monedas incompatibles ({detected}). Por seguridad, "
            "ADS Veris no publica una suma monetaria hasta separarlas o declarar una "
            "conversion verificable. Los conteos no monetarios siguen disponibles."
        )
    elif currency == "UF":
        answer = (
            "La moneda detectada es UF. Todos los montos del dashboard y del bot deben "
            "leerse como UF; no se convierten a pesos chilenos de forma automatica."
        )
    elif currency == "CLP":
        answer = "La moneda detectada es CLP, es decir, pesos chilenos."
    else:
        answer = (
            f"La moneda detectada es {currency}. Los montos se mantienen en esa "
            "unidad y no se convierten automaticamente a CLP."
        )
    return _result(answer, "metric_currency", metric_suggestions(metrics))


def _answer_income(metrics: dict[str, Any]) -> dict[str, Any] | None:
    kpis = metrics.get("kpis") or {}
    income_kpi = kpis.get("ingresos_totales")
    income = _kpi_value(income_kpi)
    if income is None:
        return _result(
            "No hay un total de ingresos publicable para el alcance actual. Revisa que "
            "la columna de ventas este mapeada y que el archivo no mezcle monedas.",
            "metric_income_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    currency = str(metrics.get("moneda") or "CLP")
    answer = (
        f"Tus ingresos totales{_period(metrics)} son {format_amount(income, currency)}. "
        f"{_variation_sentence(income_kpi)}{_partial_period_note(metrics)}"
        f"{_currency_note(metrics)}"
    )
    if not kpis.get("ganancia_neta"):
        answer += (
            " Como no hay costos suficientes, este total no permite concluir cuanto "
            "ganaste ni cual fue la rentabilidad."
        )
    return _result(answer, "metric_income", metric_suggestions(metrics))


def _answer_expenses(metrics: dict[str, Any]) -> dict[str, Any]:
    kpis = metrics.get("kpis") or {}
    expenses_kpi = kpis.get("gastos_totales")
    expenses = _kpi_value(expenses_kpi)
    currency = str(metrics.get("moneda") or "CLP")
    if expenses is None:
        answer = (
            "No hay gastos o costos totales publicables en este alcance. Ventas no "
            "equivale a gasto: hace falta una columna o fuente de costos correctamente "
            "relacionada."
        )
    else:
        answer = (
            f"Los gastos o costos reconocidos{_period(metrics)} suman "
            f"{format_amount(expenses, currency)}. {_variation_sentence(expenses_kpi)}"
        )
        coverage = ((kpis.get("cobertura_costos") or {}).get("pct"))
        if _number(coverage) is not None and float(coverage) < 99.5:
            answer += (
                f" La cobertura de costos es {_percent(coverage)}, asi que utilidad y "
                "margen deben leerse como parciales."
            )
    return _result(answer, "metric_expenses", metric_suggestions(metrics))


def _answer_profit(metrics: dict[str, Any]) -> dict[str, Any]:
    kpis = metrics.get("kpis") or {}
    profit_kpi = kpis.get("ganancia_neta")
    profit = _kpi_value(profit_kpi)
    margin = _kpi_value(kpis.get("margen_utilidad_pct"))
    currency = str(metrics.get("moneda") or "CLP")
    if profit is None:
        return _result(
            "No puedo calcular una ganancia confiable con este alcance. Falta costo de "
            "venta atribuible o su cobertura es insuficiente; ingresos no equivale a "
            "utilidad.",
            "metric_profit_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    answer = f"La utilidad publicada es {format_amount(profit, currency)}"
    if margin is not None:
        answer += f", equivalente a un margen de {_percent(margin)}"
    answer += f"{_period(metrics)}. {_variation_sentence(profit_kpi)}"
    coverage = ((kpis.get("cobertura_costos") or {}).get("pct"))
    if _number(coverage) is not None and float(coverage) < 99.5:
        answer += (
            f" La cobertura de costos es {_percent(coverage)}; por eso la conclusion "
            "es parcial y no debe extrapolarse a las ventas sin costo conocido."
        )
    return _result(answer, "metric_profit", metric_suggestions(metrics))


def _answer_margin(metrics: dict[str, Any]) -> dict[str, Any]:
    kpis = metrics.get("kpis") or {}
    margin = _kpi_value(kpis.get("margen_utilidad_pct"))
    if margin is None:
        return _answer_profit(metrics)
    answer = (
        f"El margen publicado es {_percent(margin)}: por cada 100 unidades monetarias "
        f"de la base comparable quedan aproximadamente {_es_number(margin, decimals=1)} "
        "despues de los costos incluidos en ese calculo."
    )
    coverage = ((kpis.get("cobertura_costos") or {}).get("pct"))
    if _number(coverage) is not None:
        answer += f" La cobertura de costos es {_percent(coverage)}."
    answer += (
        " Para decidir si es bueno o malo, comparalo con tu meta, periodos anteriores "
        "y negocios equivalentes; un margen aislado no define por si solo la salud financiera."
    )
    return _result(answer, "metric_margin", metric_suggestions(metrics))


def _complete_months(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in (metrics.get("evolucion_mensual") or [])
        if _number(row.get("ingresos")) is not None and not row.get("parcial")
    ]


def _answer_trend(metrics: dict[str, Any], question: str) -> dict[str, Any]:
    months = _complete_months(metrics)
    if not months:
        return _result(
            "No hay suficientes meses completos para comparar una tendencia confiable.",
            "metric_trend_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    currency = str(metrics.get("moneda") or "CLP")
    best = max(months, key=lambda row: float(row.get("ingresos") or 0))
    worst = min(months, key=lambda row: float(row.get("ingresos") or 0))
    if _contains(question, "peor mes", "mes mas bajo", "menor mes"):
        answer = (
            f"El mes completo mas bajo fue {worst.get('mes')}, con "
            f"{format_amount(worst.get('ingresos'), currency)}."
        )
        key = "metric_worst_month"
    elif _contains(question, "mejor mes", "mes mas alto", "mayor mes"):
        answer = (
            f"El mejor mes completo fue {best.get('mes')}, con "
            f"{format_amount(best.get('ingresos'), currency)}."
        )
        key = "metric_best_month"
    else:
        answer = (
            f"Entre los meses completos, el mayor fue {best.get('mes')} "
            f"({format_amount(best.get('ingresos'), currency)}) y el menor "
            f"{worst.get('mes')} ({format_amount(worst.get('ingresos'), currency)})."
        )
        key = "metric_trend"
    projection = metrics.get("proyeccion") or {}
    growth = _number(projection.get("crecimiento_pct"))
    if growth is not None:
        answer += (
            f" La tendencia mecanica estimada es {_percent(growth)} mensual; es una "
            "extrapolacion, no un pronostico garantizado."
        )
    answer += _partial_period_note(metrics)
    return _result(answer, key, metric_suggestions(metrics))


def _group_answer(
    metrics: dict[str, Any],
    rows: list[dict[str, Any]],
    label: str,
    key: str,
) -> dict[str, Any]:
    if not rows:
        return _result(
            f"No hay un desglose confiable por {label.lower()} en el alcance actual.",
            f"{key}_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    row = rows[0]
    value = _number(row.get("ingresos") if "ingresos" in row else row.get("valor"))
    name = str(row.get("nombre") or "Sin nombre")
    currency = str(metrics.get("moneda") or "CLP")
    answer = f"El {label.lower()} lider es {name}"
    if value is not None:
        answer += f", con {format_amount(value, currency)}"
    share = _number(row.get("porcentaje") or row.get("participacion_pct"))
    if share is not None:
        answer += f" ({_percent(share)} del total identificado)"
    answer += ". Revisa tambien la concentracion: un lider fuerte puede ser una ventaja comercial o un riesgo de dependencia."
    return _result(answer, key, metric_suggestions(metrics))


def _answer_quality(metrics: dict[str, Any]) -> dict[str, Any]:
    quality = _number(metrics.get("calidad_datos"))
    warnings = [str(item) for item in (metrics.get("advertencias") or []) if str(item).strip()]
    if _collection_dashboard(metrics) is not None:
        warnings = [warning for warning in warnings if "maestra de clientes" not in warning.casefold()]
    duplicates = metrics.get("duplicados") or {}
    answer = (
        f"La calidad publicada es {_percent(quality)}. "
        if quality is not None
        else "No hay un porcentaje de calidad publicado. "
    )
    detected = int(_number(duplicates.get("detectados")) or 0)
    removed = int(_number(duplicates.get("eliminados")) or 0)
    conserved = int(_number(duplicates.get("conservados")) or max(detected - removed, 0))
    if detected:
        answer += f"Se detectaron {detected} duplicados: se eliminaron {removed} y se conservaron {conserved}. "
        if conserved:
            answer += "Los totales visibles sí incluyen los duplicados conservados. "
    if warnings:
        answer += "La principal cautela del motor es: " + warnings[0]
    else:
        answer += "El motor no publica advertencias adicionales para este alcance."
    if _collection_dashboard(metrics) is not None:
        answer += (
            " Como el archivo no contiene un ID único de pago, valida esos grupos con la fuente "
            "antes de confirmar una eliminación."
        )
    answer += " Una calidad alta reduce errores de formato, pero no reemplaza validar el mapeo y el significado contable de cada columna."
    return _result(answer, "metric_quality", metric_suggestions(metrics))


def _answer_weekday(metrics: dict[str, Any]) -> dict[str, Any] | None:
    rows = [
        row for row in (metrics.get("por_dia_semana") or [])
        if isinstance(row, dict) and _number(row.get("ingresos")) is not None
    ]
    if not rows:
        return None
    best = max(rows, key=lambda row: float(row.get("ingresos") or 0))
    return _result(
        f"El día de la semana con más ingresos es {best.get('dia')}, con "
        f"{format_amount(best.get('ingresos'), str(metrics.get('moneda') or 'CLP'))} "
        f"y {_es_number(best.get('transacciones'))} transacciones. Conviene revisar "
        "si se repite en varios periodos antes de ajustar dotación o promociones.",
        "metric_weekday",
        metric_suggestions(metrics),
    )


def _flexible_group_rows(metrics: dict[str, Any], question: str) -> tuple[str, list[dict[str, Any]]] | None:
    aliases = {
        "vendedor": ("vendedor", "ejecutivo", "asesor"),
        "fuente": ("fuente", "origen"),
        "subtipo": ("subtipo", "sub tipo", "tipo operacion"),
        "region": ("region",),
        "zona": ("zona",),
        "comuna": ("comuna",),
        "marca": ("marca",),
    }
    requested = next(
        (key for key, names in aliases.items() if _contains(question, *names)),
        None,
    )
    if requested is None:
        return None
    for grouping in metrics.get("agrupaciones_flexibles") or []:
        if not isinstance(grouping, dict):
            continue
        column = _normalize(grouping.get("columna") or "")
        if requested in column or any(_normalize(name) in column for name in aliases[requested]):
            rows = grouping.get("grupos_completos") or grouping.get("grupos") or []
            return str(grouping.get("columna") or requested.title()), rows
    matrix = metrics.get("matriz_mes_dimension") or {}
    if requested in _normalize(matrix.get("dimension") or ""):
        totals: dict[str, float] = {}
        for row in matrix.get("valores") or []:
            name = str(row.get("nombre") or "Sin nombre")
            totals[name] = totals.get(name, 0.0) + float(_number(row.get("ingresos")) or 0)
        rows = [
            {"nombre": name, "ingresos": value}
            for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]
        return str(matrix.get("columna") or requested.title()), rows
    return requested.title(), []


def _answer_inventory(metrics: dict[str, Any], question: str) -> dict[str, Any] | None:
    inventory = metrics.get("analisis_inventario") or {}
    if not inventory:
        return None
    currency = str(metrics.get("moneda") or "CLP")
    if _contains(question, "bajo minimo", "quiebre", "sin stock", "stock negativo"):
        answer = (
            f"Hay {_es_number(inventory.get('bajo_minimo'))} productos o registros bajo "
            f"el mínimo y {_es_number(inventory.get('stocks_negativos') or 0)} con stock negativo. "
            "Prioriza los que combinan quiebre, ventas recientes y mayor margen."
        )
        key = "metric_inventory_risk"
    elif _contains(question, "valor inventario", "cuanto vale"):
        value = _number(inventory.get("valor_inventario"))
        if value is None:
            answer = "No hay un valor de inventario publicable; falta costo de referencia con cobertura suficiente."
        else:
            answer = f"El valor de inventario publicado es {format_amount(value, currency)}. Revisa su concentración y antigüedad antes de tratarlo como liquidez."
        key = "metric_inventory_value"
    else:
        answer = (
            f"El inventario contiene {_es_number(inventory.get('stock_total'))} unidades en "
            f"{_es_number(inventory.get('productos'))} productos, con "
            f"{_es_number(inventory.get('bajo_minimo'))} bajo el mínimo."
        )
        key = "metric_inventory"
    return _result(answer, key, metric_suggestions(metrics))


def _answer_campaigns(metrics: dict[str, Any], question: str) -> dict[str, Any] | None:
    campaigns = metrics.get("analisis_campanas") or {}
    if not campaigns:
        return None
    currency = str(metrics.get("moneda") or "CLP")
    facts = [f"{_es_number(campaigns.get('campanas'))} campañas"]
    if _number(campaigns.get("inversion")) is not None:
        facts.append(f"inversión de {format_amount(campaigns.get('inversion'), currency)}")
    if _number(campaigns.get("ctr_pct")) is not None:
        facts.append(f"CTR de {_percent(campaigns.get('ctr_pct'))}")
    if _number(campaigns.get("cpc")) is not None:
        facts.append(f"CPC de {format_amount(campaigns.get('cpc'), currency)}")
    if _number(campaigns.get("tasa_conversion_pct")) is not None:
        facts.append(f"conversión de {_percent(campaigns.get('tasa_conversion_pct'))}")
    answer = "El alcance muestra " + ", ".join(facts) + "."
    answer += " Compara plataformas por conversión y costo, no solo por clics o impresiones."
    return _result(answer, "metric_campaigns", metric_suggestions(metrics))


def _answer_product_catalog(metrics: dict[str, Any], question: str) -> dict[str, Any] | None:
    products = metrics.get("analisis_productos") or {}
    if not products:
        return None
    currency = str(metrics.get("moneda") or "CLP")
    answer = f"El catálogo contiene {_es_number(products.get('productos'))} productos"
    average_cost = _number((products.get("costos") or {}).get("promedio"))
    average_price = _number((products.get("precios_lista") or {}).get("promedio"))
    average_margin = _number((products.get("margen_potencial") or {}).get("promedio"))
    if average_cost is not None:
        answer += f", costo promedio {format_amount(average_cost, currency)}"
    if average_price is not None:
        answer += f" y precio de lista promedio {format_amount(average_price, currency)}"
    if average_margin is not None:
        answer += f", con margen potencial promedio de {_percent(average_margin)}"
    answer += ". El margen potencial no reemplaza la utilidad realizada: aún depende de ventas, descuentos y gastos reales."
    return _result(answer, "metric_product_catalog", metric_suggestions(metrics))


def _ratio_candidates(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    business = metrics.get("analisis_negocio") or {}
    ratios = [row for row in (business.get("ratios") or []) if isinstance(row, dict)]
    items = (metrics.get("indicadores_financieros") or {}).get("items") or {}
    labels = {
        "liquidez_corriente": "Liquidez corriente",
        "prueba_acida": "Prueba acida",
        "rotacion_inventario": "Rotacion de inventario",
        "dias_cobro": "Dias de cobro",
        "dias_pago": "Dias de pago",
        "roa": "ROA",
        "roe": "ROE",
    }
    known = {str(row.get("id")) for row in ratios}
    for key, value in items.items():
        if key not in known:
            ratios.append(
                {
                    "id": key,
                    "nombre": labels.get(key, key.replace("_", " ").title()),
                    "valor": value,
                    "estado": "available" if value is not None else "unavailable",
                    "nota": "",
                }
            )
    return ratios


def _answer_ratio(metrics: dict[str, Any], question: str) -> dict[str, Any] | None:
    aliases = {
        "liquidez_corriente": ("liquidez", "razon corriente", "indice circulante", "solvencia corto plazo"),
        "prueba_acida": ("prueba acida", "test acido"),
        "rotacion_inventario": ("rotacion inventario", "rotacion de inventario"),
        "dias_cobro": ("dias cobro", "periodo de cobro", "cuanto tardo en cobrar"),
        "dias_pago": ("dias pago", "periodo de pago", "cuanto tardo en pagar"),
        "roa": ("roa", "rentabilidad de activos"),
        "roe": ("roe", "rentabilidad del patrimonio"),
        "margen_bruto": ("margen bruto",),
        "margen_operacional": ("margen operacional", "margen operativo"),
        "ebitda": ("ebitda",),
        "punto_equilibrio_ventas": ("punto de equilibrio",),
    }
    target = next(
        (key for key, names in aliases.items() if _contains(question, *names)), None
    )
    if target is None:
        return None
    ratio = next((row for row in _ratio_candidates(metrics) if row.get("id") == target), None)
    if ratio is None or _number(ratio.get("valor")) is None:
        required = ", ".join((ratio or {}).get("requiere") or [])
        suffix = f" Se requieren: {required}." if required else ""
        return _result(
            f"{(ratio or {}).get('nombre') or target.replace('_', ' ').title()} no esta disponible con las fuentes actuales.{suffix}",
            f"metric_ratio_{target}_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    value = float(ratio["valor"])
    currency = str(metrics.get("moneda") or "CLP")
    if target in {"margen_bruto", "margen_operacional", "roa", "roe"}:
        formatted = _percent(value)
    elif target in {"punto_equilibrio_ventas", "ebitda"}:
        formatted = format_amount(value, currency)
    elif target in {"dias_cobro", "dias_pago"}:
        formatted = f"{_es_number(value, decimals=1)} dias"
    else:
        formatted = f"{_es_number(value, decimals=2)} veces"
    answer = f"{ratio.get('nombre') or target}: {formatted}."
    note = str(ratio.get("nota") or "").strip()
    if note:
        answer += f" {note}"
    if target == "liquidez_corriente":
        answer += " Sobre 1 suele indicar cobertura contable de corto plazo, pero un exceso tambien puede reflejar recursos inmovilizados; compara con tu sector."
    elif target == "prueba_acida":
        answer += " Cerca o sobre 1 suele ser una referencia favorable, aunque debe contrastarse con vencimientos y calidad de las cuentas por cobrar."
    elif target == "rotacion_inventario":
        answer += " Una rotacion mayor suele implicar menos capital inmovilizado, pero debe compararse con quiebres de stock y el historial del negocio."
    return _result(answer, f"metric_ratio_{target}", metric_suggestions(metrics))


def _generic_numeric_answer(metrics: dict[str, Any], question: str) -> dict[str, Any] | None:
    generic = metrics.get("analisis_generico") or {}
    candidates = [row for row in (generic.get("numericas") or []) if isinstance(row, dict)]
    question_words = set(question.split()) - {"cuanto", "cual", "total", "promedio", "mis", "mi", "es", "de", "del"}
    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in candidates:
        label = _normalize(row.get("etiqueta") or row.get("columna") or "")
        words = set(label.split())
        score = len(question_words & words)
        if label and label in question:
            score += 4
        if score:
            ranked.append((score, row))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    row = ranked[0][1]
    wants_average = _contains(question, "promedio", "media")
    value = row.get("promedio") if wants_average else row.get("total")
    operation = "promedio" if wants_average else "total"
    if value is None and not wants_average:
        value = row.get(row.get("destacado") or "promedio")
        operation = str(row.get("destacado") or "promedio")
    if _number(value) is None:
        return None
    label = str(row.get("etiqueta") or row.get("columna") or "Indicador")
    fmt = row.get("formato")
    if fmt == "moneda":
        formatted = format_amount(value, str(metrics.get("moneda") or "CLP"))
    elif fmt == "porcentaje":
        formatted = _percent(value)
    else:
        formatted = _es_number(value)
    return _result(
        f"El {operation} de {label} es {formatted}. Este resultado usa los valores validos de la columna y no completa datos faltantes.",
        "metric_generic_numeric",
        metric_suggestions(metrics),
    )


def _answer_overview(metrics: dict[str, Any]) -> dict[str, Any]:
    kpis = metrics.get("kpis") or {}
    currency = str(metrics.get("moneda") or "CLP")
    income = _kpi_value(kpis.get("ingresos_totales"))
    profit = _kpi_value(kpis.get("ganancia_neta"))
    margin = _kpi_value(kpis.get("margen_utilidad_pct"))
    facts: list[str] = []
    if income is not None:
        facts.append(f"ingresos por {format_amount(income, currency)}")
    if profit is not None:
        facts.append(f"utilidad por {format_amount(profit, currency)}")
    if margin is not None:
        facts.append(f"margen de {_percent(margin)}")
    if not facts:
        return _result(
            "El alcance actual no contiene suficientes indicadores monetarios para una conclusion ejecutiva. Puedo revisar calidad, conteos y distribuciones disponibles.",
            "metric_overview_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    answer = f"En sintesis, el dashboard muestra {', '.join(facts)}{_period(metrics)}."
    months = _complete_months(metrics)
    if len(months) >= 2:
        first = _number(months[0].get("ingresos"))
        last = _number(months[-1].get("ingresos"))
        if first not in (None, 0) and last is not None:
            change = (last - first) / abs(first) * 100
            direction = "por encima" if change > 0 else "por debajo" if change < 0 else "al mismo nivel"
            answer += f" El ultimo mes completo esta {direction} del primero ({_percent(abs(change))})."
    if profit is None:
        answer += " No hay costos suficientes para concluir rentabilidad, EBITDA o caja a partir de esos ingresos."
    coverage = _number(((kpis.get("cobertura_costos") or {}).get("pct")))
    if coverage is not None and coverage < 99.5:
        answer += f" La cobertura de costos es {_percent(coverage)}, de modo que el margen es parcial."
    warnings = metrics.get("advertencias") or []
    if warnings:
        answer += f" Cautela principal: {warnings[0]}"
    answer += " La accion mas util es comparar el resultado con una meta y revisar los segmentos que explican la mayor parte del total."
    return _result(answer, "metric_overview", metric_suggestions(metrics))


def answer_metrics_question(
    message: str,
    metrics: dict[str, Any] | None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Devuelve una respuesta si la pregunta pide datos del negocio."""

    if not isinstance(metrics, dict) or not metrics:
        return None
    question = _normalize(message)
    if not question:
        return None

    definition_only = _contains(
        question,
        "que es",
        "como se calcula",
        "formula",
        "definicion",
    ) and not _contains(question, "mi ", "mis ", "tengo", "dio", "resultado")
    if definition_only:
        return None

    if _contains(question, "y eso", "eso es bueno", "es bueno", "que significa eso") and history:
        previous = next(
            (
                str(item.get("content") or "")
                for item in reversed(history)
                if item.get("role") == "user" and str(item.get("content") or "").strip()
            ),
            "",
        )
        question = f"{_normalize(previous)} {question}".strip()

    if _contains(question, "que puedo preguntar", "que sabes de mis datos", "preguntas disponibles"):
        suggestions = metric_suggestions(metrics)
        return _result(
            "Puedo responder cifras y conclusiones sobre los indicadores visibles: "
            + "; ".join(suggestions)
            + ". Si una fuente no existe, te dire que falta en vez de estimarla.",
            "metric_capabilities",
            suggestions,
        )
    if _contains(question, "moneda", "en pesos", "en uf", "son uf", "son pesos", "divisa"):
        return _answer_currency(metrics)
    collection = _collection_dashboard(metrics)
    if collection is not None:
        collection_answer = _answer_collection_question(metrics, collection, question)
        if collection_answer is not None:
            return collection_answer
    if _contains(question, "calidad", "datos sucios", "advertencias", "problemas de datos", "duplicados"):
        return _answer_quality(metrics)

    if _contains(question, "ingresos", "ventas totales", "venta total", "facturacion", "cuanto vendi"):
        return _answer_income(metrics)
    if _contains(question, "gastos", "costos totales", "costo total", "cuanto gaste"):
        return _answer_expenses(metrics)
    if _contains(question, "ganancia", "utilidad", "beneficio", "cuanto gane", "cuanto ganamos"):
        return _answer_profit(metrics)
    if _contains(question, "margen", "rentabilidad de venta"):
        return _answer_margin(metrics)

    ratio = _answer_ratio(metrics, question)
    if ratio is not None:
        return ratio
    if _contains(question, "ticket promedio", "venta promedio", "promedio por registro"):
        ticket = _number((metrics.get("kpis") or {}).get("ticket_promedio"))
        if ticket is not None:
            return _result(
                f"El ticket promedio es {format_amount(ticket, str(metrics.get('moneda') or 'CLP'))}. Se calcula solo sobre registros con monto valido; no representa utilidad ni caja.",
                "metric_ticket",
                metric_suggestions(metrics),
            )
    if _contains(question, "transacciones", "registros", "cuantas ventas", "numero de ventas"):
        transactions = _number((metrics.get("kpis") or {}).get("transacciones"))
        if transactions is not None:
            return _result(
                f"El alcance visible contiene {_es_number(transactions)} registros o transacciones incluidos en el indicador.",
                "metric_transactions",
                metric_suggestions(metrics),
            )
    if _contains(question, "unidades", "cantidad vendida"):
        units = _number((metrics.get("kpis") or {}).get("unidades_totales"))
        if units is not None:
            return _result(
                f"El total publicado es {_es_number(units)} unidades. No debe confundirse con el número de transacciones.",
                "metric_units",
                metric_suggestions(metrics),
            )
    if _contains(question, "devoluciones", "ventas negativas", "reversas"):
        returns = (metrics.get("kpis") or {}).get("devoluciones") or {}
        amount = _number(returns.get("monto"))
        rows = _number(returns.get("filas"))
        if amount is not None:
            return _result(
                f"Las devoluciones o reversas publicadas suman {format_amount(abs(amount), str(metrics.get('moneda') or 'CLP'))} en {_es_number(rows)} filas. Revisa producto, causa y recurrencia antes de atribuirlas a un único problema.",
                "metric_returns",
                metric_suggestions(metrics),
            )
    if _contains(question, "mejor mes", "peor mes", "tendencia", "evolucion", "crecimiento mensual"):
        return _answer_trend(metrics, question)
    if _contains(question, "dia de la semana", "que dia vendo", "mejor dia"):
        weekday = _answer_weekday(metrics)
        if weekday is not None:
            return weekday
    if _contains(question, "top producto", "mejor producto", "producto lider", "que producto"):
        return _group_answer(metrics, metrics.get("top_productos") or [], "Producto", "metric_top_product")
    if _contains(question, "categoria", "rubro lider"):
        return _group_answer(metrics, metrics.get("por_categoria") or [], "Categoria", "metric_top_category")
    if _contains(question, "canal", "sucursal", "donde vendo"):
        label = "Sucursal" if metrics.get("agrupado_por_canal") == "sucursal" else "Canal"
        return _group_answer(metrics, metrics.get("ventas_por_canal") or [], label, "metric_top_channel")
    if _contains(question, "cliente", "concentracion de clientes"):
        customers = metrics.get("clientes") or {}
        rows = customers.get("top") or []
        if rows:
            answer = _group_answer(metrics, rows, "Cliente", "metric_top_customer")
            unique = _number(customers.get("unicos"))
            concentration = _number(customers.get("concentracion_top_pct"))
            if unique is not None:
                answer["answer"] += f" Hay {_es_number(unique)} clientes unicos identificados."
            if concentration is not None:
                answer["answer"] += f" El grupo principal concentra {_percent(concentration)}."
            return answer

    flexible = _flexible_group_rows(metrics, question)
    if flexible is not None:
        label, rows = flexible
        return _group_answer(metrics, rows, label, "metric_flexible_group")

    if _contains(question, "inventario", "stock", "quiebre"):
        inventory = _answer_inventory(metrics, question)
        if inventory is not None:
            return inventory
    if _contains(question, "campana", "marketing", "ctr", "cpc", "impresiones", "conversion"):
        campaigns = _answer_campaigns(metrics, question)
        if campaigns is not None:
            return campaigns
    if metrics.get("tipo_analisis") == "catalogo_productos" and _contains(
        question, "catalogo", "productos", "precio lista", "costo promedio", "margen potencial"
    ):
        products = _answer_product_catalog(metrics, question)
        if products is not None:
            return products

    generic = _generic_numeric_answer(metrics, question)
    if generic is not None:
        return generic

    if _contains(
        question,
        "conclusion",
        "recomendacion",
        "como esta mi negocio",
        "resume mis datos",
        "que opinas",
        "analiza mi negocio",
        "que deberia hacer",
    ):
        inventory = _answer_inventory(metrics, question)
        if inventory is not None:
            return inventory
        campaigns = _answer_campaigns(metrics, question)
        if campaigns is not None:
            return campaigns
        products = _answer_product_catalog(metrics, question)
        if products is not None:
            return products
        return _answer_overview(metrics)
    return None
