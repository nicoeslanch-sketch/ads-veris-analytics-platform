"""Read the selected relationship's published KPIs without recomputing the workbook."""

import re
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict

from .language_normalization import normalize_query


class PublishedKpi(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str = Field(max_length=100)
    label: str = Field(max_length=200)
    value: float | str | None
    format: Literal['currency', 'percent', 'days', 'integer', 'number', 'text']
    available: bool
    help: str | None = Field(default=None, max_length=2000)


class PublishedInsight(BaseModel):
    title: str = Field(max_length=300)
    detail: str = Field(max_length=4000)
    evidence: str | None = Field(default=None, max_length=2000)


class RelationLabel(BaseModel):
    label: str = Field(max_length=1000)


class RelationshipContext(BaseModel):
    relation: RelationLabel
    currency: str = Field(max_length=12)
    available: bool
    kpis: list[PublishedKpi] = Field(default_factory=list, max_length=30)
    findings: list[PublishedInsight] = Field(default_factory=list, max_length=30)
    alerts: list[PublishedInsight] = Field(default_factory=list, max_length=30)


def answer_relationship(message, context, history=None):
    from .metric_assistant import _es_number, format_amount, _result

    question = normalize_query(message)
    previous = next((normalize_query(row.get('content', '')) for row in reversed(history or [])
                     if row.get('role') == 'user'), '')
    followup = bool(re.search(r'\b(y eso|es bueno|es malo|como lo mejoro|que hago|por que)\b', question))
    if followup:
        question += ' ' + previous
    financial = r'\b(ventas|ingresos|utilidad|ganancia|margen|costo|costos|gastos|cobertura|stock|inventario|clientes|proveedores|riesgo|rentables|moneda|uf|pesos)\b'
    summary = bool(re.search(r'\b(resumen|resume|conexion|conclusion|conclusiones|revisar|hallazgos|alertas)\b', question))
    if not summary and not re.search(financial, question):
        return None
    suggestions = ['Resume esta conexion', 'Cobertura de costos', 'Que debo revisar']
    name = str(context['relation']['label']).replace('_', ' ')
    scope = f'En la conexion {name}: '
    if not context.get('available'):
        return _result(scope + 'no hay indicadores disponibles. No voy a completar cifras que no se calcularon.',
                       'metric_relationship_unavailable', suggestions, 'medium')
    if re.search(r'\b(moneda|uf|pesos)\b', question):
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
    )
    selected = []
    for pattern, target in topics:
        if re.search(pattern, question):
            selected.extend(row for row in kpis if re.search(target, normalize_query(row['id'] + ' ' + row['label'])))
    selected = list({row['id']: row for row in selected}.values())
    if not selected and summary:
        selected = kpis[:4]
    if not selected:
        return _result(scope + 'ese indicador no esta publicado para esta relacion. Cambia a la vision del negocio o a una conexion que incluya las fuentes necesarias.',
                       'metric_relationship_missing', suggestions, 'medium')
    answer = scope + '; '.join(f"{row['label']}: {formatted(row)}" for row in selected[:5]) + '.'
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
