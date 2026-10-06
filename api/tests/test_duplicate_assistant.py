"""Conversation regressions from duplicate-impact questions, with synthetic data."""

import pytest

from app.support_knowledge import answer_for
from tests.assistant_scenarios import purchase_metrics, sales_metrics


@pytest.mark.parametrize('question', [
    'y esos duplicados cambian mis ingresos?',
    'los duplicados afectan las ventas?',
    'las filas repetidas inflan mis ingresos?',
    'los duplciados cambian el margen?',
    'losduplicadosafectanmisventas',
    'cuanto venderia sin duplicados?',
    'cuanto compre sin duplicados?',
    'cual seria mi utilidad si quito los duplicados?',
])
@pytest.mark.parametrize('currency', ['CLP', 'UF', 'USD'])
def test_impact_never_subtracts_row_count_from_money(question, currency):
    metrics = purchase_metrics()
    metrics['moneda'] = currency
    answer = answer_for(question, metrics=metrics)
    assert answer['matched_key'] == 'metric_duplicate_impact', answer
    assert '1 duplicado' in answer['answer']
    assert 'No tengo calculado' in answer['answer']
    assert 'no equivale a un importe' in answer['answer']
    assert '$' not in answer['answer'] and 'UF ' not in answer['answer']
    assert len(answer['answer']) < 950


@pytest.mark.parametrize('question', [
    'los duplicados afectan mis ingresos en enero?',
    'cuanto vendi sin duplicados en Sur?',
    'los duplicados cambian las ventas de hoy?',
    'los duplicados afectan las ventas de la sucursal Central?',
    'cuantos duplicados hay en enero?',
    'cuantos duplicados tengo en Sur?',
])
def test_scope_does_not_reuse_global_count_or_sales(question):
    answer = answer_for(question, metrics=sales_metrics())
    assert answer['matched_key'] == 'metric_duplicate_scope', answer
    assert 'ese periodo o segmento' in answer['answer']
    assert '1 duplicado' not in answer['answer'] and '$' not in answer['answer']


@pytest.mark.parametrize('counts,phrase', [
    ({'detectados': 3, 'eliminados': 0, 'conservados': 0}, '0 duplicados conservados'),
    ({'detectados': 3, 'eliminados': 3}, '0 duplicados conservados'),
    ({'detectados': 3, 'eliminados': 1}, '2 duplicados conservados'),
    ({}, 'No tengo un conteo'),
    ({'conservados': None}, 'No tengo un conteo'),
    ({'conservados': True}, 'No tengo un conteo'),
    ({'conservados': -1}, 'No tengo un conteo'),
    ({'conservados': 1.5}, 'No tengo un conteo'),
    ({'conservados': 'nan'}, 'No tengo un conteo'),
])
def test_duplicate_count_keeps_zero_and_unknown_distinct(counts, phrase):
    metrics = sales_metrics()
    metrics['duplicados'] = counts
    answer = answer_for('los duplicados afectan mis ingresos?', metrics=metrics)
    assert phrase in answer['answer'], answer


def test_quality_keeps_explicit_zero_instead_of_reconstructing_it():
    metrics = sales_metrics()
    metrics['duplicados'] = {'detectados': 3, 'eliminados': 0, 'conservados': 0}
    answer = answer_for('cuantos duplicados tengo', metrics=metrics)
    assert 'se conservaron 0' in answer['answer']
    assert 'totales visibles s' not in answer['answer']


def test_long_conversation_does_not_claim_deletion_or_inherit_stale_topic():
    history = []
    turns = [
        ('cuantos duplicados hay', 'metric_quality', '1 duplicados'),
        ('y esos cambian mis ingresos?', 'metric_duplicate_impact', 'No tengo calculado'),
        ('y cuanto quedaria si los quito?', 'metric_duplicate_impact', 'no equivale a un importe'),
        ('entonces conviene borrarlos?', 'metric_duplicate_review', 'No conviene borrar'),
        ('como los compruebo?', 'metric_duplicate_review', 'ID'),
        ('el mismo ID basta?', 'metric_duplicate_review', 'conflicto'),
        ('borralos', 'metric_duplicate_action', 'Este chat no elimina'),
        ('ya lo hiciste?', 'metric_duplicate_action', 'Este chat no elimina'),
        ('cuanto vendi', 'metric_income', '$600'),
        ('y en febrero', 'metric_month_value', '$200'),
    ]
    for question, key, phrase in turns:
        answer = answer_for(question, metrics=sales_metrics(), history=history[-12:])
        assert answer['matched_key'] == key, (question, answer)
        assert phrase in answer['answer'], (question, answer)
        history += [{'role': 'user', 'content': question},
                    {'role': 'assistant', 'content': answer['answer']}]


@pytest.mark.parametrize('question', [
    'cuanto vendi en febrero', 'cuanto compre', 'que producto se vende mas',
    'como recuperar mi contrasena', 'si conservo los duplicados puedo descargar igual?',
    'la limpieza elimina duplicados automaticamente?',
])
def test_other_intents_are_not_replaced_by_duplicate_advice(question):
    history = [{'role': 'user', 'content': 'cuantos duplicados hay'},
               {'role': 'assistant', 'content': 'Se conserva 1 duplicado.'}]
    answer = answer_for(question, metrics=purchase_metrics(), history=history)
    assert not answer['matched_key'].startswith('metric_duplicate_'), answer


def test_duplicate_period_followup_is_not_monthly_sales():
    history = []
    for question in ['cuantos duplicados hay en enero', 'y en febrero', 'y en marzo']:
        answer = answer_for(question, metrics=sales_metrics(), history=history)
        assert answer['matched_key'] == 'metric_duplicate_scope', answer
        assert '$' not in answer['answer']
        history += [{'role': 'user', 'content': question},
                    {'role': 'assistant', 'content': answer['answer']}]
