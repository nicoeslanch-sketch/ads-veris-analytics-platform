from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.routes.assistant import BotRequest
from app.support_knowledge import answer_for
from app.language_normalization import normalize_query


@pytest.fixture
def metrics():
    return {
        'moneda': 'CLP', 'kpis': {
            'ingresos_totales': {'valor': 999999}, 'ganancia_neta': {'valor': -888888},
            'margen_utilidad_pct': {'valor': -81.1}, 'gastos_totales': {'valor': 777777},
            'cobertura_costos': {'pct': 96},
        },
        'analisis_negocio': {'perfil': 'comercial', 'estado_resultados': {
            'ventas_observadas': 1200, 'ventas_pareadas': 1000, 'costo_venta_conocido': 700,
            'utilidad_bruta': 300, 'margen_bruto_pct': 30, 'cobertura_costos_pct': 65.8,
            'gastos_operacionales': 50, 'resultado_operacional': 250, 'margen_operacional_pct': 25,
            'utilidad_certificable': 90, 'margen_certificable_pct': 20,
            'cobertura_costos_certificable_pct': 40,
        }},
    }


@pytest.mark.parametrize('question,expected', [
    ('cuantossonmisingresostotales', ['$1.200', 'Ingresos no equivale']),
    ('y mi utilidad?', ['$300', '30%', '65,8%', 'bruta']),
    ('cual es mi margen', ['30%', '65,8%']),
    ('cobertura de costos', ['65,8%']),
    ('cual es mi costo total', ['$700', '65,8%']),
    ('cuales son mis gastos', ['$50', 'operacionales']),
    ('que conclusion sacas', ['$1.200', '$300', '30%', '65,8%']),
    ('mi utilidad operacional', ['$250', '25%']),
    ('mi utilidad certificable', ['$90', '20%', '40%']),
    ('mi utilidad neta', ['No hay una utilidad neta publicable']),
])
def test_business_finances_use_dashboard_base_not_generic_kpis(metrics, question, expected):
    before = deepcopy(metrics)
    answer = answer_for(question, metrics=metrics)['answer']
    for part in expected:
        assert part in answer
    for other_base in ('$999.999', '$-888.888', '$777.777', '-81,1%', '96%'):
        assert other_base not in answer
    assert metrics == before


@pytest.mark.parametrize('missing', [None, float('nan'), float('inf')])
def test_missing_profit_never_falls_back_or_becomes_zero(metrics, missing):
    metrics['analisis_negocio']['estado_resultados']['utilidad_bruta'] = missing
    metrics['analisis_negocio']['estado_resultados']['margen_bruto_pct'] = missing
    answer = answer_for('mi utilidad', metrics=metrics)['answer']
    assert 'no disponible' in answer
    assert '$0' not in answer and '$-888.888' not in answer


@pytest.mark.parametrize('profit', [0, -50])
def test_zero_and_negative_business_profit_are_preserved(metrics, profit):
    metrics['analisis_negocio']['estado_resultados']['utilidad_bruta'] = profit
    answer = answer_for('mi utilidad', metrics=metrics)['answer']
    assert f'${profit}' in answer


def test_uf_and_conversation_keep_business_scope(metrics):
    metrics['moneda'] = 'UF'
    history = []
    for question, expected in [('mis ingresos', 'UF 1.200'), ('y mi utilidad?', 'UF 300'),
                               ('y el margen?', '30%'), ('cobertura de costos', '65,8%')]:
        answer = answer_for(question, metrics=metrics, history=history)['answer']
        assert expected in answer
        assert '$' not in answer
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer}]


@pytest.mark.parametrize('flag', ['moneda_mixta', 'datos_monetarios_disponibles'])
def test_blocked_monetary_data_remains_blocked(metrics, flag):
    metrics[flag] = flag == 'moneda_mixta'
    answer = answer_for('mi utilidad', metrics=metrics)['answer']
    assert 'No hay importes publicables' in answer
    assert '$300' not in answer


def test_filtered_values_and_absent_expenses_never_use_generic_totals(metrics):
    metrics['analisis_negocio']['estado_resultados'] = {'ventas_observadas': 42}
    assert '$42' in answer_for('mis ingresos', metrics=metrics)['answer']
    answer = answer_for('mis gastos', metrics=metrics)['answer']
    assert 'no disponibles' in answer and '$777.777' not in answer


def test_plain_sheet_keeps_its_own_kpis(metrics):
    metrics.pop('analisis_negocio')
    assert '$-888.888' in answer_for('mi utilidad', metrics=metrics)['answer']


def test_business_statement_container_is_validated():
    with pytest.raises(ValidationError):
        BotRequest(message='mi utilidad', metrics={'analisis_negocio': {'estado_resultados': [1]}})


@pytest.mark.parametrize('question', ['que producto tiene mayor utilidad', 'que mes tuvo mejor margen'])
def test_business_totals_are_not_substituted_for_a_requested_breakdown(metrics, question):
    answer = answer_for(question, metrics=metrics)['answer']
    assert '$300' not in answer and '30%' not in answer
    assert 'desglose' in answer


def test_operational_qualifier_is_not_split_into_other_words():
    assert normalize_query('miutilidadoperacional') == 'mi utilidad operacional'
