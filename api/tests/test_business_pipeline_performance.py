from copy import deepcopy
from unittest.mock import Mock

import pandas as pd
import pytest

from app.analysis_jobs import JobCancelled
from app.routes import pipeline


@pytest.fixture
def prepared():
    frames = {
        'Ventas': pd.DataFrame({'Fecha': pd.to_datetime(['2026-01-01', '2026-02-01']),
            'ID Venta': ['V1', 'V2'], 'SKU Producto': ['P1', 'P2'], 'Cantidad': [2, 1],
            'Monto Venta': [500, 300], 'Canal': ['Web', 'Local']}),
        'Costos_Productos': pd.DataFrame({'SKU Producto': ['P1', 'P2'], 'Costo Unitario': [100, 200]}),
    }
    mappings = {'Ventas': {'fecha': 'Fecha', 'monto': 'Monto Venta', 'producto': 'SKU Producto',
                           'cantidad': 'Cantidad', 'canal': 'Canal'},
                'Costos_Productos': {'producto': 'SKU Producto', 'costo': 'Costo Unitario'}}
    results = {name: {'resumen': {'calidad_despues': 100}, 'problemas': {}, 'correcciones': {}, 'avisos': []}
               for name in frames}
    scope = {'mode': 'append_join', 'active_sheet': 'Ventas', 'sheets': list(frames),
             'append_sheets': ['Ventas'], 'join': {'left_sheet': 'Ventas', 'right_sheet': 'Costos_Productos',
             'left_keys': ['SKU Producto'], 'right_keys': ['SKU Producto'], 'type': 'left'}}
    return frames, mappings, results, scope


@pytest.mark.parametrize('date_from,date_to,filters', [
    (None, None, None), ('2026-01-01', '2026-01-31', None), (None, None, {'canal': 'Web'}),
])
def test_reuses_business_result_with_identical_inputs_and_filters(prepared, monkeypatch, date_from, date_to, filters):
    frames, mappings, results, scope = prepared
    before = deepcopy(prepared)
    expected = pipeline.analyze_business_workbook(frames, mappings, results, date_from=date_from, date_to=date_to, filters=filters)
    analyzer = Mock(wraps=pipeline.analyze_business_workbook)
    monkeypatch.setattr(pipeline, 'analyze_business_workbook', analyzer)
    result = pipeline._metrics_multi_from_processed('synthetic', *prepared, date_from, date_to, filters)
    analyzer.assert_called_once_with(frames, mappings, results, date_from=date_from, date_to=date_to, filters=filters)
    assert result['analisis_negocio'] == expected
    assert result['analysis_provenance']['rows'] == 2
    for name in frames:
        pd.testing.assert_frame_equal(frames[name], before[0][name])
    assert (mappings, results, scope) == before[1:]


@pytest.mark.parametrize('analysis', [None, {'perfil': 'servicios_tecnicos', 'evidence': 'synthetic'}])
def test_unsupported_and_service_profiles_are_not_evaluated_twice(prepared, monkeypatch, analysis):
    analyzer = Mock(return_value=analysis)
    monkeypatch.setattr(pipeline, 'analyze_business_workbook', analyzer)
    result = pipeline._metrics_multi_from_processed('synthetic', *prepared, None, None)
    assert analyzer.call_count == 1
    if analysis is None:
        assert 'analisis_negocio' not in result
    else:
        assert result['analisis_negocio'] == analysis
        assert result['analysis_provenance']['mode'] == 'service_network'


def test_collection_profile_outside_business_mode_is_still_computed(prepared, monkeypatch):
    frames, mappings, results, scope = prepared
    scope = {**scope, 'mode': 'join'}
    analyzer = Mock(return_value={'perfil': 'cobranza'})
    monkeypatch.setattr(pipeline, 'has_collection_dashboard_profile', lambda _: True)
    monkeypatch.setattr(pipeline, 'analyze_business_workbook', analyzer)
    result = pipeline._metrics_multi_from_processed('synthetic', frames, mappings, results, scope, None, None)
    assert analyzer.call_count == 1
    assert result['analisis_negocio'] == {'perfil': 'cobranza'}


def test_cancellation_after_business_phase_skips_remaining_metrics(prepared, monkeypatch):
    def progress(phase, completed, total):
        if phase == 'metrics':
            raise JobCancelled()
    metrics = Mock(side_effect=AssertionError('Cancelled work must not calculate metrics'))
    monkeypatch.setattr(pipeline, 'report_job_progress', progress)
    monkeypatch.setattr(pipeline, 'compute_metrics', metrics)
    with pytest.raises(JobCancelled):
        pipeline._metrics_multi_from_processed('synthetic', *prepared, None, None)
    assert not metrics.called


def test_automatic_relationship_discovery_computes_business_only_once(prepared, monkeypatch):
    frames, mappings, results, _ = prepared
    monkeypatch.setattr(pipeline, '_processed_manifest_frames', lambda *args: (frames, mappings, results))
    analyzer = Mock(wraps=pipeline.analyze_business_workbook)
    monkeypatch.setattr(pipeline, 'analyze_business_workbook', analyzer)
    manifest = {'hojas': [{'nombre': name, 'procesar': True, 'mapping': mappings[name]} for name in frames]}
    result = pipeline._relationships_sync('synthetic.xlsx', b'', manifest, focus={'sheets': ['Ventas']})
    assert analyzer.call_count == 1
    assert result['metrics']['kpis']['ingresos_totales']['valor'] == 800
    assert result['metrics']['analisis_negocio']['estado_resultados']['costo_venta_conocido'] == 400


@pytest.mark.parametrize('analysis', [None, {'perfil': 'servicios_tecnicos', 'evidence': 'synthetic'}])
def test_unfiltered_detection_result_including_none_is_reused(prepared, monkeypatch, analysis):
    analyzer = Mock(side_effect=AssertionError('Already computed in this request'))
    monkeypatch.setattr(pipeline, 'analyze_business_workbook', analyzer)
    result = pipeline._metrics_multi_from_processed('synthetic', *prepared, None, None,
                                                    _unfiltered_business=analysis)
    assert not analyzer.called
    assert result.get('analisis_negocio') == analysis


@pytest.mark.parametrize('start,end,filters', [
    ('2026-01-01', None, None), (None, '2026-01-31', None), (None, None, {'canal': 'Web'}),
])
def test_unfiltered_result_cannot_override_requested_period_or_filter(prepared, monkeypatch, start, end, filters):
    analyzer = Mock(wraps=pipeline.analyze_business_workbook)
    monkeypatch.setattr(pipeline, 'analyze_business_workbook', analyzer)
    result = pipeline._metrics_multi_from_processed('synthetic', *prepared, start, end, filters,
                                                    _unfiltered_business={'wrong': True})
    assert analyzer.call_count == 1
    assert result['analisis_negocio'] != {'wrong': True}
