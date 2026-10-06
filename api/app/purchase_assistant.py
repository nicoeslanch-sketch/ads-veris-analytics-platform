"""Answer purchase questions from published indicator contracts."""

import re
from typing import Any

from .language_normalization import normalize_query


_TOPIC = re.compile(r"\b(?:compras?|compre|compramos|comprad[oa]s?|fletes?)\b")
_OTHER_TOPIC = re.compile(r"\b(?:vendi|ingresos|gastos|clientes|inventario|stock|plan|coins|limpieza|descargar|margen|utilidad|cxc|cobrar|deben)\b")
_FOLLOWUP = re.compile(r"^(?:y |ahora |entonces |eso |esos )")
_MEASURE_FOLLOWUP = re.compile(r"\b(?:total|importe|monto|cobertura|parcial|pagado|pagados|pague|dinero|caja|promedio|mediana|porcentaje|cuantos|cuantas)\b")


def _context(question: str, history: list[dict[str, Any]] | None) -> list[str]:
    from .assistant_queries import MONTHS

    context: list[str] = []
    for item in [*(history or [])[-12:], {'role': 'user', 'content': question}]:
        if item.get('role') != 'user':
            continue
        text = normalize_query(item.get('content') or '')
        reset = bool(re.search(r'\b(?:en general|total general)\b', text))
        period_followup = re.search(r'\b(?:' + '|'.join(MONTHS) + r'|20\d{2}|hoy|ayer|mes|semana|trimestre)\b', text)
        if (context and _FOLLOWUP.search(text) and not reset and not _OTHER_TOPIC.search(text)
                and (_TOPIC.search(text) or _MEASURE_FOLLOWUP.search(text)
                     or period_followup or re.match(r'^y en\s+', text))):
            context.append(text)
        else:
            context = [text] if _TOPIC.search(text) else []
    return context


def answer_purchases(question: str, metrics: dict[str, Any], history=None) -> dict[str, Any] | None:
    from .assistant_queries import MONTHS, _dimensions
    from .metric_assistant import _number, _percent, _result, format_amount

    business = metrics.get('analisis_negocio')
    if not isinstance(business, dict):
        return None
    context = _context(question, history)
    if not context or re.search(
        r'\b(?:plan|coins|creditos|suscripcion|deberia|conviene|recomiendas|comprar|'
        r'descargar|descargo|exportar|limpiar|estandarizar|que son|que es)\b', question,
    ):
        return None
    suggestions = ['Mis compras netas', 'Fletes de compra', 'Calidad de los datos']
    if re.search(r'\b(?:eso|esos|equivale|significa|son|es)\b', question) and re.search(
        r'\b(?:pagado|pagados|pague|dinero|caja)\b', question,
    ):
        return _result(
            'El importe de compras registra adquisiciones. Para saber cuanto dinero salio '
            'hay que conciliar los pagos, sus fechas y documentos; puede haber compras a '
            'credito o pagos de otro periodo. No deduzco caja pagada del total de compras.',
            'metric_purchases_not_cash', suggestions, 'medium',
        )
    if re.search(
        r'\b(?:cuantas|cuantos|numero|conteo|unidades|proveedores|promedio|mediana|'
        r'maximo|minimo|mayor|menor|brutas?|iva|impuesto|pagadas?|pagados?|'
        r'porcentaje|proporcion|participacion|compara|comparar|tendencia)\b', question,
    ):
        return _result(
            'Esa medida de compras no esta publicada en esta vista. El importe neto '
            'no sustituye cantidades, proveedores unicos, promedios, IVA ni pagos. '
            'Revisa la fuente y el desglose en Explorar.',
            'metric_purchases_measure_unavailable', suggestions, 'medium',
        )
    scope_pattern = (
        r'\b(?:' + '|'.join(MONTHS) + r'|\d+|hoy|ayer|mes|meses|semana|trimestre|'
        r'semestre|solo|excepto|sin|entre|desde|hasta|proveedor|producto|sku|id|sucursal|'
        r'categoria|cliente|canal|region)\b|'
        r'\b(?:en|a|al|para)\s+(?!general\b|total\b)\S+|'
        r'\b(?:de|del)\s+(?!(?:(?:mi|mis|la|las|el|los)\s+)?'
        r'(?:compras?|fletes?|archivo|negocio|periodo|vista)\b)\S+'
    )
    named = any(
        normalize_query(row.get('nombre') or '') and re.search(
            r'\b' + re.escape(normalize_query(row['nombre'])) + r'\b', text,
        ) for _, rows in _dimensions(metrics) for row in rows for text in context
    )
    if named or any(re.search(scope_pattern, text) for text in context):
        return _result(
            'No tengo publicado el importe de compras o fletes para ese periodo o segmento. '
            'Selecciona ese alcance en Explorar; las ventas y el total general no lo sustituyen.',
            'metric_purchases_scope_unavailable', suggestions, 'medium',
        )
    if metrics.get('moneda_mixta') or metrics.get('datos_monetarios_disponibles') is False:
        return _result(
            'No hay un importe publicable de compras en una moneda compatible. '
            'Separa las monedas de la fuente antes de interpretar el total.',
            'metric_purchases_unavailable', suggestions, 'medium',
        )
    topic = next((text for text in reversed(context) if _TOPIC.search(text)), question)
    freight = bool(re.search(r'\bfletes?\b', topic))
    key = 'fletes_compra' if freight else 'compras_netas'
    label = 'Fletes de compra' if freight else 'Compras netas'
    indicator = next((item for group in ((business.get('catalogo_indicadores') or {}).get('categorias') or [])
                      for item in (group.get('indicadores') or []) if item.get('id') == key), {})
    value = _number(indicator.get('valor'))
    warnings = [str(warning) for warning in (indicator.get('advertencias') or []) if warning]
    if indicator.get('estado') not in {'available', 'partial'} or value is None:
        return _result(
            f'{label}: no hay un importe validado disponible. No significa cero. '
            + (' '.join(warnings[:2]) if warnings else
               'Revisa importes, fechas e IDs en la fuente; las ventas no permiten deducir las compras.'),
            'metric_purchases_unavailable', suggestions, 'medium',
        )
    answer = f"{label}: {format_amount(value, str(metrics.get('moneda') or 'CLP'))}."
    coverage = _number(indicator.get('cobertura_datos_pct'))
    partial = indicator.get('estado') == 'partial'
    if partial:
        answer += ' Es un importe parcial.'
    if coverage is not None:
        answer += f' Cobertura de datos: {_percent(coverage)}.'
    sources = indicator.get('fuentes') or []
    if sources:
        answer += ' Fuente: ' + ', '.join(str(source) for source in sources[:3]) + '.'
    answer += (' El flete se cuenta una vez por documento, sin repetirlo por linea.' if freight else
               ' Corresponde a compras no anuladas del alcance visible; no acredita pagos realizados.')
    if warnings:
        answer += ' ' + ' '.join(warnings[:2])
    return _result(answer, 'metric_purchase_freight' if freight else 'metric_purchases',
                   suggestions, 'medium' if partial or warnings else 'high')
