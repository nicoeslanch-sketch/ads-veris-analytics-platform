from copy import deepcopy
import json

import pandas as pd
import pytest

from app.engine.product_patterns import product_patterns
from app.engine.metrics import compute_metrics
from app.support_knowledge import answer_for
from app.routes.assistant import BotRequest


def history_frame():
    rows = []
    for year in (2024, 2025):
        for month in range(1, 13):
            for day in (1, pd.Period(f'{year}-{month:02}', freq='M').days_in_month):
                rows.append(('001', 'Regalo', f'{year}-{month:02}-{day:02}', 500 if month == 12 else 10))
                rows.append(('002', 'Permanente', f'{year}-{month:02}-{day:02}', 100))
    frame = pd.DataFrame(rows, columns=['id_producto', 'producto', 'fecha', 'monto'])
    frame['id_venta'] = ['V' + str(i) for i in range(len(frame))]
    return frame


def patterns(frame):
    dates = pd.to_datetime(frame.fecha)
    return product_patterns(frame.id_producto, frame.producto, dates, frame.monto,
                            complete_months=[str(m) for m in pd.period_range('2024-01', '2025-12', freq='M')])


def test_recurring_peaks_are_independently_reconciled_and_not_forecasts():
    frame = history_frame()
    before = deepcopy(frame)
    result = patterns(frame)
    assert result['anos_comparables'] == ['2024', '2025']
    assert len(result['picos_recurrentes']) == 1
    peak = result['picos_recurrentes'][0]
    assert peak['id'] == '001' and peak['mes'] == 12
    assert peak['evidencia'] == [{'ano': year, 'mes': 12, 'ventas_positivas': 1000., 'participacion_pct': round(1000 / 1220 * 100, 1)} for year in ['2024', '2025']]
    assert sum(point['ventas_netas'] for row in result['series'] for point in row['valores']) == frame.monto.sum()
    pd.testing.assert_frame_equal(frame, before)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('mode', ['single_year', 'missing_month', 'unknown_date', 'changed_peak', 'same_name'])
def test_does_not_invent_repetition_or_merge_product_names(mode):
    frame = history_frame()
    if mode == 'single_year':
        frame = frame[frame.fecha.str.startswith('2024')]
    elif mode == 'missing_month':
        frame = frame[~frame.fecha.str.startswith('2025-02')]
    elif mode == 'unknown_date':
        frame.loc[0, 'fecha'] = None
    elif mode == 'changed_peak':
        frame.loc[(frame.id_producto == '001') & frame.fecha.str.startswith('2025-11'), 'monto'] = 10000
    else:
        frame.loc[frame.fecha.str.startswith('2025') & (frame.id_producto == '001'), 'id_producto'] = '003'
    assert patterns(frame)['picos_recurrentes'] == []


def test_returns_remain_net_and_do_not_erase_positive_sales():
    frame = history_frame()
    frame.loc[len(frame)] = ('001', 'Regalo', '2025-12-31', -2000, 'DEV1')
    result = patterns(frame)
    row = next(row for row in result['series'] if row['id'] == '001')['valores'][-1]
    assert row == {'mes': '2025-12', 'ventas_netas': -1000., 'ventas_positivas': 1000.}
    assert result['picos_recurrentes'][0]['mes'] == 12


def test_metrics_integration_and_filtered_scope():
    frame = history_frame()
    result = compute_metrics(frame)
    assert result['patrones_productos']['total_picos'] == 1
    filtered = compute_metrics(frame, date_from='2025-01-15', date_to='2025-12-31')
    assert filtered['patrones_productos']['anos_comparables'] == []
    assert filtered['patrones_productos']['picos_recurrentes'] == []


def test_long_conversation_keeps_data_and_cleaning_topics_distinct():
    metrics = compute_metrics(history_frame())
    BotRequest(message='hola', metrics=metrics)
    history = []
    turns = [
        ('que productos tienen estacionalidad', 'Regalo'),
        ('y debo dejar de comprar fuera de temporada', 'No recomiendo retirar'),
        ('que picos recurrentes hay en diciembre', '2024'),
        ('y en enero', 'No se detecto'),
        ('y en febrero', 'No se detecto'),
        ('estacionalidad en 2020', 'no tiene doce meses'),
        ('el proximo ano seguro sera igual en temporada', 'no garantiza'),
        ('estacionalidad del producto Permanente', 'No se detecto'),
        ('y en diciembre', 'No se detecto'),
        ('que productos tienen estacionalidad', 'Regalo'),
        ('y el producto Permanente en diciembre', 'No se detecto'),
        ('y en diciembre del 2025', 'No se detecto'),
        ('estacionalidad del producto Inventado', 'No puedo identificar'),
        ('y en diciembre', 'No puedo identificar'),
        ('que grafico me ayuda a decidir', 'Pregunta de analisis'),
        ('como elegir un grafico', 'Pregunta de analisis'),
        ('que son los valores atipicos', 'no necesariamente un error'),
        ('puedo rellenar nulos', 'desconocido'),
        ('que pasa con los ceros a la izquierda', '0012'),
        ('que es el separador decimal', 'UF'),
        ('diferencia entre limpieza y estandarizacion', 'roles'),
        ('quiero ayuda de un humano', 'No he enviado ninguna solicitud'),
        ('que productos tienen estacionalidad', 'Regalo'),
        ('gracias', 'De nada'),
    ]
    for question, expected in turns:
        result = answer_for(question, metrics=metrics, history=history[-12:])
        assert expected.casefold() in result['answer'].casefold(), (question, result)
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': result['answer']}]


@pytest.mark.parametrize('question', ['quetienenestacionalidad', 'que productos tienen estacionalidd', 'picosrecurrentes', 'queproductostienenestacionalidad'])
def test_seasonality_typos(question):
    result = answer_for(question, metrics=compute_metrics(history_frame()))
    assert result['matched_key'] == 'metric_product_patterns_observed', result


def test_empty_context_does_not_certify_seasonality():
    result = answer_for('que productos tienen estacionalidad', metrics={'moneda': 'UF'})
    assert result['matched_key'] == 'metric_product_patterns_missing'


@pytest.mark.parametrize('question,key', [('cerosalaizquierda', 'cleaning_ids'),
    ('valores atipcios', 'cleaning_outliers'), ('separador decimal', 'cleaning_decimal'),
    ('rellenar nulos', 'cleaning_null_zero'), ('picos recurrentes del id 001', 'metric_product_patterns_observed')])
def test_cleaning_and_product_typo_language(question, key):
    result = answer_for(question, metrics=compute_metrics(history_frame()))
    assert result['matched_key'] == key, result


def test_malformed_peak_does_not_crash_or_invent_a_claim():
    result = answer_for('estacionalidad', metrics={'patrones_productos': {
        'picos_recurrentes': [{'id': '001', 'nombre': 'A', 'mes': 99, 'evidencia': [{}]}], 'series': [{}]}})
    assert result['matched_key'] == 'metric_product_patterns_none'


def test_pattern_payload_is_bounded_without_changing_population():
    frame = pd.concat([history_frame().assign(id_producto=str(i)) for i in range(100)], ignore_index=True)
    result = patterns(frame)
    assert result['productos_revisados'] == 100
    assert len(result['series']) <= 12
    assert len(result['picos_recurrentes']) <= 8


@pytest.mark.parametrize('nested', [False, True])
def test_bot_rejects_invalid_nested_pattern_context(nested):
    value = {'series': [{'id': '001', 'valores': 'bad'}]}
    metrics = {'analisis_negocio': {'conciliacion': {'patrones_productos': value}}} if nested else {'patrones_productos': value}
    with pytest.raises(ValueError):
        BotRequest(message='estacionalidad', metrics=metrics)
