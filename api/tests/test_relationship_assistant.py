from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.routes.assistant import BotRequest
from app.relationship_assistant import RelationshipContext
from app.support_knowledge import answer_for


def dashboard():
    return {'relation': {'label': 'Ventas_2026 + Costos_Productos'}, 'currency': 'CLP', 'available': True,
            'kpis': [
                {'id': 'ventas', 'label': 'Ventas netas', 'value': 669700, 'format': 'currency', 'available': True},
                {'id': 'utilidad', 'label': 'Utilidad bruta estimada', 'value': -10000079, 'format': 'currency', 'available': True},
                {'id': 'cobertura', 'label': 'Cobertura de costos', 'value': 65.8, 'format': 'percent', 'available': True},
            ], 'alerts': [{'title': 'Costos incompletos', 'detail': 'Revisa los IDs sin costo.', 'evidence': None}]}


@pytest.mark.parametrize('question,expected', [
    ('cuanto son mis ingresos totales', '$669.700'),
    ('cuales miutilidad', '$-10.000.079'),
    ('cobertura de costos', '65,8%'),
    ('resume esta conexion', '$669.700'),
    ('en que moneda estan', 'CLP'),
    ('cuanto stock tengo', 'no esta publicado'),
    ('que debo revisar', 'IDs sin costo'),
])
def test_answers_use_only_selected_relationship(question, expected):
    context = RelationshipContext.model_validate(dashboard()).model_dump()
    result = answer_for(question, metrics={'relationship_dashboard': context})
    assert expected in result['answer'], result
    assert result['matched_key'].startswith('metric_relationship')


def test_conversation_keeps_scope_and_can_return_to_platform_help():
    history = []
    for question in ['mis ingresos', 'mi utilidad', 'y eso es malo', 'cobertura de costos',
                     'que debo revisar', 'resume esta conexion']:
        result = answer_for(question, metrics={'relationship_dashboard': dashboard()}, history=history)
        assert 'Ventas 2026 + Costos Productos' in result['answer']
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': result['answer']}]
    result = answer_for('como descargo los datos limpios', metrics={'relationship_dashboard': dashboard()}, history=history)
    assert not result['matched_key'].startswith('metric_relationship')


def test_uf_is_not_converted_and_unavailable_is_not_zero():
    data = deepcopy(dashboard())
    data['currency'] = 'UF'
    data['kpis'][0]['value'] = 125.75
    assert 'UF 125,75' in answer_for('mis ventas', metrics={'relationship_dashboard': data})['answer']
    data['kpis'][0]['available'] = False
    assert 'no esta publicado' in answer_for('mis ventas', metrics={'relationship_dashboard': data})['answer']


def test_relationship_payload_is_structured_and_bounded():
    data = dashboard()
    assert BotRequest(message='hola', relationship_dashboard=data).relationship_dashboard
    data['kpis'] *= 11
    with pytest.raises(ValidationError):
        BotRequest(message='hola', relationship_dashboard=data)


@pytest.mark.parametrize('question', ['mis ventas en enero', 'mis ingresos de 2025',
    'utilidad del cliente Pedro', 'mis ventas ayer', 'ingresos de la sucursal Centro',
    'productos con mas ingresos en enero', 'productos mas vendidos en la sucursal Centro'])
def test_scoped_question_never_uses_whole_relationship_total(question):
    result = answer_for(question, metrics={'relationship_dashboard': dashboard()})
    assert '$' not in result['answer']
    assert result['matched_key'] == 'metric_relationship_scope'


def test_net_profit_is_not_gross_profit_and_missing_expenses_not_zero():
    data = {'relationship_dashboard': dashboard()}
    result = answer_for('mi utilidad neta', metrics=data)
    assert '10.000.079' not in result['answer'] and 'no esta publicado' in result['answer']
    result = answer_for('mis ventas y gastos', metrics=data)
    assert '$669.700' in result['answer'] and 'No esta publicado: gastos' in result['answer']


@pytest.mark.parametrize('question', ['mis ventas en UF', 'cuantossonmisingresostotales en uf'])
def test_currency_in_metric_question_does_not_hide_the_number(question):
    data = dashboard()
    data.update(currency='UF')
    data['kpis'][0]['value'] = 125.75
    result = answer_for(question, metrics={'relationship_dashboard': data})
    assert 'UF 125,75' in result['answer']


def test_conversion_needs_dated_rate():
    result = answer_for('convierte mis ventas a UF', metrics={'relationship_dashboard': dashboard()})
    assert 'tasa y su fecha' in result['answer'] and '669.700' not in result['answer']


def chart_context():
    data = dashboard()
    data['charts'] = [{'title': 'Ingresos por producto', 'category_key': 'producto',
        'series': [{'key': 'ingresos', 'label': 'Ingresos', 'format': 'currency'}],
        'data': [{'producto': 'Azul', 'ingresos': 120}, {'producto': 'Verde', 'ingresos': 240},
                 {'producto': 'Rojo', 'ingresos': None}]}]
    return data


def test_rankings_reference_published_chart_and_distinguish_measure():
    data = RelationshipContext.model_validate(chart_context()).model_dump()
    result = answer_for('que producto genera mas ingresos', metrics={'relationship_dashboard': data})
    assert "'Ingresos por producto'" in result['answer']
    assert result['answer'].index('Verde: $240') < result['answer'].index('Azul: $120')
    assert 'Rojo:' not in result['answer'] and 'elementos mostrados' in result['answer']
    result = answer_for('cuales son los productos mas vendidos en unidades', metrics={'relationship_dashboard': data})
    assert 'No confundire mas unidades' in result['answer'] and '$' not in result['answer']


def test_long_relationship_conversation_handles_topic_switches_without_stale_data():
    history = []
    data = chart_context()
    turns = [
        ('cuantossonmisingresostotales', '$669.700'),
        ('y mi ut lidad', '$-10.000.079'),
        ('mi utilidad', '$-10.000.079'),
        ('y eso es malo', 'La utilidad bruta no es caja'),
        ('por que', 'Revisa los IDs sin costo'),
        ('cobertura de costos', '65,8%'),
        ('mi utilidad neta', 'no esta publicado'),
        ('mis ventas y gastos', 'No esta publicado: gastos'),
        ('mis ventas en enero', 'no usare el total'),
        ('y las de marzo', 'no usare el total'),
        ('mis ventas de marzo', 'no usare el total'),
        ('en que moneda estan', 'CLP'),
        ('convierte mis ventas a UF', 'tasa y su fecha'),
        ('que producto genera mas ingresos', 'Verde: $240'),
        ('productos mas vendidos en unidades', 'No confundire'),
        ('cuanto stock tengo', 'no esta publicado'),
        ('cuanta liquidez tengo', 'no esta publicado'),
        ('cuanto efectivo tengo', 'no esta publicado'),
        ('como descargo los datos limpios', 'descarga'),
        ('resume esta conexion', 'Ventas 2026 + Costos Productos'),
    ]
    for question, expected in turns:
        result = answer_for(question, metrics={'relationship_dashboard': data}, history=history[-12:])
        if expected:
            assert expected in result['answer'], (question, result)
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': result['answer']}]
    changed = dashboard()
    changed['relation']['label'] = 'Gastos_Operacionales + Sucursales'
    changed['kpis'] = [{'id': 'gastos', 'label': 'Gastos', 'value': 8100, 'format': 'currency', 'available': True}]
    result = answer_for('mis gastos', metrics={'relationship_dashboard': changed}, history=history[-12:])
    assert '$8.100' in result['answer'] and '669.700' not in result['answer']
    assert 'Gastos Operacionales + Sucursales' in result['answer']


@pytest.mark.parametrize('value', [True, 'x' * 501, float('inf')])
def test_published_value_cannot_be_boolean_unbounded_or_infinite(value):
    data = dashboard()
    data['kpis'][0]['value'] = value
    with pytest.raises(ValidationError):
        RelationshipContext.model_validate(data)


def test_relationship_context_http(client, auth_headers):
    response = client.post('/assistant/bot', headers=auth_headers,
                           json={'message': 'mis ventas', 'relationship_dashboard': dashboard()})
    assert response.status_code == 200, response.text
    assert '$669.700' in response.json()['answer']
    data = dashboard()
    data['kpis'][0]['value'] = float('nan')
    with pytest.raises(ValidationError):
        BotRequest(message='hola', relationship_dashboard=data)
