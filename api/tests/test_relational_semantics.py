import pandas as pd
import pytest

from app.engine.document_model import MATCH_COLUMN, prepare_document_lines
from app.engine.mapping import detect_column_roles
from app.support_knowledge import answer_for
from app.engine.loader import _classify_sheet_sample


def test_suffix_ids_are_never_additive_and_explicit_net_beats_gross():
    assert detect_column_roles(['venta_id', 'neto_documento_clp', 'iva_documento_clp',
                                'total_documento_clp']) == {'monto': 'neto_documento_clp'}
    assert detect_column_roles(['compra_id', 'neto_clp', 'total_bruto_clp']) == {'monto': 'neto_clp'}
    mapping = detect_column_roles(['detalle_venta_id', 'venta_id', 'producto_id', 'cantidad',
        'costo_unitario_neto_clp', 'costo_linea_clp', 'neto_linea_clp'])
    assert mapping['costo'] == 'costo_linea_clp'
    assert 'categoria' not in mapping


def test_relations_link_prefix_and_suffix_identifiers_of_the_same_entity():
    from app.engine.multi_sheet import _candidate_pairs
    left = pd.DataFrame({'IDCliente': ['C1'], 'IDVendedor': ['E1']})
    right = pd.DataFrame({'cliente_id': ['C1'], 'empleado_id': ['E1']})
    pairs = _candidate_pairs(left, right)
    assert ('IDCliente', 'cliente_id') in pairs
    assert ('IDVendedor', 'empleado_id') in pairs
    assert ('IDCliente', 'empleado_id') not in pairs


def test_catalog_does_not_offer_key_only_purchase_dashboard():
    from app.engine.relationships import detect_relationship_catalog
    frames = {'Compras': pd.DataFrame({'compra_id': ['B1', 'B2'], 'proveedor_id': ['P1', 'P1']}),
              'Proveedores': pd.DataFrame({'proveedor_id': ['P1'], 'razon_social': ['Proveedor']})}
    assert not detect_relationship_catalog(frames)['relationships']


@pytest.mark.parametrize('name', ['NOTAS_CREDITO', 'Notas de crédito', 'Nota débito'])
def test_credit_notes_are_data_not_user_instructions(name):
    sample = pd.DataFrame([['nota_credito_id', 'neto_creditado_clp'], ['N1', '100']])
    assert _classify_sheet_sample(name, sample)['clasificacion'] == 'datos'
    assert _classify_sheet_sample('Notas', sample)['clasificacion'] == 'auxiliar'


def test_monetary_header_is_enriched_but_collections_and_credits_are_not_headers():
    frames = {
        'VENTAS': pd.DataFrame({'venta_id': [' V01 '], 'fecha_venta': ['2025-01-01'],
            'estado': ['Emitida'], 'neto_documento_clp': [100], 'empleado_id': ['E01']}),
        'DET_VENTAS': pd.DataFrame({'detalle_venta_id': ['L1', 'L2'], 'venta_id': ['v01', 'V01'],
            'producto_id': ['P1', 'P2'], 'cantidad': [1, 1], 'neto_linea_clp': [60, 40]}),
        'COBROS': pd.DataFrame({'venta_id': ['V01'], 'fecha_cobro': ['2025-02-01'], 'importe_bruto_clp': [80]}),
        'NOTAS_CREDITO': pd.DataFrame({'venta_id': ['V01'], 'fecha_nota': ['2025-03-01'], 'neto_creditado_clp': [20]}),
    }
    model = prepare_document_lines(frames, {})
    assert model.headers == {'VENTAS'}
    assert model.details == {'DET_VENTAS'}
    enriched = model.frames['DET_VENTAS']
    assert enriched[MATCH_COLUMN].tolist() == [1, 1]
    assert enriched.neto_linea_clp.sum() == 100
    assert 'neto_documento_clp' not in enriched
    assert enriched.IDVendedor.tolist() == ['e01', 'e01']
    assert 'FechaVenta' not in frames['DET_VENTAS']


@pytest.mark.parametrize('question', [
    'como puedo conseguir ayuda de un humano', 'necesito que una persona me atienda',
    'quiero hablar con soporte', 'comopuedoconseguirayudadeunhumano',
    'quiero contactarme con un asesor', 'necesito ayuda humana',
])
def test_human_support_is_available_even_with_financial_history(question):
    result = answer_for(question, metrics={'kpis': {'ingresos_totales': {'valor': 100}}},
                        history=[{'role': 'user', 'content': 'cuanto vendi'}])
    assert result['matched_key'] == 'human_support'
    assert 'Ayuda' in result['answer']
    assert 'No he enviado' in result['answer']
def test_dictionary_header_is_not_replaced_by_first_id_row():
    import pandas as pd
    from app.engine.loader import _detect_header_row
    raw = pd.DataFrame([['hoja', 'columna', 'tipo_logico', 'rol', 'referencia_o_regla'],
                        ['SUCURSALES', 'sucursal_id', 'ID/texto', 'PK', '']])
    assert _detect_header_row(raw) == 0


def test_manual_customer_ticket_counts_documents_not_product_lines():
    from app.engine.relationship_dashboard import build_relationship_dashboard
    from app.engine.relationships import detect_relationship_catalog
    frames = {
        'VENTAS': pd.DataFrame({'venta_id': ['V1'], 'fecha_venta': ['2025-01-01'],
            'estado': ['Emitida'], 'neto_documento_clp': [100], 'cliente_id': ['C1']}),
        'DET_VENTAS': pd.DataFrame({'detalle_venta_id': ['L1', 'L2'], 'venta_id': ['V1', 'V1'],
            'producto_id': ['P1', 'P2'], 'cantidad': [1, 1], 'neto_linea_clp': [60, 40]}),
        'CLIENTES': pd.DataFrame({'cliente_id': ['C1'], 'nombre_cliente': ['Cliente de prueba']}),
    }
    relation = next(r for r in detect_relationship_catalog(frames)['relationships']
                    if r['template'] == 'sales_customers')
    dashboard = build_relationship_dashboard(frames, {}, {}, relation)
    assert dashboard['available']
    assert next(k for k in dashboard['kpis'] if k['id'] == 'ticket')['value'] == 100
