"""Scoped questions over published aggregates, never an implicit new data query."""

import re

from .language_normalization import normalize_basic, normalize_query

MONTHS = {name: index for index, name in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}
MONTHS["setiembre"] = 9
_MONTH = re.compile(r"\b(" + "|".join(MONTHS) + r")\s*(?:(?:de|del)\s+)?((?:19|20)\d{2})?\b")
_PERIOD = re.compile(r"\b(?:" + "|".join(MONTHS) + r")(?:\s+(?:de\s+)?(?:19|20)\d{2})?\b|\b(?:19|20)\d{2}(?:[ /-](?:0[1-9]|1[0-2]))?\b")
_GLOBAL = re.compile(r"\b(?:total general|todo el archivo|todos los periodos|todas las sucursales|en general)\b")
_MEASURES = (
    (r"\b(?:ticket|promedio por venta)\b", "ticket promedio"),
    (r"\b(?:clientes|clientela)\b", "clientes"),
    (r"\b(?:unidades|cantidad vendida)\b", "unidades"),
    (r"\b(?:transacciones|registros|cuantas ventas)\b", "transacciones"),
    (r"\b(?:margen|rentabilidad|rentable)\b", "margen"),
    (r"\b(?:ganancia|utilidad|gane)\b", "ganancia"),
    (r"\b(?:costos?|gastos?|gaste|egresos)\b", "gastos"),
    (r"\biva\b", "iva"),
    (r"\b(?:ingresos|ventas|vendi|facturacion)\b", "ingresos"),
)


def _measure(question):
    return next((name for pattern, name in _MEASURES if re.search(pattern, question)), "")


def _normalize_scoped(message, metrics):
    literal = normalize_basic(message)
    replacements = {}
    names = {normalize_basic(row.get("nombre") or "")
             for _, rows in _dimensions(metrics) for row in rows}
    for name in sorted(names - {""}, key=len, reverse=True):
        token = f"zzentity{len(replacements)}zz"
        literal, count = re.subn(r"\b" + re.escape(name) + r"\b", token, literal)
        if count:
            replacements[token] = name
    normalized = normalize_query(literal)
    for token, name in replacements.items():
        normalized = normalized.replace(token, name)
    return normalized


def _scope_parts(question, metrics):
    periods = [match.group() for match in _PERIOD.finditer(question)]
    if periods:
        joiner = " hasta " if re.search(r"\b(?:entre|desde|hasta)\b", question) else " y "
        period = "en " + joiner.join(periods)
    else:
        period = ""
    segments = []
    for label, rows in _dimensions(metrics):
        for row in rows:
            name = normalize_basic(row.get("nombre") or "")
            if name and re.search(r"\b" + re.escape(name) + r"\b", question):
                segments.append("en " + normalize_basic(label) + " " + name)
    # Retain unknown filters too: a failed lookup must not turn into a global KPI.
    if not segments:
        unknown = re.search(r"\b(?:en|de) (?:la |el )?(?:sucursal|canal|categoria|producto|cliente)\s+.+", question)
        if unknown:
            segments.append(unknown.group())
    exclusion = re.search(r"\b(?:sin|excepto|excluyendo|solo)\s+.+", question)
    if exclusion:
        segments.append(exclusion.group())
    return period, " ".join(dict.fromkeys(segments))


def resolve_followup_scope(message, metrics, history):
    """Carry only explicit scopes through a bounded chain of user follow-ups."""
    previous = ""
    messages = [str(row.get("content") or "") for row in (history or [])[-12:]
                if row.get("role") == "user"] + [message]
    for current in messages:
        literal = normalize_basic(current)
        question = _normalize_scoped(current, metrics)
        if _GLOBAL.search(question):
            if not _measure(question) and _measure(previous):
                question += " " + _measure(previous)
            previous = question
            continue
        if question.startswith("y ") and previous:
            old_period, old_segment = _scope_parts(previous, metrics)
            period, segment = _scope_parts(question, metrics)
            if not period and old_period:
                question += " " + old_period
            if not segment and old_segment:
                question += " " + old_segment
            if (period or segment) and not _measure(question) and _measure(previous):
                question += " " + _measure(previous)
            if (period or segment) and re.search(r"\b(?:porcentaje|participacion|proporcion)\b", previous) and not _measure(literal):
                question += " porcentaje"
        previous = question
    # Known names are matched literally by the caller, never autocorrected.
    return previous if _normalize_scoped(message, metrics) != previous else message


def _monthly_series(metrics, question):
    generic = metrics.get("analisis_generico") or {}
    evolution = generic.get("evolucion") or {}
    if evolution.get("valores"):
        return (str(evolution.get("columna") or "valor"), "valor", evolution["valores"],
                evolution.get("formato"), evolution.get("operacion", "total"))
    return "ingresos", "ingresos", metrics.get("evolucion_mensual") or [], "moneda", "total"


def _dimensions(metrics):
    dimensions = [
        ("sucursal" if metrics.get("agrupado_por_canal") == "sucursal" else "canal", metrics.get("ventas_por_canal") or []),
        ("categoria", metrics.get("por_categoria") or []),
        ("producto", metrics.get("top_productos") or []),
        ("cliente", (metrics.get("clientes") or {}).get("top") or []),
    ]
    dimensions += [(str(group.get("columna") or ""), group.get("grupos") or [])
                   for group in metrics.get("agrupaciones_flexibles") or []]
    return dimensions


def answer_scoped_question(message, metrics, history):
    from .metric_assistant import _number, _result, _es_number, _percent, _group_answer, format_amount, metric_suggestions

    resolved = resolve_followup_scope(message, metrics, history)
    literal = normalize_basic(resolved)
    intent_text = literal
    for _, rows in _dimensions(metrics):
        for row in rows:
            name = normalize_basic(row.get("nombre") or "")
            if name:
                intent_text = re.sub(r"\b" + re.escape(name) + r"\b", "segmento", intent_text)
    question = normalize_query(intent_text)
    previous = next((str(row.get("content") or "") for row in reversed(history or []) if row.get("role") == "user"), "")
    result = lambda text, key, confidence="high", suggestions=None: _result(
        text, key, suggestions or metric_suggestions(metrics), confidence)
    if re.fullmatch(r"(?:el |en |de )?(?:19|20)\d{2}", literal) and _MONTH.search(normalize_basic(previous)):
        question = literal = f"{normalize_basic(previous)} {literal}"
    month_mentions = list(_MONTH.finditer(question))
    iso_mentions = list(re.finditer(r"\b((?:19|20)\d{2})[-/ ](0[1-9]|1[0-2])\b", literal))
    years = re.findall(r"\b(?:19|20)\d{2}\b", literal)
    if re.search(r"\b(?:[0-2]?\d|3[01]) (?:0?[1-9]|1[0-2]) (?:19|20)\d{2}\b", literal):
        return result("No tengo detalle diario para esa fecha en el contexto mensual. Filtra ese dia en Explorar; el total del archivo no es el total de ese dia.", "metric_daily_scope_unavailable", "medium")
    # Definitions and support about periods are not requests for a new subtotal.
    temporal = bool(month_mentions or iso_mentions or (years and re.search(r"\b(vendi|ventas|ingresos|gaste|gastos|compara|total|en)\b", question)))
    if re.search(r"\b(como|por que|porque)\b.*\b(filtro|filtrar|selecciono|seleccionar|importar|descargar)\b", question):
        return None
    relative_period = re.search(r"\b(hoy|ayer|trimestre|semestre|semana|mes pasado|mes anterior|ultimo mes|ultimos \d+ dias)\b", question)
    if relative_period and re.search(r"\b(vendi|ventas|ingresos|gastos|gaste|total)\b", question):
        return result("Ese periodo necesita un filtro explicito. Indica los meses o ajusta las fechas en Explorar: no sustituyo un dia, una semana o un trimestre por el total del archivo.", "metric_period_filter_needed", "medium")
    if re.search(r"\b(sin|excepto|excluyendo|excluir|solo)\b", question) and re.search(r"\b(vendi|ventas|ingresos|gastos|gaste|unidades|compara)\b", question):
        return result("Esa inclusion o exclusion necesita un filtro calculado sobre las filas. No tengo ese subtotal publicado y no lo deduzco de totales separados. Aplica el filtro en Explorar y vuelve a preguntar.", "metric_exclusion_unavailable", "medium")
    if temporal and literal.startswith("y "):
        previous_literal = normalize_basic(previous)
        if any(re.search(r"\b" + re.escape(normalize_basic(row.get("nombre"))) + r"\b", previous_literal)
               for _, rows in _dimensions(metrics) for row in rows if row.get("nombre")):
            return result("Si seguimos con el segmento anterior, no tengo publicado su cruce con ese mes. Aplica ambos filtros en Explorar, o pregunta explicitamente por el total general del mes.", "metric_cross_scope_unavailable", "medium")
    named_dimensions = []
    for label, rows in _dimensions(metrics):
        named = [row for row in rows if normalize_basic(row.get("nombre")) and
                 re.search(r"\b" + re.escape(normalize_basic(row.get("nombre"))) + r"\b", literal)]
        explicit = re.search(r"\b" + re.escape(normalize_basic(label)) + r"s?\b", question)
        if named or explicit:
            named_dimensions.append((label, rows, named, bool(explicit)))
    chosen = next((entry for entry in named_dimensions if entry[3]), None)
    if chosen is None and len(named_dimensions) == 1:
        chosen = named_dimensions[0]
    distinct_names = {normalize_basic(row.get("nombre")) for entry in named_dimensions for row in entry[2]}
    different_segments = len(distinct_names) > 1 and sum(bool(entry[2]) for entry in named_dimensions) > 1
    if (temporal and named_dimensions) or sum(entry[3] for entry in named_dimensions) > 1 or different_segments:
        return result("No tengo publicado el cruce entre ese segmento y ese periodo. Sus totales separados no permiten deducir la interseccion. Aplica ambos filtros en Explorar y vuelve a preguntar con ese alcance.", "metric_cross_scope_unavailable", "medium")
    if len(named_dimensions) > 1 and sum(bool(entry[2]) for entry in named_dimensions) > 1 and not chosen:
        return result("El nombre aparece en varias dimensiones. Indica si te refieres a " + ", ".join(entry[0] for entry in named_dimensions) + ".", "metric_dimension_ambiguous", "medium")
    if _GLOBAL.search(question) and not temporal and not named_dimensions:
        measure = _measure(question)
        if measure:
            from .metric_assistant import answer_metrics_question
            return answer_metrics_question(measure, metrics)
    if temporal:
        label, value_key, source, value_format, operation = _monthly_series(metrics, question)
        if metrics.get("moneda_mixta") and value_format == "moneda":
            return result("No comparo ni sumo importes de monedas mezcladas. Filtra una moneda o aporta el tipo de cambio y su fecha antes de calcular.", "metric_mixed_scope_unavailable", "medium")
        requested_measures = set(question.split()) & {"neto", "neta", "iva", "bruto", "bruta", "utilidad", "ganancia", "margen", "costo", "costos", "unidades", "clientes", "ticket", "transacciones"}
        label_words = set(normalize_basic(label).split())
        semantic_measure = _measure(question)
        if semantic_measure in {"ganancia", "margen", "ticket promedio", "transacciones", "unidades", "clientes"}:
            requested_measures.update(semantic_measure.split())
        if re.search(r"\b(gaste|gastos|egresos)\b", question) and not label_words & {"gastos", "gasto", "egresos", "egreso"}:
            requested_measures.add("gastos")
        if re.search(r"\b(vendi|ventas|ingresos)\b", question) and label_words & {"gastos", "gasto", "egresos", "egreso"}:
            requested_measures.add("ingresos")
        if requested_measures - label_words:
            return result(f"No tengo publicada esa medida por mes. La serie disponible corresponde a {label}, y no la usare como sustituto. Selecciona la medida en Explorar o revisa si falta su fuente.", "metric_month_measure_unavailable", "medium")
        rows = {str(row.get("mes")): row for row in source if _number(row.get(value_key)) is not None}
        if re.search(r"\b(?:el|dia)\s+\d{1,2}\s+(?:de\s+)?(?:" + "|".join(MONTHS) + r")\b", question) or re.search(r"\b(?:19|20)\d{2} \d{2} \d{2}\b", literal):
            return result("No tengo el detalle diario de esa fecha en este contexto mensual. Selecciona ese dia en los filtros de Explorar; no usare el total del mes como si fuera el del dia.", "metric_daily_scope_unavailable", "medium")
        requests = []
        for mention in month_mentions:
            month = MONTHS[mention.group(1)]
            year = mention.group(2) or (years[-1] if len(set(years)) == 1 else None)
            candidates = [key for key in rows if key.endswith(f"-{month:02d}") and (not year or key.startswith(year))]
            if len(candidates) > 1:
                return result("Hay varios periodos para ese mes: " + ", ".join(sorted(candidates)) + ". ¿Cual quieres consultar?", "metric_period_ambiguous", "medium", sorted(candidates))
            requests.append(candidates[0] if candidates else (f"{year}-{month:02d}" if year else mention.group(1)))
        requests += [f"{mention.group(1)}-{mention.group(2)}" for mention in iso_mentions]
        requests = list(dict.fromkeys(requests))
        if not requests and years:
            requests = sorted(key for key in rows if key[:4] in years)
            if not requests:
                return result("No hay datos mensuales publicados para " + ", ".join(years) + " en el alcance visible. Cambia de hoja o periodo; no equivalen a cero.", "metric_period_unavailable", "medium")
        missing = [period for period in requests if period not in rows]
        if missing or not requests:
            return result("No hay un valor publicado para " + ", ".join(missing or ["ese periodo"]) + ". No significa cero. Revisa el alcance y la cobertura de fechas.", "metric_period_unavailable", "medium")
        values = [float(rows[period][value_key]) for period in requests]
        fmt = (lambda value: format_amount(value, str(metrics.get("moneda") or "CLP"))) if value_format == "moneda" else _percent if value_format == "porcentaje" else _es_number
        partial = any(rows[period].get("parcial") for period in requests)
        note = " Hay cobertura parcial; la comparacion no representa periodos completos equivalentes." if partial else ""
        if len(requests) == 1 and re.search(r"\b(?:porcentaje|participacion|proporcion)\b", question):
            denominator = sum(float(row[value_key]) for row in rows.values())
            if operation != "total" or denominator <= 0 or any(float(row[value_key]) < 0 for row in rows.values()):
                return result("No hay una base aditiva positiva para calcular esa participacion. Los promedios o importes con signos mezclados no representan partes de un total de ventas positivas.", "metric_month_share_unavailable", "medium")
            return result(f"{requests[0]} aporta {_percent(values[0] / denominator * 100)}: {fmt(values[0])} / {fmt(denominator)}. El denominador suma los {len(rows)} meses publicados ({', '.join(sorted(rows))}); no incluye meses ausentes." + note,
                          "metric_month_share", "medium" if partial else "high")
        if len(requests) == 2 and re.search(r"\b(compara|comparar|versus|vs|diferencia|crecio|crecieron|cambio|subio|bajo)\b", question):
            first, last = values
            change = last - first
            comparison = (f" El cambio es {fmt(change)} ({_percent(change / abs(first) * 100)} respecto al primero)."
                          if first != 0 else f" El cambio es {fmt(change)}; la variacion porcentual no esta definida con una base de cero.")
            return result(f"{label.title()}: {requests[0]} = {fmt(first)}; {requests[1]} = {fmt(last)}." + comparison + note,
                          "metric_month_comparison", "medium" if partial else "high")
        if len(requests) > 1:
            if re.search(r"\b(entre|desde|hasta)\b", question) and len(requests) == 2:
                start, end = sorted(requests)
                requests = sorted(period for period in rows if start <= period <= end)
                values = [float(rows[period][value_key]) for period in requests]
                if any(rows[period].get("parcial") for period in requests):
                    note = " Hay cobertura parcial; la comparacion no representa periodos completos equivalentes."
            if operation != "total":
                return result("La serie publica promedios por mes. No los sumo ni calculo un promedio global sin sus cantidades: " + "; ".join(f"{period}: {fmt(value)}" for period, value in zip(requests, values)) + note, "metric_month_values", "medium")
            return result(f"El total disponible de {label} es {fmt(sum(values))} en {len(requests)} meses publicados ({', '.join(requests)}). No presupone cobertura de meses ausentes." + note, "metric_month_total")
        return result(f"En {requests[0]}, {label} = {fmt(values[0])}. Es el valor del periodo publicado, no el total de todo el archivo." + note,
                      "metric_month_value", "medium" if partial else "high")
    if chosen:
        label, rows, named, explicit = chosen
        money_question = re.search(r"\b(vendi|ventas|ingresos|ingreso|aporta|aportan|compara|versus|vs)\b", question)
        if named and re.search(r"\b(unidades|margen|utilidad|ganancia|neto|neta|iva|costos|gastos|clientes|ticket|transacciones)\b", question):
            return result("El desglose disponible de ese segmento es de ingresos, no de la medida que pides. No sustituire unidades, costos o margen por un importe de ventas. Selecciona la medida y el filtro en Explorar.", "metric_group_measure_unavailable", "medium")
        if named and (money_question or literal.startswith("y ")):
            if metrics.get("moneda_mixta"):
                return result("No comparo importes de monedas mezcladas; selecciona una moneda antes de interpretar el desglose.", "metric_mixed_scope_unavailable", "medium")
            key = {"producto": "metric_top_product", "cliente": "metric_top_customer",
                   "categoria": "metric_top_category", "canal": "metric_top_channel",
                   "sucursal": "metric_top_channel"}.get(label, "metric_flexible_group")
            return _group_answer(metrics, rows, label, key, literal)
        unknown = re.search(r"\b(?:en (?:la |el )?|de (?:la |el )?|el |la |del )" + re.escape(normalize_basic(label)) + r"\s+(.+)$", literal)
        if explicit and not named and unknown and money_question:
            return result(f"No encuentro {unknown.group(1).title()} en el desglose publicado de {label}. Puede faltar en el top visible o estar fuera del filtro; no lo interpreto como cero ni uso el total general.", "metric_named_group_unavailable", "medium")
    if re.search(r"\b(?:vendi|ventas|ingresos)\s+(?:en|para|con)\s+", question):
        return result("No reconozco ese filtro en los desgloses publicados. Indica la dimension y el valor exacto, o seleccionalos en Explorar. No usare el total general como si correspondiera a ese segmento.", "metric_filter_unavailable", "medium")
    return None
