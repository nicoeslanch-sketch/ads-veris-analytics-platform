from copy import deepcopy

import pytest

from app.support_knowledge import answer_for
from tests.test_assistant_numeric_oracle import oracle_metrics


def ask(question, metrics, history):
    reply = answer_for(question, metrics=metrics, history=history[-12:])
    history.extend([{'role': 'user', 'content': question},
                    {'role': 'assistant', 'content': reply['answer']}])
    return reply


def test_pair_followups_rank_only_selected_groups_and_reset(oracle_metrics):
    history = []
    ask('cuanto vendi en Retail y Ferreteria', oracle_metrics, history)
    ask('y la diferencia entre ambos', oracle_metrics, history)
    reply = ask('cual vende menos de esos dos', oracle_metrics, history)
    assert '$200' in reply['answer'] and 'Ferreteria' in reply['answer']
    assert 'Distribucion' not in reply['answer']
    reply = ask('y cual vende mas de esos dos', oracle_metrics, history)
    assert '$350' in reply['answer'] and 'Retail' in reply['answer']
    reply = ask('mis ingresos en general', oracle_metrics, history)
    assert '$600' in reply['answer']
    reply = ask('cual vende menos de esos dos', oracle_metrics, history)
    assert not reply['matched_key'] or not reply['matched_key'].endswith('_selected_rank')


def test_combined_share_uses_net_total_not_partial_top(oracle_metrics):
    metrics = deepcopy(oracle_metrics)
    metrics['por_categoria'] = [r for r in metrics['por_categoria'] if r['nombre'] != 'Retail']
    history = []
    ask('cuanto suman Distribucion y Ferreteria', metrics, history)
    reply = ask('y que porcentaje son del total', metrics, history)
    assert '41,7%' in reply['answer'] and '$250 / $600' in reply['answer']
    assert '100%' not in reply['answer']
    assert 'netas' in reply['answer']


@pytest.mark.parametrize('missing', ['share', 'total', 'zero', 'negative', 'mixed_currency'])
def test_share_does_not_invent_a_denominator(oracle_metrics, missing):
    metrics = deepcopy(oracle_metrics)
    if missing == 'share':
        for row in metrics['por_categoria']:
            row.pop('participacion_neta_pct', None)
    elif missing == 'total':
        metrics['kpis'].pop('ingresos_totales')
    elif missing in {'zero', 'negative'}:
        metrics['kpis']['ingresos_totales']['valor'] = 0 if missing == 'zero' else -600
    else:
        metrics['moneda_mixta'] = True
    reply = answer_for('que porcentaje son Distribucion y Ferreteria del total', metrics=metrics)
    assert '41,7%' not in reply['answer']
    assert not reply['matched_key'].endswith('_share')


def test_positive_units_do_not_return_net_units(oracle_metrics):
    reply = answer_for('cuantas unidades positivas vendi', metrics=oracle_metrics)
    assert '65 unidades' in reply['answer'] and '60 unidades' not in reply['answer']
    oracle_metrics['kpis'].pop('unidades_detalle')
    reply = answer_for('cuantas unidades positivas vendi', metrics=oracle_metrics)
    assert reply['matched_key'] == 'metric_positive_units_unavailable'


def test_unspecified_percentage_does_not_assume_combined_share(oracle_metrics):
    history = []
    ask('cuanto vendi en Retail y Ferreteria', oracle_metrics, history)
    reply = ask('y el porcentaje', oracle_metrics, history)
    assert reply['matched_key'].endswith('_share_clarify')
    assert '91,7%' not in reply['answer']


def test_selected_rank_includes_ties(oracle_metrics):
    for row in oracle_metrics['por_categoria']:
        if row['nombre'] in {'Ferreteria', 'Distribucion'}:
            row['ingresos'] = 50
    reply = answer_for('cual vende menos Ferreteria y Distribucion', metrics=oracle_metrics)
    assert 'empate' in reply['answer'] and 'Ferreteria' in reply['answer'] and 'Distribucion' in reply['answer']
