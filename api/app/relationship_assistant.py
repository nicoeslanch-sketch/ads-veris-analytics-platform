"""Read the selected relationship's published KPIs without recomputing the workbook."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ConfigDict, StrictFloat

from .language_normalization import normalize_query


class PublishedKpi(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str = Field(max_length=100)
    label: str = Field(max_length=200)
    value: StrictFloat | Annotated[str, Field(max_length=500)] | None
    format: Literal['currency', 'percent', 'days', 'integer', 'number', 'text']
    available: bool
    help: str | None = Field(default=None, max_length=2000)


class PublishedInsight(BaseModel):
    title: str = Field(max_length=300)
    detail: str = Field(max_length=4000)
    evidence: str | None = Field(default=None, max_length=2000)


class RelationLabel(BaseModel):
    label: str = Field(max_length=1000)


class PublishedSeries(BaseModel):
    key: str = Field(max_length=100)
    label: str = Field(max_length=200)
    format: Literal['currency', 'percent', 'days', 'integer', 'number', 'text']


class PublishedChart(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    title: str = Field(max_length=300)
    category_key: str = Field(max_length=100)
    series: list[PublishedSeries] = Field(max_length=6)
    data: list[Annotated[dict[Annotated[str, Field(max_length=100)],
        StrictFloat | Annotated[str, Field(max_length=500)] | None], Field(max_length=7)]] = Field(max_length=30)


class PublishedPeriod(BaseModel):
    desde: str | None = Field(default=None, max_length=30)
    hasta: str | None = Field(default=None, max_length=30)


class RelationshipContext(BaseModel):
    relation: RelationLabel
    currency: str = Field(max_length=12)
    available: bool
    kpis: list[PublishedKpi] = Field(default_factory=list, max_length=30)
    findings: list[PublishedInsight] = Field(default_factory=list, max_length=30)
    alerts: list[PublishedInsight] = Field(default_factory=list, max_length=30)
    charts: list[PublishedChart] = Field(default_factory=list, max_length=12)
    period: PublishedPeriod | None = None


def answer_relationship(message, context, history=None):
    from .metric_assistant import _es_number, format_amount, _result

    question = normalize_query(message)
    if re.search(r'\b(descargar|descargo|subir|limpiar|limpieza|estandarizar|contrasena|autenticador)\b', question):
        return None
    financial = r'\b(ventas|ingresos|utilidad|ganancia|margen|costo|costos|gastos|cobertura|stock|inventario|clientes|proveedores|riesgo|rentables|moneda|uf|pesos|caja|efectivo|liquidez|deuda|ticket|iva|dso|unidades|productos)\b'
    previous = next((normalize_query(row.get('content', '')) for row in reversed(history or [])
                     if row.get('role') == 'user' and re.search(financial, normalize_query(row.get('content', '')))), '')
    followup = bool(re.search(r'\b(y eso|es bueno|es malo|como lo mejoro|que hago|por que)\b', question))
    if previous and not re.search(financial, question) and re.search(r'\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b', question):
        followup = True
    if followup:
        question += ' ' + previous
    summary = bool(re.search(r'\b(resumen|resume|conexion|conclusion|conclusiones|revisar|hallazgos|alertas)\b', question))
    if not summary and not re.search(financial + r'|\bperiodo\b', question):
        return None
    suggestions = ['Resume esta conexion', 'Cobertura de costos', 'Que debo revisar']
    name = str(context['relation']['label']).replace('_', ' ')
    scope = f'En la conexion {name}: '
    if not context.get('available'):
        return _result(scope + 'no hay indicadores disponibles. No voy a completar cifras que no se calcularon.',
                       'metric_relationship_unavailable', suggestions, 'medium')
    if re.search(r'\b(periodo|fechas)\b', question) and not re.search(financial, question):
        period = context.get('period') or {}
        text = f"el periodo publicado va de {period['desde']} a {period['hasta']}." if period.get('desde') and period.get('hasta') else 'no hay un rango de fechas publicado en esta conexion.'
        return _result(scope + text, 'metric_relationship_period', suggestions)
    if re.search(r'\b(convertir|convierte|conversion|pasar|pasalo)\b', question) and re.search(r'\b(uf|pesos|clp|usd|dolares)\b', question):
        return _result(scope + f"la moneda es {context['currency']}. Para convertir necesito la tasa y su fecha; no aplicare una tasa inventada.", 'metric_relationship_conversion', suggestions, 'medium')
    dated = re.search(r'\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|ayer|hoy|trimestre|semestre|mes pasado)\b|\b20\d{2}\b', question)
    scoped_ranking = re.search(r'\b(en|para|sin|excepto) (?:la |el )?(sucursal|cliente|producto|vendedor)\b', question)
    named_entity = re.search(r'\b(sucursal|cliente|producto|vendedor)\s+\w+', question)
    ranking = re.search(r'\b(mas|menos|top|ranking|mejor|peor)\b', question)
    if dated or scoped_ranking or (named_entity and not ranking):
        return _result(scope + 'no tengo ese desglose por fecha o entidad en los indicadores publicados. Ajusta el periodo o filtro en la vista; no usare el total como si fuera ese segmento.', 'metric_relationship_scope', suggestions, 'medium')
    if re.search(r'\b(moneda|uf|pesos)\b', question) and not re.search(r'\b(ventas|ingresos|utilidad|ganancia|costo|costos|gastos|stock)\b', question):
        return _result(scope + f"los importes estan expresados en {context['currency']}. No hice una conversion a pesos ni a otra moneda.",
                       'metric_relationship_currency', suggestions)
    kpis = [row for row in context.get('kpis', []) if row.get('available') and row.get('value') is not None]

    def formatted(row):
        value = row['value']
        if isinstance(value, str):
            return value
        if row['format'] == 'currency':
            return format_amount(value, context['currency'])
        return _es_number(value, decimals=1 if row['format'] in {'percent', 'days'} else 2) + {'percent': '%', 'days': ' dias'}.get(row['format'], '')

    if re.search(r'\b(mas|menos|top|ranking|mejor|peor)\b', question) and re.search(r'\b(producto|productos|sucursal|sucursales|cliente|clientes|vendedor|vendedores)\b', question):
        measure = 'unidades|cantidad' if re.search(r'\b(unidades|cantidad|vendidos)\b', question) else 'utilidad|ganancia' if re.search(r'\b(utilidad|ganancia|rentables)\b', question) else 'ventas|ingresos'
        dimension = next(word for word in ('producto', 'sucursal', 'cliente', 'vendedor') if word in question)
        for chart in context.get('charts', []):
            if dimension not in normalize_query(chart['title'] + ' ' + chart['category_key']):
                continue
            series = next((s for s in chart['series'] if re.search(measure, normalize_query(s['label'] + ' ' + s['key']))), None)
            if not series:
                continue
            rows = [r for r in chart['data'] if isinstance(r.get(series['key']), (int, float)) and r.get(chart['category_key']) is not None]
            if not rows:
                continue
            ascending = bool(re.search(r'\b(menos|peor)\b', question))
            rows = sorted(rows, key=lambda r: r[series['key']], reverse=not ascending)[:3]
            text = '; '.join(f"{r[chart['category_key']]}: {formatted({'value': r[series['key']], 'format': series['format']})}" for r in rows)
            return _result(scope + f"entre los elementos mostrados en '{chart['title']}', por {series['label']}: {text}. No implica que sean todos los productos o clientes del archivo.", 'metric_relationship_ranking', suggestions)
        return _result(scope + 'no tengo un grafico con ese desglose y esa medida. No confundire mas unidades con mas ingresos o mayor margen.', 'metric_relationship_ranking_missing', suggestions, 'medium')

    topics = (
        (r'\b(cobertura|faltan costos)\b', r'cobertura'),
        (r'\b(utilidad|ganancia|beneficio)\b', r'utilidad|ganancia'),
        (r'\bmargen\b', r'margen'),
        (r'\b(costo|costos)\b', r'^costo$|costo de'),
        (r'\b(ventas|ingresos)\b', r'ventas|ingresos'),
        (r'\bgastos\b', r'gasto'),
        (r'\b(stock|inventario)\b', r'stock|inventario'),
        (r'\bclientes\b', r'cliente'),
        (r'\b(riesgo|rentables)\b', r'riesgo|rentables'),
        (r'\b(caja|efectivo)\b', r'caja|efectivo'),
        (r'\bliquidez\b', r'liquidez|razon corriente'),
        (r'\bdeuda\b', r'deuda|endeudamiento'),
        (r'\bticket\b', r'ticket'),
        (r'\biva\b', r'\biva\b'),
        (r'\bdso\b', r'\bdso\b'),
    )
    selected = []
    missing = []
    for pattern, target in topics:
        if re.search(pattern, question):
            if target == r'^costo$|costo de' and re.search(r'\bcobertura\b', question):
                continue
            if 'utilidad|ganancia' in target and re.search(r'\b(neta|neto)\b', question):
                target = r'(utilidad|ganancia|resultado).*net[oa]'
            matches = [row for row in kpis if re.search(target, normalize_query(row['id'] + ' ' + row['label']))]
            selected.extend(matches)
            if not matches:
                missing.append(re.search(pattern, question)[0])
    selected = list({row['id']: row for row in selected}.values())
    if not selected and summary:
        selected = kpis[:4]
    if not selected:
        return _result(scope + 'ese indicador no esta publicado para esta relacion. Cambia a la vision del negocio o a una conexion que incluya las fuentes necesarias.',
                       'metric_relationship_missing', suggestions, 'medium')
    answer = scope + '; '.join(f"{row['label']}: {formatted(row)}" for row in selected[:5]) + '.'
    if missing:
        answer += ' No esta publicado: ' + ', '.join(dict.fromkeys(missing)) + '. No equivale a cero.'
    explanations = [row['help'] for row in selected if row.get('help')]
    if explanations:
        answer += ' ' + ' '.join(dict.fromkeys(explanations))
    if any(re.search(r'utilidad|margen|costo', normalize_query(row['label'])) for row in selected):
        answer += ' La utilidad bruta no es caja ni utilidad neta; revisa cobertura y si el costo es historico o estimado antes de decidir.'
    if summary or followup:
        insights = context.get('alerts', []) or context.get('findings', [])
        if insights:
            answer += ' Para revisar: ' + ' '.join(f"{row['title']}: {row['detail']}" for row in insights[:2])
        elif followup:
            answer += ' Compara periodos equivalentes y completa los datos faltantes; esta cifra por si sola no demuestra la causa.'
    return _result(answer, 'metric_relationship', suggestions)
