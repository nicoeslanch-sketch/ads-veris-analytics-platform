from copy import deepcopy

import pandas as pd
import pytest

from app.engine.purchase_documents import analyze_purchase_documents
from app.engine.business import analyze_business_workbook
from app.engine.mapping import resolve_mapping
from app.support_knowledge import answer_for


@pytest.fixture
def frames():
    return {
        'Compras': pd.DataFrame({'IDCompra': [' C01 ', 'C1', 'C2'],
            'FechaCompra': ['2026-01-10', '2026-02-10', '2026-02-11'],
            'EstadoCompra': ['Recibida', 'Pendiente', 'Anulada'],
            'IDProveedor': ['S1', 'S2', 'S1']}),
        'Detalle_Compras': pd.DataFrame({'IDCompra': ['c01', 'C01', 'C1', 'C2'],
            'Linea': [1, 2, 1, 1], 'IDProducto': ['P1', 'P2', 'P1', 'P2'],
            'Cantidad': [2, 3, 1, 1], 'CostoUnitarioCompra_CLP': [10, 20, 30, 999]}),
    }


def analyze(frames, **options):
    options.setdefault('currency', 'CLP')
    options.setdefault('period_mask', lambda dates: dates.notna())
    return analyze_purchase_documents(frames, **options)


def test_values_detail_without_multiplying_header_and_keeps_sources_unchanged(frames):
    original = deepcopy(frames)
    result = analyze(frames)
    assert result['valor'] == 110
    assert result['estado'] == 'available'
    assert result['cobertura_datos_pct'] == 100
    assert result['lineas_valorizadas'] == 3
    assert result['fuentes'] == ['Compras', 'Detalle_Compras']
    assert 'IVA' in ' '.join(result['advertencias'])
    for name, frame in original.items():
        pd.testing.assert_frame_equal(frame, frames[name])


def test_repeated_identical_header_does_not_repeat_purchase_lines(frames):
    frames['Compras'] = pd.concat([frames['Compras'], frames['Compras'].iloc[[0]]], ignore_index=True)
    result = analyze(frames)
    assert result['valor'] == 110
    assert result['relacion']['copias_cabecera_no_multiplicadas'] == 1


@pytest.mark.parametrize('field,value', [('EstadoCompra', 'Anulada'), ('FechaCompra', '2026-03-01'),
    ('IDProveedor', 'S9')])
def test_conflicting_headers_never_choose_first(frames, field, value):
    duplicate = frames['Compras'].iloc[[0]].copy()
    duplicate[field] = value
    frames['Compras'] = pd.concat([frames['Compras'], duplicate], ignore_index=True)
    result = analyze(frames)
    assert result['valor'] == 30
    assert result['estado'] == 'partial'
    assert result['relacion']['cabeceras_conflictivas'] == 2


@pytest.mark.parametrize('field,value', [('FechaCompra', '2026-03-01'), ('EstadoCompra', 'Anulada'),
    ('IDProveedor', 'S9')])
def test_explicit_detail_metadata_conflict_blocks_only_affected_lines(frames, field, value):
    frames['Detalle_Compras'][field] = [value, None, None, None]
    result = analyze(frames)
    assert result['valor'] == 90
    assert result['estado'] == 'partial'
    assert result['relacion']['atributos_conflictivos'] == 1


def test_orphan_line_is_partial_and_keeps_location(frames):
    frames['Detalle_Compras'].loc[0, 'IDCompra'] = 'MISSING'
    frames['Detalle_Compras'].attrs['adsveris_source_rows'] = [8, 9, 10, 11]
    result = analyze(frames)
    assert result['valor'] == 90
    assert result['cobertura_datos_pct'] == 66.67
    assert result['relacion']['huerfanas'] == 1
    assert result['relacion']['ubicaciones'] == [{'hoja': 'Detalle_Compras', 'fila': 8, 'clave': 'missing'}]


@pytest.mark.parametrize('value', [None, -1, float('inf'), 'error'])
@pytest.mark.parametrize('field', ['Cantidad', 'CostoUnitarioCompra_CLP'])
def test_invalid_inputs_are_not_zero(frames, field, value):
    frames['Detalle_Compras'][field] = frames['Detalle_Compras'][field].astype(object)
    frames['Detalle_Compras'].loc[0, field] = value
    result = analyze(frames)
    assert result['valor'] == 90
    assert result['estado'] == 'partial'
    assert result['cobertura_datos_pct'] == 66.67


def test_observed_zero_is_available_but_all_missing_is_not(frames):
    frames['Detalle_Compras']['CostoUnitarioCompra_CLP'] = 0
    assert analyze(frames)['valor'] == 0
    frames['Detalle_Compras']['CostoUnitarioCompra_CLP'] = None
    result = analyze(frames)
    assert result['valor'] is None and result['estado'] == 'unavailable'


def test_exact_line_copies_are_preserved_and_warned(frames):
    frames['Detalle_Compras'] = pd.concat([frames['Detalle_Compras'], frames['Detalle_Compras'].iloc[[0]]], ignore_index=True)
    result = analyze(frames)
    assert result['valor'] == 130
    assert result['estado'] == 'partial'
    assert any('copias repetidas' in warning for warning in result['advertencias'])


def test_conflicting_line_identity_is_excluded_not_arbitrarily_deduplicated(frames):
    copy = frames['Detalle_Compras'].iloc[[0]].copy()
    copy['Cantidad'] = 5
    frames['Detalle_Compras'] = pd.concat([frames['Detalle_Compras'], copy], ignore_index=True)
    result = analyze(frames)
    assert result['valor'] == 90
    assert result['estado'] == 'partial'


@pytest.mark.parametrize('month,expected', [(1, 80), (2, 30), (3, None)])
def test_period_comes_from_header_not_from_unfiltered_detail(frames, month, expected):
    result = analyze(frames, period_mask=lambda dates: dates.dt.month.eq(month))
    assert result['valor'] == expected


@pytest.mark.parametrize('status', [None, '', 'desconocida'])
def test_unknown_status_is_not_treated_as_non_cancelled(frames, status):
    frames['Compras'].loc[0, 'EstadoCompra'] = status
    result = analyze(frames)
    assert result['valor'] == 30
    assert result['estado'] == 'partial'


def test_missing_detail_warns_even_when_line_coverage_is_complete(frames):
    frames['Compras'].loc[3] = ['C3', '2026-02-11', 'Recibida', 'S1']
    result = analyze(frames)
    assert result['cabeceras_sin_detalle'] == 1
    assert result['estado'] == 'partial'
    assert result['cobertura_datos_pct'] == 100


def test_period_and_detail_can_span_several_sheets(frames):
    frames['Compras_Otro'] = frames['Compras'].iloc[1:].copy()
    frames['Compras'] = frames['Compras'].iloc[:1].copy()
    frames['Detalle_Otro'] = frames['Detalle_Compras'].iloc[2:].copy()
    frames['Detalle_Compras'] = frames['Detalle_Compras'].iloc[:2].copy()
    result = analyze(frames)
    assert result['valor'] == 110
    assert len(result['fuentes']) == 4


def test_unknown_dimensional_scope_is_not_replaced_with_global(frames):
    result = analyze(frames, dimensional_filter=True)
    assert result['valor'] is None and result['estado'] == 'unavailable'


def test_uf_header_cost_is_not_summed_as_pesos(frames):
    frames['Detalle_Compras'] = frames['Detalle_Compras'].rename(columns={'CostoUnitarioCompra_CLP': 'CostoUnitarioCompra_UF'})
    assert analyze(frames)['valor'] is None
    assert analyze(frames, currency='UF')['valor'] == 110


def test_explicit_currency_on_header_is_used_when_cost_has_no_unit(frames):
    frames['Detalle_Compras'] = frames['Detalle_Compras'].rename(columns={'CostoUnitarioCompra_CLP': 'CostoUnitarioCompra'})
    frames['Compras']['Moneda'] = 'UF'
    assert analyze(frames, currency='UF')['valor'] == 110
    assert analyze(frames)['valor'] is None


def test_currency_conflict_between_header_and_cost_blocks_sum(frames):
    frames['Compras']['Moneda'] = 'UF'
    assert analyze(frames, currency='UF')['valor'] is None
    assert analyze(frames)['valor'] is None


def test_business_indicator_and_bot_do_not_call_valuation_net_or_paid(frames):
    frames['Ventas'] = pd.DataFrame({'IDVenta': ['V1'], 'FechaVenta': ['2026-02-10'],
        'IDProducto': ['P1'], 'Cantidad': [1], 'Monto Venta': [100]})
    mappings = {name: resolve_mapping(list(frame.columns), None) for name, frame in frames.items()}
    result = analyze_business_workbook(frames, mappings, {})
    indicators = {item['id']: item for group in result['catalogo_indicadores']['categorias'] for item in group['indicadores']}
    assert indicators['compras_netas']['valor'] is None
    assert indicators['compras_valorizadas']['valor'] == 110
    assert indicators['compras_valorizadas']['fuentes'] == ['Compras', 'Detalle_Compras']
    assert indicators['compras_valorizadas']['periodo_actual'] == {'desde': '2026-01-10', 'hasta': '2026-02-10'}
    metrics = {'moneda': 'CLP', 'analisis_negocio': result}
    history = []
    for question, snippets in [
        ('cuanto compre', ['Compras valorizadas', '$110', 'no como importe neto', '2026-01-10 a 2026-02-10']),
        ('y eso esta pagado', ['conciliar los pagos']),
        ('mis compras netas', ['no hay un importe validado']),
        ('y el total', ['Compras netas', 'no hay un importe validado']),
        ('y eso esta pagado', ['conciliar los pagos']),
        ('cuanto compre al proveedor S1', ['ese periodo o segmento']),
        ('mis compras en general', ['Compras valorizadas', '$110']),
    ]:
        answer = answer_for(question, metrics=metrics, history=history)
        assert all(part in answer['answer'] for part in snippets), (question, answer)
        history += [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer['answer']}]


@pytest.mark.parametrize('word', ['pagado', 'pagados', 'pagada', 'pagadas', 'pague', 'pasado'])
def test_payment_words_are_not_corrected_into_time_words(word):
    from app.language_normalization import normalize_query
    assert normalize_query(word) == word


def test_unspecified_currency_defaults_to_clp_without_crashing(frames):
    frames['Detalle_Compras'] = frames['Detalle_Compras'].rename(columns={'CostoUnitarioCompra_CLP': 'CostoUnitarioCompra'})
    assert analyze(frames)['valor'] == 110


def test_sum_overflow_is_unavailable_not_infinite(frames):
    frames['Detalle_Compras']['Cantidad'] = 1.0
    frames['Detalle_Compras']['CostoUnitarioCompra_CLP'] = 1e308
    result = analyze(frames)
    assert result['valor'] is None
    assert result['estado'] == 'unavailable'
    assert any('rango numerico' in warning for warning in result['advertencias'])


@pytest.mark.parametrize('sheet', ['Compras', 'Detalle_Compras'])
def test_empty_purchase_sheet_is_safe(frames, sheet):
    frames[sheet] = frames[sheet].iloc[:0].copy()
    assert analyze(frames)['valor'] is None


def test_all_missing_header_status_is_safe(frames):
    frames['Compras']['EstadoCompra'] = None
    assert analyze(frames)['valor'] is None


def test_duplicate_cost_columns_are_not_guessed(frames):
    frames['Detalle_Compras']['CostoUnitarioCompra_UF'] = 1
    assert analyze(frames) is None


@pytest.mark.parametrize('sheet', ['Compras', 'Detalle_Compras'])
def test_ambiguous_currency_columns_are_not_ignored(frames, sheet):
    frames[sheet]['Moneda'] = 'CLP'
    frames[sheet]['Currency'] = 'UF'
    assert analyze(frames) is None


def test_business_date_filter_is_applied_to_purchase_headers(frames):
    frames['Ventas'] = pd.DataFrame({'IDVenta': ['V1'], 'FechaVenta': ['2026-02-10'],
        'IDProducto': ['P1'], 'Cantidad': [1], 'Monto Venta': [100]})
    mappings = {name: resolve_mapping(list(frame.columns), None) for name, frame in frames.items()}
    result = analyze_business_workbook(frames, mappings, {}, date_from='2026-02-01', date_to='2026-02-28')
    value = result['operacion']['compras_valorizadas']
    assert value['valor'] == 30
    assert value['periodo_actual'] == {'desde': '2026-02-10', 'hasta': '2026-02-10'}
