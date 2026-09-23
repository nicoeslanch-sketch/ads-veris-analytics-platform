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
    data = dashboard()
    data['kpis'][0]['value'] = float('nan')
    with pytest.raises(ValidationError):
        BotRequest(message='hola', relationship_dashboard=data)
