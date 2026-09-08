"""Respuestas deterministas sobre los indicadores visibles del dashboard.

El asistente rapido no necesita un modelo para contestar cifras verificables.
Este modulo transforma el contrato ``MetricsResult`` en respuestas breves,
auditables y prudentes: nunca calcula un indicador que el motor no publico y
nunca mezcla monedas o confunde ventas con caja o utilidad.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .language_normalization import normalize_basic, normalize_query


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
    return normalize_basic(text)


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


def _previous_user_message(history: list[dict[str, Any]] | None) -> str:
    return next(
        (
            normalize_query(item.get("content") or "")
            for item in reversed(history or [])
            if item.get("role") == "user" and str(item.get("content") or "").strip()
        ),
        "",
    )


def _recent_conversation_text(
    history: list[dict[str, Any]] | None,
    limit: int = 4,
) -> str:
    contents = [
        normalize_query(item.get("content") or "")
        for item in (history or [])[-limit:]
        if str(item.get("content") or "").strip()
    ]
    return " ".join(content for content in contents if content)


def _with_conversation_context(
    question: str,
    history: list[dict[str, Any]] | None,
) -> str:
    previous = _previous_user_message(history)
    if not previous:
        return question
    if _contains(
        question,
        "corresponde a cobranza",
        "corresponde realmente a cobranza",
    ):
        return question
    if _contains(question, "que porcentaje es eso", "que porcentaje representa eso"):
        return "porcentaje corresponde a cobranza"
    if _contains(question, "y la peor", "y el peor"):
        grain = next(
            (value for value in ("semana", "mes", "periodo") if value in previous),
            "periodo",
        )
        return f"peor {grain}"
    if _contains(question, "y la mejor", "y el mejor"):
        grain = next(
            (value for value in ("semana", "mes", "periodo") if value in previous),
            "periodo",
        )
        return f"mejor {grain}"
    if _contains(question, "y stock") and _contains(previous, "equipo", "flujo", "stock"):
        return "equipo stock"
    if _contains(question, "y efectivo") and _contains(previous, "pago", "webpay", "efectivo"):
        return "forma de pago efectivo"
    if _contains(question, "y concepcion") and _contains(previous, "agencia", "web", "concepcion"):
        return "agencia concepcion"
    if _contains(question, "cual aporta menos") and (
        _contains(previous, "periodo", "cotizado")
        or any(month in previous for month in _SPANISH_MONTHS)
    ):
        return "periodo cotizado que aporta menos"
    if _contains(question, "comparalos", "comparalas", "compara ambos", "compara ambas"):
        recent = _recent_conversation_text(history)
        return f"{recent} {question}".strip()
    if _contains(question, "cuanto aporto"):
        recent = _recent_conversation_text(history, limit=1)
        return f"{recent} {question}".strip()
    explicit_topics = (
        "gastos",
        "costos",
        "ingresos",
        "ganancia",
        "utilidad",
        "margen",
        "moneda",
        "calidad",
        "duplicados",
    )
    if question.startswith("y ") and _contains(question, *explicit_topics):
        return question
    contextual_phrases = (
        "y eso",
        "eso es bueno",
        "que significa eso",
        "y la peor",
        "y la mejor",
        "y stock",
        "y efectivo",
        "y concepcion",
        "cuanto aporto",
        "quien va segundo",
        "cual aporta menos",
        "resumelo",
    )
    if question.startswith("y ") or _contains(question, *contextual_phrases):
        return f"{previous} {question}".strip()
    return question


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
        grain = str(collection.get("grano_temporal") or "periodo")
        period_suggestion = (
            "¿Cuál fue la semana con mayor recaudación?"
            if grain == "semana"
            else f"¿Cuál fue el {grain} con mayor recaudación?"
        )
        return [
            "¿Cuánto recaudo de cobranza y cuánto queda fuera?",
            "¿Qué equipo aporta más a la cobranza?",
            period_suggestion,
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


def _collection_named_rows(
    rows: list[dict[str, Any]],
    question: str,
    name_key: str,
) -> list[dict[str, Any]]:
    haystack = f" {question} "
    return [
        row
        for row in rows
        if len(_normalize(row.get(name_key) or "")) >= 3
        and f" {_normalize(row.get(name_key) or '')} " in haystack
    ]


def _ranked_rows(
    rows: list[dict[str, Any]], value_key: str
) -> list[dict[str, Any]]:
    return sorted(
        [row for row in rows if _number(row.get(value_key)) is not None],
        key=lambda row: float(row.get(value_key) or 0),
        reverse=True,
    )


def _collection_comparison_answer(
    rows: list[dict[str, Any]],
    question: str,
    *,
    name_key: str,
    value_key: str,
    dimension: str,
    currency: str,
    scope: str,
    suggestions: list[str],
) -> dict[str, Any] | None:
    ranked = _ranked_rows(rows, value_key)
    named = _collection_named_rows(ranked, question, name_key)
    wants_second = _contains(question, "segundo", "segunda")
    wants_top_two = _contains(
        question,
        "dos principales",
        "dos equipos principales",
        "dos agencias principales",
        "2 principales",
        "top 2",
        "dos mejores",
    )
    wants_comparison = _contains(
        question, "compara", "comparar", "versus", "vs", "cuanto mas", "diferencia"
    )
    wants_combined = _contains(question, "juntos", "sumados", "en conjunto")
    if wants_second and len(ranked) >= 2:
        row = ranked[1]
        answer = (
            f"El segundo {dimension}{scope} es {row.get(name_key)}, con "
            f"{format_amount(row.get(value_key), currency)} "
            f"({_percent(row.get('participacion_pct'), decimals=2)})."
        )
        return _result(answer, f"metric_collection_{dimension}_ranking", suggestions)
    if wants_top_two and len(ranked) >= 2:
        first, second = ranked[:2]
        answer = (
            f"Los dos {dimension}s principales{scope} son {first.get(name_key)} "
            f"con {format_amount(first.get(value_key), currency)} y {second.get(name_key)} "
            f"con {format_amount(second.get(value_key), currency)}."
        )
        return _result(answer, f"metric_collection_{dimension}_ranking", suggestions)
    if len(named) >= 2 and (wants_comparison or wants_combined):
        first, second = named[:2]
        first_value = float(first[value_key])
        second_value = float(second[value_key])
        combined = first_value + second_value
        if wants_combined:
            answer = (
                f"{first.get(name_key)} y {second.get(name_key)} suman "
                f"{format_amount(combined, currency)}{scope}."
            )
        else:
            leader, follower = (
                (first, second) if first_value >= second_value else (second, first)
            )
            difference = abs(first_value - second_value)
            answer = (
                f"{first.get(name_key)} aporta {format_amount(first_value, currency)} y "
                f"{second.get(name_key)} {format_amount(second_value, currency)}{scope}. "
                f"{leader.get(name_key)} supera a {follower.get(name_key)} por "
                f"{format_amount(difference, currency)}."
            )
        return _result(answer, f"metric_collection_{dimension}_comparison", suggestions)
    return None


_SPANISH_MONTHS = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


def _quoted_period_rows(
    rows: list[dict[str, Any]], question: str
) -> list[dict[str, Any]]:
    years = re.findall(r"\b20\d{2}\b", question)
    matches: list[dict[str, Any]] = []
    for row in rows:
        period = str(row.get("periodo") or "")
        normalized_period = _normalize(period)
        direct = normalized_period and normalized_period in question
        month_match = any(
            month in question and period.endswith(f"-{number}")
            for month, number in _SPANISH_MONTHS.items()
        )
        year_match = not years or any(period.startswith(year) for year in years)
        if direct or (month_match and year_match):
            matches.append(row)
    return matches


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

    if re.search(r"\b(?:filtra|aplica filtro|selecciona solo)\b", question):
        return _result(
            "No cambio los controles del dashboard desde el chat. Aplica el filtro en "
            "Resumen y vuelve a preguntarme: recibiré exactamente las métricas del "
            "alcance visible y mencionaré el filtro en la respuesta.",
            "metric_collection_filter_instruction",
            suggestions,
            "medium",
        )

    if _contains(
        question,
        "que filtros",
        "filtros activos",
        "alcance actual",
        "incluye todo",
        "incluyen todo",
    ):
        applied = ((metrics.get("analisis_negocio") or {}).get("filtros") or {}).get(
            "aplicados"
        ) or {}
        if applied:
            answer = (
                f"Los cálculos se realizaron{scope}. "
                "No incluyen las filas excluidas por esos filtros."
            )
        else:
            answer = (
                f"No hay filtros de negocio activos. Los cálculos usan todas las filas "
                f"válidas del archivo{scope}; las reglas del indicador aún excluyen lo "
                "que no cumple su definición, como cobranza fuera de Lote ≤ 300."
            )
        return _result(answer, "metric_collection_scope", suggestions)

    if _contains(question, "entre que fechas", "rango de fechas", "desde cuando", "hasta cuando"):
        period = collection.get("periodo") or {}
        since, until = period.get("desde"), period.get("hasta")
        answer = (
            f"El alcance visible va desde {since} hasta {until}."
            if since and until
            else "El dashboard no publica un rango de fechas completo para este alcance."
        )
        return _result(answer, "metric_collection_period", suggestions)

    if _contains(question, "agrupados por", "agrupado por", "grano temporal", "dia semana o mes"):
        grain = str(collection.get("grano_temporal") or "periodo")
        return _result(
            f"La evolución visible está agrupada por {grain}. Cada punto compara "
            "recaudación dentro de intervalos de ese mismo tamaño.",
            "metric_collection_grain",
            suggestions,
        )

    if _contains(question, "flujo de caja", "caja disponible"):
        return _result(
            "Este archivo permite analizar recaudación, pero no un flujo de caja "
            "completo. Para calcularlo faltan saldos iniciales y todas las entradas y "
            "salidas efectivas con sus fechas; la recaudación no equivale a caja disponible.",
            "metric_collection_cashflow_unavailable",
            suggestions,
            "medium",
        )

    if _contains(question, "mis costos", "tengo costos", "costos tengo", "cuanto cuestan", "gastos tengo"):
        return _result(
            "No hay costos ni gastos atribuibles publicados en este dashboard de "
            "cobranza. Por eso no puedo deducir utilidad, margen ni EBITDA a partir de "
            "la recaudación.",
            "metric_collection_costs_unavailable",
            suggestions,
            "medium",
        )

    if _contains(question, "puedo confiar", "son confiables", "confiar en estos numeros"):
        quality = _number(metrics.get("calidad_datos"))
        duplicates = int(_number((metrics.get("duplicados") or {}).get("conservados")) or 0)
        answer = (
            f"Las cifras son reproducibles para las reglas y filtros visibles y la calidad "
            f"publicada es {_percent(quality)}. Aun así, hay {duplicates} duplicados "
            "conservados: son aptas para análisis exploratorio, pero conviene validar "
            "esas repeticiones con la fuente antes de usarlas como cierre definitivo."
        )
        return _result(answer, "metric_collection_trust", suggestions)

    if _contains(question, "que no puedes concluir", "limitaciones", "que falta"):
        return _result(
            "Con este alcance no puedo concluir ventas, costos, utilidad, rentabilidad, "
            "EBITDA, liquidez ni flujo de caja. Sí puedo describir recaudación, cobertura "
            "de cobranza, periodos, equipos, agencias, formas de pago y calidad publicada.",
            "metric_collection_limitations",
            suggestions,
        )

    if _contains(question, "que grafico", "grafico deberia", "donde mirar primero"):
        return _result(
            "Mira primero la evolución por semana para detectar picos, después la brecha "
            "entre recaudación total y cobranza, y finalmente el aporte por equipo para "
            "ubicar dónde se concentra el resultado.",
            "metric_collection_chart_guidance",
            suggestions,
        )

    if _contains(question, "eso es bueno", "que significa eso"):
        share = _number(kpis.get("participacion_cobranza_pct"))
        outside = _number(kpis.get("diferencia"))
        return _result(
            f"La cobertura observada es {_percent(share, decimals=2)} y quedan "
            f"{format_amount(outside, currency)} fuera de la condición de cobranza. "
            "Sin una meta o un periodo comparable no sería riguroso llamarlo bueno o "
            "malo; úsalo como base y compáralo con el objetivo operativo.",
            "metric_collection_interpretation",
            suggestions,
        )

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
        "revisar primero",
        "tres recomendaciones",
        "3 recomendaciones",
        "mayor riesgo",
        "principal riesgo",
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
    team_comparison = _collection_comparison_answer(
        team_rows,
        question,
        name_key="equipo",
        value_key="recaudacion_cobranza",
        dimension="equipo",
        currency=currency,
        scope=scope,
        suggestions=suggestions,
    )
    if team_comparison is not None:
        return team_comparison
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
    if _contains(question, "sucursal") and not _contains(question, "agencia"):
        return _result(
            "El alcance actual no publica un desglose por sucursal. Agencia de pago y "
            "sucursal comercial no son equivalentes, así que no las reemplazo entre sí.",
            "metric_collection_branch_unavailable",
            suggestions,
            "medium",
        )
    agency_comparison = _collection_comparison_answer(
        agency_rows,
        question,
        name_key="nombre",
        value_key="valor",
        dimension="agencia",
        currency=currency,
        scope=scope,
        suggestions=suggestions,
    )
    if agency_comparison is not None:
        return agency_comparison
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
    payment_comparison = _collection_comparison_answer(
        payment_rows,
        question,
        name_key="nombre",
        value_key="valor",
        dimension="medio",
        currency=currency,
        scope=scope,
        suggestions=suggestions,
    )
    if payment_comparison is not None:
        return payment_comparison
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
        "cuanto recaude en total",
        "cuanto recaude total",
    )
    wants_collection = _contains(
        question,
        "recaudo de cobranza",
        "recaudacion de cobranza",
        "cobranza total",
        "cuanto recaudo",
        "cuanto cobre",
        "cobrado",
        "corresponde a cobranza",
        "corresponde realmente a cobranza",
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
        "subio",
        "bajo",
        "variacion",
        "anterior",
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
        "porcentaje en cero",
        "sin monto positivo",
        "porcentaje de pagos",
        "pagos esta en cero",
    ):
        records = int(_number(kpis.get("registros")) or 0)
        positive = int(_number(kpis.get("pagos_positivos")) or 0)
        zero_or_non_positive = max(records - positive, 0)
        zero_pct = zero_or_non_positive / records * 100 if records else None
        answer = (
            f"Hay {_es_number(zero_or_non_positive)} pagos sin Valor Nominal positivo{scope}. "
            f"Representan {_percent(zero_pct, decimals=2)} de las filas visibles. "
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
        "semana fue la mejor",
        "mayor semana",
        "semana con mayor",
        "mejor mes",
        "mejor periodo",
        "periodo con mayor",
        "pico",
        "evolucion",
        "tendencia",
        "peor semana",
        "semana fue la peor",
        "menor semana",
        "semana con menor",
        "peor mes",
        "peor periodo",
        "periodo con menor",
        "mejor que la peor",
    ):
        timeline = [row for row in (collection.get("evolucion") or []) if isinstance(row, dict)]
        key = "recaudacion_total" if _contains(question, "total") else "recaudacion_cobranza"
        candidates = [row for row in timeline if _number(row.get(key)) is not None]
        if candidates and _contains(question, "mejor") and _contains(question, "peor"):
            highest = _collection_top(candidates, key)
            lowest = min(candidates, key=lambda row: float(row.get(key) or 0))
            difference = float(highest[key]) - float(lowest[key])
            answer = (
                f"El mayor periodo fue {str(highest.get('periodo')).replace('/', ' a ')} "
                f"con {format_amount(highest.get(key), currency)} y el menor fue "
                f"{str(lowest.get('periodo')).replace('/', ' a ')} con "
                f"{format_amount(lowest.get(key), currency)}. La diferencia es "
                f"{format_amount(difference, currency)}."
            )
            return _result(answer, "metric_collection_period_comparison", suggestions)
        wants_lowest = _contains(question, "peor", "menor")
        selected = (
            min(candidates, key=lambda row: float(row.get(key) or 0))
            if wants_lowest and candidates
            else _collection_top(candidates, key)
        )
        if selected is not None:
            label = str(selected.get("periodo") or "periodo visible").replace("/", " a ")
            grain = str(collection.get("grano_temporal") or "periodo")
            article = "La" if grain == "semana" else "El"
            answer = (
                f"{article} {grain} con {'menor' if wants_lowest else 'mayor'} "
                f"{'recaudación total' if key == 'recaudacion_total' else 'recaudación de cobranza'} "
                f"fue {label}, con {format_amount(selected.get(key), currency)}. "
                "Es un valor observado en el alcance filtrado, no una proyección."
            )
            return _result(
                answer,
                "metric_collection_worst_period" if wants_lowest else "metric_collection_best_period",
                suggestions,
            )

    period_rows = [
        row
        for row in (collection.get("periodos_cotizados") or [])
        if isinstance(row, dict) and _number(row.get("valor")) is not None
    ]
    named_periods = _quoted_period_rows(period_rows, question)
    if named_periods or _contains(
        question,
        "periodo cotizado",
        "cotizacion",
        "mes cotizado",
        "marzo",
        "diciembre",
    ):
        wants_lowest = _contains(question, "menos", "menor", "peor")
        wants_compare = _contains(question, "compara", "versus", "vs", "diferencia")
        if len(named_periods) >= 2 and wants_compare:
            first, second = named_periods[:2]
            difference = abs(float(first["valor"]) - float(second["valor"]))
            answer = (
                f"{first.get('periodo')} aporta {format_amount(first.get('valor'), currency)} "
                f"y {second.get('periodo')} {format_amount(second.get('valor'), currency)}. "
                f"La diferencia es {format_amount(difference, currency)}."
            )
            return _result(answer, "metric_collection_quoted_period_comparison", suggestions)
        if len(named_periods) == 1:
            selected = named_periods[0]
        elif wants_lowest and period_rows:
            selected = min(period_rows, key=lambda row: float(row.get("valor") or 0))
        else:
            selected = _collection_top(period_rows, "valor")
        if selected is not None:
            qualifier = "menor" if wants_lowest and not named_periods else "consultado" if named_periods else "mayor"
            answer = (
                f"Entre los periodos cotizados mostrados, el aporte {qualifier} corresponde a "
                f"{selected.get('periodo')}, con {format_amount(selected.get('valor'), currency)} de cobranza. "
                "Esta serie puede limitarse a los últimos periodos visibles del gráfico."
            )
            return _result(answer, "metric_collection_quoted_period", suggestions)

    if _contains(
        question,
        "periodo anterior",
        "comparacion anterior",
        "versus anterior",
        "variacion",
        "subio o bajo",
        "subio",
        "bajo",
    ):
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
    if _contains(question, "peor mes", "mes mas bajo", "menor mes", "mes fue peor"):
        answer = (
            f"El mes completo mas bajo fue {worst.get('mes')}, con "
            f"{format_amount(worst.get('ingresos'), currency)}."
        )
        key = "metric_worst_month"
    elif _contains(question, "mejor mes", "mes mas alto", "mayor mes", "mes fue mejor"):
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
    question: str = "",
) -> dict[str, Any]:
    if not rows:
        return _result(
            f"No hay un desglose confiable por {label.lower()} en el alcance actual.",
            f"{key}_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    ranked = sorted(
        rows,
        key=lambda item: float(
            _number(item.get("ingresos") if "ingresos" in item else item.get("valor"))
            or 0
        ),
        reverse=True,
    )
    named = [
        row
        for row in ranked
        if _normalize(row.get("nombre") or "")
        and re.search(
            rf"\b{re.escape(_normalize(row.get('nombre') or ''))}\b", question
        )
    ]
    if len(named) >= 2 and _contains(
        question, "compara", "versus", "vs", "cuanto mas", "diferencia"
    ):
        first, second = named[:2]
        first_value = float(
            _number(first.get("ingresos") if "ingresos" in first else first.get("valor"))
            or 0
        )
        second_value = float(
            _number(second.get("ingresos") if "ingresos" in second else second.get("valor"))
            or 0
        )
        difference = abs(first_value - second_value)
        answer = (
            f"{first.get('nombre')} aporta {format_amount(first_value, str(metrics.get('moneda') or 'CLP'))} "
            f"y {second.get('nombre')} {format_amount(second_value, str(metrics.get('moneda') or 'CLP'))}. "
            f"La diferencia es {format_amount(difference, str(metrics.get('moneda') or 'CLP'))}."
        )
        return _result(answer, f"{key}_comparison", metric_suggestions(metrics))
    if _contains(question, "segundo", "segunda") and len(ranked) >= 2:
        row = ranked[1]
    elif named:
        row = named[0]
    elif _contains(question, "menos", "menor", "ultimo", "ultima"):
        row = ranked[-1]
    else:
        row = ranked[0]
    value = _number(row.get("ingresos") if "ingresos" in row else row.get("valor"))
    name = str(row.get("nombre") or "Sin nombre")
    currency = str(metrics.get("moneda") or "CLP")
    article = "La" if label.lower() in {"categoria", "categoría"} else "El"
    if _contains(question, "segundo", "segunda") and len(ranked) >= 2:
        position = "segunda" if article == "La" else "segundo"
    elif named:
        position = "consultada" if article == "La" else "consultado"
    elif _contains(question, "menos", "menor", "ultimo", "ultima"):
        position = "con menor ingreso"
    else:
        position = "líder"
    answer = f"{article} {label.lower()} {position} es {name}"
    if value is not None:
        answer += f", con {format_amount(value, currency)}"
    share = _number(row.get("participacion_bruta_pct"))
    share_base = "de las ventas brutas positivas"
    if share is None:
        share = _number(row.get("porcentaje") if row.get("porcentaje") is not None else row.get("participacion_pct"))
        share_base = "del total identificado"
    if share is not None:
        answer += f" ({_percent(share)} {share_base})"
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
    if _contains(question, "sucursal", "sucursales"):
        rows = inventory.get("por_sucursal") or []
        if rows:
            ranked = sorted(rows, key=lambda row: _number(row.get("stock")) or 0)
            row = ranked[0] if _contains(question, "menos", "menor") else ranked[-1]
            return _result(f"{row['nombre']} tiene {_es_number(row.get('stock'))} unidades de stock y {_es_number(row.get('bajo_minimo'))} registros bajo minimo en el corte visible.", "metric_inventory_branch", metric_suggestions(metrics))
    if _contains(question, "comprometidas", "comprometidos", "conteo"):
        field = "diferencia_conteo" if "conteo" in question else "unidades_comprometidas"
        value = _number(inventory.get(field))
        label = "diferencia de conteo" if field == "diferencia_conteo" else "unidades comprometidas"
        answer = f"El indicador de {label} es {_es_number(value)} unidades." if value is not None else f"No hay un indicador de {label} disponible."
        return _result(answer, f"metric_inventory_{field}", metric_suggestions(metrics))
    if _contains(question, "bajo minimo", "bajo el minimo", "quiebre", "sin stock", "stock negativo"):
        answer = (
            f"Hay {_es_number(inventory.get('bajo_minimo'))} registros bajo "
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
            f"{_es_number(inventory.get('bajo_minimo'))} registros bajo el mínimo. "
            "Un producto puede aparecer en varias sucursales."
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


def _generic_numeric_answer(metrics: dict[str, Any], question: str, context: str = "") -> dict[str, Any] | None:
    generic = metrics.get("analisis_generico") or {}
    candidates = [row for row in (generic.get("numericas") or []) if isinstance(row, dict)]
    stop = {"cuanto", "cuantas", "cual", "total", "promedio", "mediana", "maximo", "minimo", "mas", "alto", "bajo", "mis", "mi", "es", "de", "del", "el", "la", "y", "los", "las", "que", "es", "tengo"}
    question_words = set(question.split()) - stop
    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in candidates:
        label = _normalize(row.get("columna") or "")
        words = set(label.split())
        score = sum(4 if word in {"neto", "neta", "iva", "bruto", "bruta", "margen", "nuevos"} else 1 for word in question_words & words)
        if label and label in question:
            score += 4
        if score:
            ranked.append((score, row))
    if not ranked:
        if context and _contains(question, "maximo", "minimo", "mediana", "promedio", "media", "rango"):
            return _generic_numeric_answer(metrics, f"{context} {question}")
        subtype = generic.get("subtipo")
        if candidates and ((subtype == "gastos" and _contains(question, "gaste", "gastos", "gasto")) or (subtype == "compras" and _contains(question, "compre", "compras"))):
            ranked = [(1, candidates[0])]
        else:
            return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    row = ranked[0][1]
    operations = [(match.start(), name) for name, pattern in (
        ("maximo", r"\b(maximo|mas alto|mayor)\b"), ("minimo", r"\b(minimo|mas bajo|menor)\b"),
        ("mediana", r"\bmediana\b"), ("promedio", r"\b(promedio|media)\b"),
    ) for match in re.finditer(pattern, question)]
    operation = max(operations)[1] if operations else "total"
    value = row.get(operation)
    if value is None and not operations:
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
        f"{'La' if operation == 'mediana' else 'El'} {operation} de {label} es {formatted}. Este resultado usa los valores validos de la columna y no completa datos faltantes.",
        "metric_generic_numeric",
        metric_suggestions(metrics),
    )


def _answer_generic_profile(metrics: dict[str, Any], question: str, history: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    generic = metrics.get("analisis_generico") or {}
    if not generic:
        return None
    subtype = str(generic.get("subtipo") or "datos")
    currency = str(metrics.get("moneda") or "CLP")
    context = _previous_user_message(history)
    def formatted(value: Any, fmt: str | None) -> str:
        return format_amount(value, currency) if fmt == "moneda" else _percent(value) if fmt == "porcentaje" else _es_number(value)

    if _contains(question, "resumen", "conclusion", "panorama", "resumelo"):
        facts = []
        for row in (generic.get("numericas") or [])[:3]:
            operation = row.get("destacado") or "total"
            value = row.get(operation)
            if _number(value) is not None:
                facts.append(f"{operation} de {row['columna']}: {formatted(value, row.get('formato'))}")
        return _result(f"La hoja de {subtype} contiene {_es_number(generic.get('registros'))} registros. " + "; ".join(facts) + ". Los valores corresponden a esta hoja y sus filtros; metas, precios y limites de credito no son ingresos realizados.", "metric_generic_overview", metric_suggestions(metrics))
    if _contains(question, "cuantos clientes", "cuantos proveedores", "cuantas sucursales", "cuantos registros", "cuantos trabajadores"):
        return _result(f"La hoja de {subtype} contiene {_es_number(generic.get('registros'))} registros. Es un conteo de filas, no una garantia de entidades unicas; revisa duplicados e identificadores.", "metric_generic_count", metric_suggestions(metrics))

    for breakdown in generic.get("desgloses") or []:
        dimension_words = set(_normalize(breakdown.get("dimension") or "").split()) - {"de", "id", "gasto"}
        if dimension_words & set(question.split()) and _contains(question, "cuanto", "monto", "total", "gaste", "compra"):
            rows = breakdown.get("valores") or []
            if rows:
                description = "; ".join(f"{row['nombre']}: {formatted(row['valor'], breakdown.get('formato'))}" for row in rows[:5])
                return _result(f"{breakdown['operacion']} de {breakdown['columna']} por {breakdown['dimension']}: {description}. Se muestran los primeros {min(5, len(rows))} grupos; no son necesariamente el total de la hoja.", "metric_generic_breakdown", metric_suggestions(metrics))
    for distribution in generic.get("distribuciones") or []:
        words = set(_normalize(distribution.get("columna") or "").split()) - {"de", "id", "gasto"}
        if words & set(question.split()):
            rows = distribution.get("valores") or []
            if rows:
                row = max(rows, key=lambda item: item.get("registros", 0))
                return _result(f"En {distribution['columna']} predomina {row['nombre']}, con {_es_number(row['registros'])} registros. Esta distribucion cuenta filas, no montos.", "metric_generic_distribution", metric_suggestions(metrics))
    evolution = generic.get("evolucion") or {}
    if evolution.get("valores") and _contains(question, "mejor mes", "peor mes", "tendencia", "evolucion", "mes mas"):
        rows = sorted(evolution["valores"], key=lambda row: row["valor"])
        row = rows[0] if _contains(question, "peor", "menor", "menos") else rows[-1]
        return _result(f"El mes {'menor' if row is rows[0] else 'mayor'} en {evolution['columna']} es {row['mes']}: {formatted(row['valor'], evolution.get('formato'))}. Mayor gasto no significa mejor desempeno; compara periodos con cobertura equivalente.", "metric_generic_trend", metric_suggestions(metrics))
    return _generic_numeric_answer(metrics, question, context)


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
    original_question = normalize_query(message)
    if not original_question:
        return None
    if _contains(original_question, "gracias", "muchas gracias"):
        return _result(
            "De nada. Seguiré usando las cifras y filtros visibles, y te avisaré cuando "
            "falte una fuente en vez de completar el dato por mi cuenta.",
            "metric_conversation_thanks",
            metric_suggestions(metrics),
        )
    question = _with_conversation_context(original_question, history)

    definition_only = _contains(
        question,
        "que es",
        "como se calcula",
        "formula",
        "definicion",
    ) and not _contains(question, "mi ", "mis ", "tengo", "dio", "resultado")
    if definition_only:
        return None

    if _contains(
        original_question,
        "que puedo preguntar",
        "que sabes de mis datos",
        "preguntas disponibles",
        "que puedes hacer con este archivo",
        "que puedes hacer con mis datos",
    ):
        suggestions = metric_suggestions(metrics)
        return _result(
            "Puedo responder cifras y conclusiones sobre los indicadores visibles: "
            + "; ".join(suggestions)
            + ". Si una fuente no existe, te dire que falta en vez de estimarla.",
            "metric_capabilities",
            suggestions,
        )
    if _contains(
        original_question,
        "volver a filtrar",
        "vuelve a limpiar",
        "limpia todo al filtrar",
        "filtro vuelve a limpiar",
    ):
        return _result(
            "No. Los filtros del dashboard calculan sobre un artefacto limpio firmado "
            "y no vuelven a limpiar el Excel. La limpieza completa solo se repite si "
            "cambian el archivo, las reglas, el mapeo, la hoja o la decisión sobre "
            "duplicados; si la caché no coincide, el servidor la descarta para mantener "
            "la corrección.",
            "metric_filter_cache",
            metric_suggestions(metrics),
        )
    if _contains(
        original_question,
        "convertir a uf",
        "convertirlo a uf",
        "convertir estos pesos a uf",
        "convertir pesos a uf",
        "convierte a uf",
        "pasar a uf",
        "pasarlos a uf",
        "pasarlas a uf",
    ):
        return _result(
            "No convierto automáticamente a UF porque necesito el valor oficial de la "
            "UF correspondiente a la fecha de cada monto. El dashboard conserva la "
            "moneda detectada para evitar una conversión inventada o temporalmente incorrecta.",
            "metric_currency_conversion_unavailable",
            metric_suggestions(metrics),
            "medium",
        )
    if _contains(question, "moneda", "en pesos", "en uf", "son uf", "son pesos", "divisa", "esta en uf"):
        return _answer_currency(metrics)
    collection = _collection_dashboard(metrics)
    if collection is not None:
        if _contains(original_question, "resumelo", "en una frase"):
            return _collection_overview(metrics, collection)
        collection_answer = _answer_collection_question(metrics, collection, question)
        if collection_answer is not None:
            return collection_answer
    if _contains(question, "calidad", "datos sucios", "advertencias", "problemas de datos", "duplicados"):
        if _contains(question, "descargar", "exportar", "borrar", "eliminar") and _contains(question, "sin", "puedo"):
            return _result("Si. Puedes limpiar y descargar conservando los duplicados. Solo se eliminan repeticiones exactas del original cuando lo confirmas; los conflictos de ID y las coincidencias por normalizacion se conservan para revision.", "metric_download_duplicates", metric_suggestions(metrics))
        return _answer_quality(metrics)

    if _contains(original_question, "si los dejo", "si los conservo", "cambia el total") and _contains(_recent_conversation_text(history), "duplicados"):
        return _answer_quality(metrics)
    generic_answer = _answer_generic_profile(metrics, original_question, history)
    if generic_answer is not None:
        return generic_answer
    if metrics.get("analisis_inventario") and _contains(question, "inventario", "stock", "sucursal", "comprometidas", "conteo", "bajo el minimo", "resumen", "conclusion"):
        return _answer_inventory(metrics, question)

    if _contains(question, "ingresos", "ingreso total", "ventas totales", "venta total", "facturacion", "cuanto vendi"):
        return _answer_income(metrics)
    if _contains(question, "gastos", "mis costos", "costos totales", "costo total", "cuanto gaste"):
        return _answer_expenses(metrics)
    if _contains(question, "ganancia", "utilidad", "beneficio", "cuanto gane", "cuanto ganamos"):
        return _answer_profit(metrics)
    if _contains(question, "margen", "rentabilidad de venta"):
        return _answer_margin(metrics)
    if _contains(question, "cobertura de costos", "costos completos", "costos es completa"):
        coverage = _number(((metrics.get("kpis") or {}).get("cobertura_costos") or {}).get("pct"))
        if coverage is None:
            return _result(
                "No hay una cobertura de costos publicada para este alcance.",
                "metric_cost_coverage_unavailable",
                metric_suggestions(metrics),
                "medium",
            )
        qualifier = "completa" if coverage >= 99.5 else "parcial"
        return _result(
            f"La cobertura de costos es {_percent(coverage)} y se considera {qualifier}. "
            "Utilidad y margen solo usan filas con ingreso y costo comparables.",
            "metric_cost_coverage",
            metric_suggestions(metrics),
        )

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
    if _contains(
        question,
        "mejor mes",
        "mes fue mejor",
        "peor mes",
        "mes fue peor",
        "tendencia",
        "evolucion",
        "crecimiento mensual",
    ):
        return _answer_trend(metrics, question)
    if _contains(question, "dia de la semana", "que dia vendo", "mejor dia"):
        weekday = _answer_weekday(metrics)
        if weekday is not None:
            return weekday
    product_rows = metrics.get("top_productos") or []
    mentioned_products = [
        row
        for row in product_rows
        if _normalize(row.get("nombre") or "")
        and re.search(rf"\b{re.escape(_normalize(row.get('nombre') or ''))}\b", question)
    ]
    if _contains(question, "top producto", "mejor producto", "producto lider", "que producto") or len(mentioned_products) >= 2:
        return _group_answer(metrics, product_rows, "Producto", "metric_top_product", question)
    if _contains(question, "categoria", "rubro lider"):
        return _group_answer(metrics, metrics.get("por_categoria") or [], "Categoría", "metric_top_category", question)
    if _contains(question, "canal", "sucursal", "donde vendo"):
        label = "Sucursal" if metrics.get("agrupado_por_canal") == "sucursal" else "Canal"
        return _group_answer(metrics, metrics.get("ventas_por_canal") or [], label, "metric_top_channel", question)
    if _contains(question, "cliente", "concentracion de clientes"):
        customers = metrics.get("clientes") or {}
        rows = customers.get("top") or []
        unique = _number(customers.get("unicos"))
        if unique is not None and _contains(question, "cuantos", "cantidad", "numero de", "total de clientes"):
            return _result(
                f"Hay {_es_number(unique)} clientes unicos identificados en el alcance visible. "
                "El conteo usa los identificadores presentes; no equivale al numero de ventas.",
                "metric_customer_count", metric_suggestions(metrics),
            )
        if rows:
            answer = _group_answer(metrics, rows, "Cliente", "metric_top_customer", question)
            unique = _number(customers.get("unicos"))
            concentration = _number(customers.get("concentracion_top_pct"))
            if unique is not None:
                answer["answer"] += f" Hay {_es_number(unique)} clientes unicos identificados."
            if concentration is not None:
                answer["answer"] += f" El grupo principal concentra {_percent(concentration)}."
            return answer
        return _result(
            "No hay un conteo o desglose confiable de clientes en el alcance actual.",
            "metric_customers_unavailable",
            metric_suggestions(metrics),
            "medium",
        )

    flexible = _flexible_group_rows(metrics, question)
    if flexible is not None:
        label, rows = flexible
        return _group_answer(metrics, rows, label, "metric_flexible_group", question)

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

    if _contains(question, "puedo confiar", "son confiables", "confiar en esto"):
        return _answer_quality(metrics)

    if _contains(
        question,
        "que datos faltan",
        "que informacion falta",
        "que informacion me falta",
        "limitaciones",
    ):
        kpis = metrics.get("kpis") or {}
        gaps: list[str] = []
        coverage = _number((kpis.get("cobertura_costos") or {}).get("pct"))
        if coverage is None or coverage < 99.5:
            gaps.append("costos completos y atribuibles")
        if not (metrics.get("clientes") or {}).get("top"):
            gaps.append("clientes identificados")
        if not any(
            _number(row.get("valor")) is not None for row in _ratio_candidates(metrics)
        ):
            gaps.append("saldos de balance para liquidez, deuda, ROA y ROE")
        answer = (
            "Las principales brechas del alcance son: " + "; ".join(gaps) + "."
            if gaps
            else "No detecto una fuente esencial ausente entre los indicadores publicados."
        )
        return _result(
            answer,
            "metric_data_gaps",
            metric_suggestions(metrics),
            "medium" if gaps else "high",
        )

    if _contains(
        question,
        "conclusion",
        "recomendacion",
        "como esta mi negocio",
        "resume mis datos",
        "resumelo",
        "en una frase",
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
