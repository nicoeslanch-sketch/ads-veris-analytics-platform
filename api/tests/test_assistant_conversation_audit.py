from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.language_normalization import normalize_query
from app.support_knowledge import ARTICLES, answer_for
from app.routes import assistant
from tests.assistant_scenarios import conversation_scenarios, sales_metrics


@pytest.mark.parametrize('name,metrics,turns', conversation_scenarios(), ids=lambda item: item if isinstance(item, str) else None)
def test_reproducible_conversations(name, metrics, turns):
    history = []
    for question, expected in turns:
        answer = answer_for(question, metrics=metrics, history=history[-12:])
        for part in expected:
            assert part.casefold() in answer['answer'].casefold(), (name, question, answer)
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer['answer']}]


@pytest.mark.parametrize('prefix', ['cuanto vendi en ', 'cuantovendien', 'cuatno vendi en ', 'mis ingrezos en '])
@pytest.mark.parametrize('month,index', [('enero', 1), ('febrero', 2), ('marzo', 3)])
@pytest.mark.parametrize('currency,prefix_money', [('CLP', '$'), ('UF', 'UF '), ('USD', 'US$')])
def test_typo_month_currency_matrix(prefix, month, index, currency, prefix_money):
    metrics = sales_metrics()
    metrics['moneda'] = currency
    answer = answer_for(prefix + month, metrics=metrics)
    assert f'2026-0{index}' in answer['answer']
    assert f'{prefix_money}{index * 100}' in answer['answer']


@pytest.mark.parametrize('question', [
    'cuanto vendi en Sur y Producto Verde', 'cuanto vendi en Sur sin Alimentos',
    'cuanto vendi en febrero sin devoluciones', 'cuanto vendi excepto Sur',
    'cuantas unidades vendi en Sur', 'cuantos ingresos tuvo el cliente Cliente B',
    'cuanto vendi el 15/01/2026', 'cuanto vendi el 15-01-2026',
])
def test_unknown_scope_never_returns_total(question):
    answer = answer_for(question, metrics=sales_metrics())
    assert '$' not in answer['answer'], answer
    assert answer['confidence'] != 'high'


def test_averages_are_not_added_and_percentages_not_currency():
    metrics = sales_metrics()
    metrics['analisis_generico'] = {'evolucion': {'columna': 'tasa', 'formato': 'porcentaje', 'operacion': 'promedio',
        'valores': [{'mes': '2026-01', 'valor': 10}, {'mes': '2026-02', 'valor': 20}]}}
    response = answer_for('total entre enero y febrero', metrics=metrics)
    assert 'No los sumo' in response['answer']
    assert '10%' in response['answer'] and '20%' in response['answer']
    assert '$' not in response['answer']


def test_mixed_currencies_not_added():
    metrics = sales_metrics()
    metrics['moneda_mixta'] = True
    answer = answer_for('cuanto vendi entre enero y marzo', metrics=metrics)
    assert '$600' not in answer['answer']


@pytest.mark.parametrize('word,expected', [('enreo', 'enero'), ('febreo', 'febrero'), ('marso', 'marzo'),
    ('cuantovendienenero', 'cuanto vendi en enero'), ('cuantossonmisingresostotales', 'cuantos son mis ingresos totales')])
def test_normalization_is_explicit(word, expected):
    assert normalize_query(word) == expected


def test_unknown_entity_is_not_fuzzy_replaced():
    metrics = sales_metrics()
    metrics['ventas_por_canal'] = [{'nombre': 'Margen Ltda', 'ingresos': 400}, {'nombre': 'Marven Ltda', 'ingresos': 200}]
    answer = answer_for('cuanto vendi en la sucursal Marven Ltda', metrics=metrics)
    assert 'Marven Ltda' in answer['answer'] and '$200' in answer['answer']


def test_product_decision_conversation_uses_ids_and_avoids_unsupported_advice():
    metrics = sales_metrics()
    question = 'Que productos llevan meses sin vender'
    assert answer_for(question, metrics=metrics)['matched_key'] == 'metric_product_activity_missing'
    metrics['actividad_productos'] = {'fecha_corte': '2026-06-30', 'productos': [
        {'id': '001', 'nombre': 'Producto Azul', 'meses_sin_venta_observada': 4}]}
    history = []
    for question in ['Que productos llevan meses sin vender', 'Y que hago', 'Entonces lo retiro']:
        answer = answer_for(question, metrics=metrics, history=history)
        assert 'ID 001' in answer['answer']
        assert 'No demuestra falta de demanda' in answer['answer']
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer['answer']}]


@pytest.mark.parametrize('question', ['cuota de almacenamiento', 'error 507', 'espacio lleno', 'cuantos archivos puedo guardar'])
def test_storage_quota_answers_are_not_financial_loan_advice(question):
    answer = answer_for(question)
    assert answer['matched_key'] == 'storage_quota'
    assert 'sin borrar' in answer['answer']
    assert 'duplicados' in answer['answer']


@pytest.mark.parametrize('metrics', [
    {'clientes': {'top': 'mal'}}, {'analisis_generico': {'evolucion': 'mal'}},
    {'analisis_negocio': {'cobranza': {'kpis': []}}}, {'analisis_productos': 'mal'},
    {'analisis_generico': {'desgloses': [{'valores': ['mal']}] }},
    {'agrupaciones_flexibles': [{'grupos': [1]}]}, {'kpis': {'cobertura_costos': 'mal'}},
])
def test_invalid_context_is_rejected(metrics):
    with pytest.raises(ValidationError):
        assistant.BotRequest(message='cuanto vendi', metrics=metrics)


def test_blank_and_deep_context_rejected():
    with pytest.raises(ValidationError):
        assistant.BotRequest(message='   ')
    node = {}
    for _ in range(20):
        node = {'nested': node}
    with pytest.raises(ValidationError):
        assistant.BotRequest(message='hola', metrics=node)


def test_metric_request_never_fetches_catalog(client, auth_headers, monkeypatch):
    network = Mock(side_effect=AssertionError('Metrics must not query the catalog'))
    monkeypatch.setattr(assistant, '_cached_catalog', network)
    monkeypatch.setattr(assistant, '_guard_rate', lambda _: None)
    response = client.post('/assistant/bot', headers=auth_headers, json={'message': 'cuanto vendi', 'metrics': sales_metrics()})
    assert response.status_code == 200
    assert '$600' in response.json()['answer']
    assert not network.called


def test_catalog_cached_and_expires(monkeypatch):
    from app.config import Settings
    settings = Settings(supabase_url='https://catalog.test', supabase_service_role_key='test-only')
    loader = Mock(return_value=ARTICLES)
    monkeypatch.setattr(assistant, '_load_catalog', loader)
    monkeypatch.setattr(assistant, '_catalog_cache', assistant.OrderedDict())
    monkeypatch.setattr(assistant, 'monotonic', lambda: 1000)
    assistant._cached_catalog(settings)
    assistant._cached_catalog(settings)
    assert loader.call_count == 1
    monkeypatch.setattr(assistant, 'monotonic', lambda: 1121)
    assistant._cached_catalog(settings)
    assert loader.call_count == 2


def test_rate_limiter_reclaims_expired_users(monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(minutes=2)
    requests = assistant.defaultdict(assistant.deque, {'expired': assistant.deque([old])})
    monkeypatch.setattr(assistant, '_requests', requests)
    monkeypatch.setattr(assistant, '_last_rate_sweep', 0)
    assistant._guard_rate('active')
    assert set(requests) == {'active'}


def test_rephrased_currency_question_is_not_answered_twice():
    response = answer_for('y en que moneda estan? son UF?', metrics=sales_metrics())
    assert response['answer'].count('La moneda detectada') == 1
    assert response['matched_key'] != 'conversation_multiple'


@pytest.mark.parametrize('question', ['y eso es ganancia?', 'y eso es plata cobrada?'])
def test_income_followup_explains_distinction_instead_of_repeating_total(question):
    response = answer_for(question, metrics=sales_metrics(), history=[{'role': 'user', 'content': 'cuantos ingresos tengo'}])
    assert response['matched_key'] == 'conversation_financial_distinction'
    assert 'No son equivalentes' in response['answer']
