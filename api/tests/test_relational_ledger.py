from copy import deepcopy
import json

import pandas as pd
import pytest

from app.engine.relational_ledger import SCHEMAS, analyze_relational_ledger


def workbook_frames():
    frames = {name: pd.DataFrame(columns=columns) for name, columns in SCHEMAS.items()}
    frames['sales'] = pd.DataFrame({'venta_id': ['V1', 'V2', 'V3'],
        'fecha_venta': ['2025-01-02', '2026-01-02', '2026-01-03'], 'estado': ['Emitida', 'Emitida', 'Anulada'],
        'neto_documento_clp': [100, 200, 300], 'iva_documento_clp': [19, 38, 57], 'total_documento_clp': [119, 238, 357],
        'cliente_id': ['C1', 'C1', 'C2'], 'empleado_id': ['E1', 'E1', 'E1']})
    frames['lines'] = pd.DataFrame({'detalle_venta_id': ['D1', 'D2', 'D3'], 'venta_id': ['V1', 'V2', 'V3'],
        'producto_id': ['P1'] * 3, 'lote_id': ['L1'] * 3, 'cantidad': [1, 2, 3],
        'neto_linea_clp': [100, 200, 300], 'iva_linea_clp': [19, 38, 57], 'total_linea_clp': [119, 238, 357],
        'costo_linea_clp': [40, 80, 120], 'costo_unitario_neto_clp': [40] * 3})
    frames['credits'] = pd.DataFrame({'nota_credito_id': ['N1'], 'venta_id': ['V1'], 'fecha_nota': ['2026-02-01'],
        'neto_creditado_clp': [100], 'iva_creditado_clp': [19], 'total_creditado_clp': [119]})
    frames['returns'] = pd.DataFrame({'detalle_devolucion_id': ['R1'], 'nota_credito_id': ['N1'],
        'detalle_venta_id': ['D1'], 'producto_id': ['P1'], 'lote_id': ['L1'], 'cantidad_devuelta': [1],
        'neto_revertido_clp': [100], 'iva_revertido_clp': [19], 'total_revertido_clp': [119],
        'costo_referencial_revertido_clp': [40], 'reingresa_stock': [True]})
    frames['lots'] = pd.DataFrame({'lote_id': ['L1'], 'producto_id': ['P1'], 'sucursal_id': ['S1'],
        'fecha_entrada': ['2024-12-01'], 'unidades_entrada': [10], 'costo_unitario_neto_clp': [40]})
    frames['products'] = pd.DataFrame({'producto_id': ['P1'], 'nombre_producto': ['Producto de prueba'], 'categoria_id': ['C1']})
    frames['categories'] = pd.DataFrame({'categoria_id': ['C1'], 'nombre_categoria': ['Accesorios']})
    frames['branches'] = pd.DataFrame({'sucursal_id': ['S1'], 'nombre': ['Centro']})
    frames['employees'] = pd.DataFrame({'empleado_id': ['E1'], 'sucursal_id': ['S1'], 'nombre_empleado': ['Equipo uno']})
    return frames


def test_reconciles_without_mutation_and_keeps_credit_in_its_own_period():
    frames = workbook_frames()
    before = deepcopy(frames)
    result = analyze_relational_ledger(frames)
    assert result['available'], result['advertencias']
    assert result['kpis']['ventas_netas'] == 200
    assert result['kpis']['costo_ventas_neto'] == 80
    assert result['kpis']['cuentas_por_cobrar'] == 238
    assert result['kpis']['stock_unidades'] == 8
    assert result['kpis']['inventario_valorizado'] == 320
    assert result['mensual'][-1]['ventas'] == -100
    assert result['mensual'][-1]['mes'] == '2026-02'
    feb = analyze_relational_ledger(frames, date_from='2026-02-01', date_to='2026-02')
    assert feb['kpis']['ventas_netas'] == -100
    assert feb['kpis']['cuentas_por_cobrar'] == 238
    assert feb['kpis']['stock_unidades'] == 8
    assert feb['kpis']['ventas_emitidas'] == 0
    json.dumps(result, allow_nan=False)
    for name in frames:
        pd.testing.assert_frame_equal(before[name], frames[name])


def test_return_does_not_reverse_cost_without_stock_reentry():
    frames = workbook_frames()
    frames['returns']['reingresa_stock'] = False
    result = analyze_relational_ledger(frames)
    assert result['kpis']['costo_ventas_neto'] == 120
    assert result['kpis']['stock_unidades'] == 7


def test_split_collections_do_not_multiply_sales():
    frames = workbook_frames()
    frames['collections'] = pd.DataFrame({'cobro_id': ['P1', 'P2'], 'venta_id': ['V2', 'V2'],
        'fecha_cobro': ['2026-01-10', '2026-02-10'], 'importe_bruto_clp': [50, 100],
        'comision_medio_pago_clp': [1, 2], 'deposito_neto_clp': [49, 98]})
    result = analyze_relational_ledger(frames)
    assert result['kpis']['ventas_netas'] == 200
    assert result['kpis']['cuentas_por_cobrar'] == 88
    assert result['kpis']['depositos_netos'] == 147


@pytest.mark.parametrize('kind,column,value', [('lines', 'venta_id', 'MISSING'),
    ('lines', 'neto_linea_clp', 999), ('returns', 'reingresa_stock', 'tal vez'),
    ('sales', 'fecha_venta', 'invalid'), ('returns', 'detalle_venta_id', 'D2')])
def test_inconsistent_source_blocks_financial_totals(kind, column, value):
    frames = workbook_frames()
    frames[kind][column] = frames[kind][column].astype(object)
    frames[kind].loc[0, column] = value
    result = analyze_relational_ledger(frames)
    assert not result['available']
    assert result['advertencias']
    assert 'kpis' not in result


def test_duplicate_and_control_tables_never_become_a_hidden_source():
    frames = workbook_frames()
    frames['CONTROL_sourcedata'] = frames['sales'].copy()
    result = analyze_relational_ledger(frames)
    assert result['available']
    assert 'CONTROL_sourcedata' not in result['fuentes']
    frames['sales'] = pd.concat([frames['sales'], frames['sales'].iloc[[0]]])
    assert not analyze_relational_ledger(frames)['available']


@pytest.mark.parametrize('kind,column,value', [('returns', 'cantidad_devuelta', 2),
    ('returns', 'costo_referencial_revertido_clp', 500), ('lots', 'fecha_entrada', 'bad'),
    ('lots', 'unidades_entrada', 0), ('credits', 'fecha_nota', '2024-01-01'),
    ('lots', 'sucursal_id', 'missing'), ('products', 'categoria_id', 'missing')])
def test_invalid_balances_and_historical_references_are_not_published(kind, column, value):
    frames = workbook_frames()
    frames[kind][column] = frames[kind][column].astype(object)
    frames[kind].loc[0, column] = value
    result = analyze_relational_ledger(frames)
    assert not result['available']
    assert 'kpis' not in result


def test_unsold_products_have_json_null_not_nan_and_retain_ids():
    frames = workbook_frames()
    frames['products'] = pd.concat([frames['products'], frames['products'].assign(producto_id='P2')])
    frames['lots'] = pd.concat([frames['lots'], frames['lots'].assign(lote_id='L2', producto_id='P2')])
    result = analyze_relational_ledger(frames)
    assert result['available']
    json.dumps(result, allow_nan=False)
    assert result['inventario_lento'][0]['dias_sin_venta'] is None


def test_empty_ledger_blocks_without_crashing():
    frames = {name: frame.iloc[:0] for name, frame in workbook_frames().items()}
    assert not analyze_relational_ledger(frames)['available']


def test_pipeline_uses_same_reconciled_revenue_as_business_panel():
    from app.routes.pipeline import _metrics_multi_from_processed
    from app.engine.mapping import resolve_mapping
    frames = {name: frame for name, frame in workbook_frames().items() if not frame.empty}
    mappings = {name: resolve_mapping(list(frame.columns), None) for name, frame in frames.items()}
    results = {name: {'resumen': {'calidad_despues': 100}} for name in frames}
    scope = {'mode': 'append_join', 'sheets': ['lines', 'products'], 'append_sheets': ['lines'],
        'active_sheet': 'lines', 'join': {'left_sheet': 'lines', 'right_sheet': 'products',
        'left_keys': ['producto_id'], 'right_keys': ['producto_id'], 'type': 'left'}}
    result = _metrics_multi_from_processed('fixture.xlsx', frames, mappings, results, scope, None, None)
    assert result['analisis_negocio']['conciliacion']['kpis']['ventas_netas'] == 200
    assert result['kpis']['ingresos_totales']['valor'] == 200
    assert result['kpis']['ticket_promedio'] == 150


def test_rankings_keep_profit_leaders_outside_revenue_extremes():
    frames = workbook_frames()
    frames['credits'] = frames['credits'].iloc[:0]
    frames['returns'] = frames['returns'].iloc[:0]
    for kind, pk in [('sales', 'venta_id'), ('lines', 'detalle_venta_id'),
                     ('products', 'producto_id'), ('lots', 'lote_id')]:
        rows = []
        for i in range(301):
            row = frames[kind].iloc[[0]].copy()
            row[pk] = f'{kind}{i}'
            if 'venta_id' in row:
                row['venta_id'] = f'sales{i}'
            if 'producto_id' in row:
                row['producto_id'] = f'products{i}'
            if 'lote_id' in row:
                row['lote_id'] = f'lots{i}'
            if kind == 'sales':
                row['neto_documento_clp'] = i + 100
                row['iva_documento_clp'] = 0
                row['total_documento_clp'] = i + 100
            if kind == 'lines':
                row['neto_linea_clp'] = i + 100
                row['iva_linea_clp'] = 0
                row['total_linea_clp'] = i + 100
                row['costo_linea_clp'] = 0 if i == 150 else i + 99
            rows.append(row)
        frames[kind] = pd.concat(rows, ignore_index=True)
    result = analyze_relational_ledger(frames)
    assert result['available'], result['advertencias']
    best = max(result['productos'], key=lambda row: row['utilidad'])
    assert best['id'] == 'products150'
    assert best['utilidad'] == 250
