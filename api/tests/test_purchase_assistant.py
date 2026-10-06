from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.language_normalization import normalize_query
from app.support_knowledge import answer_for
from app.routes.assistant import BotRequest
from tests.assistant_scenarios import purchase_metrics


def indicator(metrics, index=0):
    return metrics['analisis_negocio']['catalogo_indicadores']['categorias'][0]['indicadores'][index]


@pytest.mark.parametrize('question', ['cuanto compre', 'cuantocompre', 'cuatno compre',
    'mis compras netas', 'cuanto compramos', 'cual es el importe de compras'])
def test_purchase_questions_use_published_contract_and_partial_coverage(question):
    response = answer_for(question, metrics=purchase_metrics())
    assert response['matched_key'] == 'metric_purchases'
    assert '$120' in response['answer'] and '50%' in response['answer']
    assert 'parcial' in response['answer'] and 'Compras' in response['answer']
    assert '$999.999' not in response['answer'] and '$600' not in response['answer']


@pytest.mark.parametrize('state,value', [('unavailable', None), ('blocked', 120),
    ('available', None), ('available', float('nan')), ('partial', float('inf'))])
def test_missing_blocked_and_invalid_purchase_amounts_are_not_zero(state, value):
    metrics = purchase_metrics()
    indicator(metrics).update(estado=state, valor=value)
    response = answer_for('cuanto compre', metrics=metrics)
    assert response['matched_key'] == 'metric_purchases_unavailable'
    assert '$' not in response['answer'] and 'cero' in response['answer']


@pytest.mark.parametrize('currency,formatted', [('CLP', '$0'), ('UF', 'UF 0'), ('USD', 'US$0')])
def test_observed_zero_is_available_in_original_currency(currency, formatted):
    metrics = purchase_metrics()
    metrics['moneda'] = currency
    indicator(metrics).update(estado='available', valor=0, cobertura_datos_pct=100, advertencias=[])
    response = answer_for('cuanto compre', metrics=metrics)
    assert response['matched_key'] == 'metric_purchases'
    assert formatted in response['answer'] and 'parcial' not in response['answer']


@pytest.mark.parametrize('question', ['cuanto compre en enero', 'compras en Sur',
    'compras del proveedor Acme', 'fletes de la sucursal Norte', 'compras del producto P01',
    'compras de 2025', 'compras hoy', 'compras sin devoluciones', 'compras entre 100 y 200',
    'cuanto compre a Acme', 'compras para Cliente B'])
def test_unpublished_purchase_scope_never_uses_sales_or_global_total(question):
    response = answer_for(question, metrics=purchase_metrics())
    assert response['matched_key'] == 'metric_purchases_scope_unavailable'
    assert '$' not in response['answer']


@pytest.mark.parametrize('question', ['cuantas compras tengo', 'cuantos proveedores tengo en compras',
    'promedio de compras', 'cual es la mayor compra', 'compras brutas', 'IVA de compras',
    'unidades compradas', 'compras pagadas', 'porcentaje de fletes', 'compara compras y ventas'])
def test_other_purchase_measures_do_not_return_net_total(question):
    response = answer_for(question, metrics=purchase_metrics())
    assert response['matched_key'] == 'metric_purchases_measure_unavailable'
    assert '$' not in response['answer']


@pytest.mark.parametrize('flag', ['moneda_mixta', 'datos_monetarios_disponibles'])
def test_incompatible_currency_never_publishes_purchase_amount(flag):
    metrics = purchase_metrics()
    metrics[flag] = flag == 'moneda_mixta'
    response = answer_for('cuanto compre', metrics=metrics)
    assert '$120' not in response['answer'] and 'moneda' in response['answer'].lower()


def test_purchase_followups_preserve_scope_reset_and_topic_changes():
    history = []
    turns = [
        ('cuantocompre', 'metric_purchases', '$120'),
        ('y los fletes', 'metric_purchase_freight', '$10'),
        ('y eso es dinero pagado', 'metric_purchases_not_cash', 'pagos'),
        ('cuanto compre al proveedor Acme', 'metric_purchases_scope_unavailable', 'segmento'),
        ('y los fletes', 'metric_purchases_scope_unavailable', 'segmento'),
        ('ahora las compras en general', 'metric_purchases', '$120'),
        ('y los fletes', 'metric_purchase_freight', '$10'),
        ('cuanto vendi', 'metric_income', '$600'),
    ]
    for question, key, expected in turns:
        response = answer_for(question, metrics=purchase_metrics(), history=history[-12:])
        assert response['matched_key'] == key, (question, response)
        assert expected in response['answer'], (question, response)
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': response['answer']}]


def test_freight_context_does_not_survive_unrelated_question():
    response = answer_for('y el total', metrics=purchase_metrics(), history=[
        {'role': 'user', 'content': 'cuanto compre'},
        {'role': 'user', 'content': 'cuanto vendi'},
    ])
    assert response['matched_key'] != 'metric_purchases'


@pytest.mark.parametrize('question', ['y cuanto me deben', 'y el margen', 'y cuantos clientes tengo',
                                    'y mi stock', 'y cuanto vendi'])
def test_purchase_context_does_not_capture_a_different_metric(question):
    response = answer_for(question, metrics=purchase_metrics(), history=[
        {'role': 'user', 'content': 'cuanto compre'},
    ])
    assert response['matched_key'] not in {'metric_purchases', 'metric_purchase_freight'}


def test_purchase_reply_does_not_modify_source_metrics():
    metrics = purchase_metrics()
    original = deepcopy(metrics)
    answer_for('cuanto compre', metrics=metrics)
    assert metrics == original


@pytest.mark.parametrize('question', ['como compro un plan', 'comprar ADS Coins',
    'deberia comprar mas inventario', 'que son las compras', 'como descargo compras'])
def test_platform_and_decision_questions_are_not_purchase_totals(question):
    assert answer_for(question, metrics=purchase_metrics())['matched_key'] != 'metric_purchases'


def test_purchase_vocabulary_preserves_verb_and_splits_joined_question():
    assert normalize_query('compré') == 'compre'
    assert normalize_query('cuantocompre') == 'cuanto compre'


@pytest.mark.parametrize('catalog', [[], {'categorias': {}}, {'categorias': [None]},
    {'categorias': [{'indicadores': 'invalid'}]}, {'categorias': [{'indicadores': [None]}]},
    {'categorias': [{'indicadores': [{'advertencias': 'invalid'}]}]},
    {'categorias': [{'indicadores': [{'fuentes': [None]}]}]},
])
def test_malformed_purchase_context_is_rejected_before_answering(catalog):
    with pytest.raises(ValidationError):
        BotRequest(message='cuanto compre', metrics={'analisis_negocio': {'catalogo_indicadores': catalog}})


@pytest.mark.parametrize('catalog', [None, {'categorias': None}, {'categorias': [{'indicadores': None}]}])
def test_nullable_purchase_catalog_reports_unavailable(catalog):
    metrics = {'analisis_negocio': {'catalogo_indicadores': catalog}}
    request = BotRequest(message='cuanto compre', metrics=metrics)
    assert answer_for(request.message, metrics=request.metrics)['matched_key'] == 'metric_purchases_unavailable'
