from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.language_normalization import normalize_query
from app.support_knowledge import ARTICLES, answer_for
from app.routes import assistant
from tests.assistant_scenarios import conversation_scenarios, sales_metrics


@pytest.mark.parametrize('question', ['quiero eliminar mi cuenta', 'borrarmicuenta',
    'quieroeliminarmicuenta', 'borramisdatos', 'borra mis datos', 'quieroelimnarmicuenta'])
def test_privacy_erasure_is_not_a_financial_account_and_never_claims_execution(question):
    history = []
    for text in [question, 'y ya lo borraste?', 'yaloborraste']:
        reply = answer_for(text, metrics=sales_metrics(), history=history)
        assert reply['matched_key'] == 'privacy_erasure', reply
        assert 'Este chat no ejecuta borrados' in reply['answer']
        assert 'recibida no significa' in reply['answer']
        history += [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': reply['answer']}]


@pytest.mark.parametrize('question,key', [('politicadeprivacidad', 'privacy_rights'),
    ('revocarconsentimiento', 'privacy_rights'), ('donde puedo guardar tarjeta', 'privacy_card_data'),
    ('te envio mi cvv', 'privacy_card_data')])
def test_privacy_guidance_without_invented_actions(question, key):
    answer = answer_for(question)
    assert answer['matched_key'] == key, answer


@pytest.mark.parametrize('question', ['quiero borrar mis datos duplicados', 'eliminar mis datos duplicados',
                                    'borra mis datos duplicados'])
def test_duplicate_cleanup_is_not_account_erasure(question):
    answer = answer_for(question, metrics=sales_metrics())
    assert answer['matched_key'] == 'duplicates', answer
    assert 'Configuracion > Privacidad' not in answer['answer']


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


@pytest.mark.parametrize('followup', [
    'y ese costo de referencia es lo que he gastado?',
    'y mi costo promedio', 'que es ese costo de referencia', 'y cuanto gaste',
])
@pytest.mark.parametrize('currency,amount', [('CLP', '$125'), ('UF', 'UF 125')])
def test_catalog_cost_followup_does_not_repeat_previous_income_answer(followup, currency, amount):
    metrics = sales_metrics()
    metrics.update(tipo_analisis='catalogo_productos', moneda=currency,
        analisis_productos={'productos': 3, 'costos': {'promedio': 125},
                           'precios_lista': {'promedio': 200}})
    first_question = 'cuantossonmisingresostotales'
    first = answer_for(first_question, metrics=metrics)
    assert first['matched_key'] == 'metric_catalog_income_unavailable'
    assert 'catalogo' in first['answer']
    assert '$600' not in first['answer']
    history = [{'role': 'user', 'content': first_question}, {'role': 'assistant', 'content': first['answer']}]
    response = answer_for(followup, metrics=metrics, history=history)
    assert response['matched_key'] == 'metric_catalog_reference_cost'
    assert amount in response['answer']
    assert 'No es lo que has gastado' in response['answer']
    assert 'cantidades y transacciones vinculadas por ID' in response['answer']


def test_catalog_cost_unknown_or_mixed_currency_never_fabricates_amount():
    metrics = sales_metrics()
    metrics.update(tipo_analisis='catalogo_productos', analisis_productos={'productos': 2, 'costos': {}})
    response = answer_for('y mi costo de referencia', metrics=metrics)
    assert 'No hay un costo' in response['answer'] and '$' not in response['answer']
    metrics['analisis_productos']['costos']['promedio'] = 100
    metrics['moneda_mixta'] = True
    response = answer_for('y mi costo promedio', metrics=metrics)
    assert '$100' not in response['answer']
    assert response['matched_key'] == 'metric_currency'


@pytest.mark.parametrize('question', ['costo promedio en enero', 'costo del producto XYZ', 'costo del SKU ABC'])
def test_catalog_scope_is_not_replaced_with_global_average(question):
    metrics = sales_metrics()
    metrics.update(tipo_analisis='catalogo_productos',
        analisis_productos={'productos': 2, 'costos': {'promedio': 125}})
    response = answer_for(question, metrics=metrics)
    assert '$125' not in response['answer']
    assert response['confidence'] == 'medium'


@pytest.mark.parametrize('question', [
    'y cuanto me deben mis clientes?', 'cuanto me debe la clientela',
    'cual es mi saldo por cobrar', 'mis cuentas por cobrar', 'mis cxc',
])
def test_receivables_are_not_customer_sales_rankings(question):
    metrics = sales_metrics()
    history = [{'role': 'user', 'content': 'cuanto vendi'}]
    response = answer_for(question, metrics=metrics, history=history)
    assert response['matched_key'] == 'metric_receivables_unavailable'
    assert 'CxC' in response['answer']
    assert '$' not in response['answer']
    metrics['analisis_negocio'] = {'operacion': {'cuentas_por_cobrar': 125}}
    response = answer_for(question, metrics=metrics, history=history)
    assert response['matched_key'] == 'metric_receivables_balance'
    assert '$125' in response['answer']
    assert 'no ventas nuevas ni dinero cobrado' in response['answer']


@pytest.mark.parametrize('question', [
    'cuanto me debe Cliente B', 'y cuanto me debe el cliente XYZ', 'cuanto me debe Pedro',
    'saldo por cobrar de Pedro',
    'cuanto me deben en enero', 'cuentas por cobrar en 2026',
    'cuanto me deben hoy', 'saldo por cobrar solo en Sur',
    'cuanto tengo en inventario en febrero', 'valor inventario del producto Azul',
])
def test_balances_never_use_sales_subtotals_or_global_balance_for_other_scope(question):
    metrics = sales_metrics()
    metrics['analisis_negocio'] = {'operacion': {'cuentas_por_cobrar': 125, 'valor_inventario': 300}}
    response = answer_for(question, metrics=metrics)
    assert response['matched_key'] == 'metric_balance_scope_unavailable'
    assert '$' not in response['answer']


def test_receivables_zero_missing_mixed_and_generic_source():
    metrics = sales_metrics()
    metrics['analisis_negocio'] = {'operacion': {'cuentas_por_cobrar': 0}}
    assert '$0' in answer_for('cuanto me deben', metrics=metrics)['answer']
    metrics['moneda_mixta'] = True
    assert '$0' not in answer_for('cuanto me deben', metrics=metrics)['answer']
    metrics['moneda_mixta'] = False
    metrics['analisis_negocio']['operacion']['cuentas_por_cobrar'] = None
    assert '$0' not in answer_for('cuanto me deben', metrics=metrics)['answer']
    metrics['analisis_generico'] = {'subtipo': 'cuentas_por_cobrar', 'numericas': [
        {'columna': 'SaldoPendiente_CLP', 'total': -25, 'formato': 'moneda'}]}
    response = answer_for('cuanto me deben mis clientes', metrics=metrics)
    assert '$-25' in response['answer']
    assert 'saldo declarado' in response['answer']


def test_business_inventory_uses_snapshot_not_sold_units():
    metrics = sales_metrics()
    response = answer_for('cuanto tengo en inventario', metrics=metrics)
    assert response['matched_key'] == 'metric_business_inventory_unavailable'
    assert 'no significa stock cero' in response['answer']
    metrics['analisis_negocio'] = {'operacion': {
        'stock_inventario': 40, 'valor_inventario': 300, 'fecha_corte_inventario': '2026-03-31'}}
    response = answer_for('y cuanto tengo en inventario', metrics=metrics,
                         history=[{'role': 'user', 'content': 'cuanto vendi'}])
    for text in ['40 unidades', '$300', '2026-03-31', 'no la suma']:
        assert text in response['answer']
    metrics['moneda_mixta'] = True
    assert '$300' not in answer_for('cuanto vale el inventario', metrics=metrics)['answer']


@pytest.mark.parametrize('question', ['cuentas por cobrar', 'cuenta', 'clientela', 'deben'])
def test_valid_receivables_words_are_not_changed_by_typo_correction(question):
    assert normalize_query(question) == question


@pytest.mark.parametrize('question', [
    'cuota de almacenamiento', 'error 507', 'espacio lleno', 'cuantos archivos puedo guardar',
    'cuantosarchivospuedoguardar', 'cuatnosarchivospuedoguardar', 'cuantosarchibospuedoguardar',
    'cuantosarchivospuedosubir', 'cuotadealmacenamiento', 'cuota de almacenamieto',
    'cuantoespaciotengo', 'espaciolleno', 'limite de almacenamiento',
])
def test_storage_quota_answers_are_not_financial_loan_advice(question):
    answer = answer_for(question)
    assert answer['matched_key'] == 'storage_quota'
    assert 'sin borrar' in answer['answer']
    assert 'duplicados' in answer['answer']


@pytest.mark.parametrize('followup', ['Y que hago', 'Entonces lo retiro', 'Y que hago antes de dejar de invertir en uno', 'Pruebo marketing'])
def test_product_decision_without_evidence_still_offers_bounded_guidance(followup):
    metrics = sales_metrics()
    question = 'Que productos llevan meses sin vender'
    first = answer_for(question, metrics=metrics)
    history = [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': first['answer']}]
    answer = answer_for(followup, metrics=metrics, history=history)
    assert answer['matched_key'] == 'metric_product_activity_guidance'
    assert answer['confidence'] == 'medium'
    for word in ['stock', 'estacional', 'costos completos', 'falta evidencia']:
        assert word in answer['answer']
    assert 'Producto Azul' not in answer['answer']
    unrelated = answer_for('cuanto vendi en enero', metrics=metrics, history=history)
    assert unrelated['matched_key'] != 'metric_product_activity_guidance'


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
    monkeypatch.setattr(assistant, 'monotonic', lambda: 120.0)
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


@pytest.mark.parametrize('previous', ['cuanto tengo en inventario', 'cuanto me deben mis clientes'])
@pytest.mark.parametrize('question', [
    'y eso es plata disponible para gastar?',
    'y eso es dinero disponible?',
    'y eso es efectivo disponible?',
    'puedo gastar eso?',
    'puedo gastarlo?',
    'yesoesplatadisponibleparagastar',
])
def test_noncash_balance_followup_never_becomes_spending_money(previous, question):
    response = answer_for(question, metrics=sales_metrics(), history=[
        {'role': 'user', 'content': previous},
        {'role': 'assistant', 'content': 'Saldo publicado: $300.'},
    ])
    assert response['matched_key'] == 'conversation_balance_not_cash'
    assert 'caja y bancos' in response['answer']
    assert '$300' not in response['answer']


@pytest.mark.parametrize('question', [
    'el inventario es plata disponible?',
    'las cuentas por cobrar son dinero para gastar?',
    'puedo gastar el valor de mi stock?',
])
def test_explicit_balance_cash_distinction_does_not_need_history(question):
    response = answer_for(question)
    assert response['matched_key'] == 'conversation_balance_not_cash'


def test_cash_followup_does_not_intercept_new_stock_or_payment_questions():
    history = [{'role': 'user', 'content': 'cuanto tengo en inventario'}]
    for question in ['y cuantos productos tengo?', 'y cuanto vendi en efectivo?', 'como puedo pagar el plan?']:
        response = answer_for(question, metrics=sales_metrics(), history=history)
        assert response['matched_key'] != 'conversation_balance_not_cash'


def test_income_cash_availability_followup_still_explains_distinction():
    response = answer_for('y eso es plata disponible?', metrics=sales_metrics(), history=[
        {'role': 'user', 'content': 'cuantos ingresos tengo'},
    ])
    assert response['matched_key'] == 'conversation_financial_distinction'


@pytest.mark.parametrize('word', ['plata', 'gastar', 'gastarlo', 'gastado'])
def test_spending_vocabulary_is_not_rewritten(word):
    assert normalize_query(word) == word
