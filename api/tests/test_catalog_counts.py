import pandas as pd
import pytest

from app.engine.metrics import compute_metrics
from app.support_knowledge import answer_for


def catalog_metrics():
    return compute_metrics(pd.DataFrame({
        'Producto': ['Uno', 'Uno', 'Dos', 'Tres', 'Cuatro'],
        'Categoria': ['Hogar', 'Hogar', 'Oficina', 'Hogar', 'Oficina'],
        'Costo Unitario': [100, 100, 200, 300, 400],
        'Precio Lista': [200, 200, 400, 600, 800],
        'Activo': ['Si', 'Si', 'No', 'desconocido', None],
    }))


def test_catalog_preserves_duplicates_and_publishes_count_grain():
    metrics = catalog_metrics()
    assert metrics['tipo_analisis'] == 'catalogo_productos'
    products = metrics['analisis_productos']
    assert products['productos'] == 4
    assert products['registros'] == 5
    assert products['columna_producto'] == 'Producto'
    assert products['estado_unidad'] == 'registros'
    assert products['activos'] == 2 and products['inactivos'] == 1
    assert products['sin_estado'] == 2
    assert sum(row['productos'] for row in products['categorias']) == 5
    assert products['totales_catalogo_unitario']['costo'] == 1100
    assert metrics['kpis']['ingresos_totales'] is None
    assert any('por fila, no por SKU' in warning for warning in metrics['advertencias'])


@pytest.mark.parametrize('question,expected', [
    ('cuantos productos inactivos tengo', '1 registro inactivo'),
    ('y cuantos estan inactivos', '1 registro inactivo'),
    ('cuantosproductosinactivos', '1 registro inactivo'),
    ('cuantos productos inactvos tengo', '1 registro inactivo'),
    ('y los activos', '2 registros activos'),
    ('estado del catalogo', '2 registros activos; 1 registro inactivo'),
    ('inactivos del catalogo', '1 registro inactivo'),
    ('porcentaje de mis productos inactivos', '1 registro inactivo'),
    ('estado de todos mis productos', '2 registros activos; 1 registro inactivo'),
])
def test_bot_answers_catalog_state_not_generic_summary(question, expected):
    reply = answer_for(question, metrics=catalog_metrics(), history=[{'role': 'user', 'content': 'cuantos productos tengo'}])
    assert reply['matched_key'] == 'metric_catalog_status'
    assert expected in reply['answer']
    assert '2 registros sin estado reconocido' in reply['answer']
    assert 'no prueba que lleve meses sin vender' in reply['answer']


def test_catalog_state_conversation_denominator_is_all_rows_not_unique_products():
    metrics, history = catalog_metrics(), []
    turns = [
        ('cuantos productos inactivos tengo', '1 registro inactivo'),
        ('que porcentaje representa eso', '20%'),
        ('y los activos', '2 registros activos'),
        ('que porcentaje representan', '40%'),
    ]
    for question, expected in turns:
        reply = answer_for(question, metrics=metrics, history=history)
        assert reply['matched_key'] == 'metric_catalog_status'
        assert expected in reply['answer']
        if 'porcentaje' in question:
            assert '5 registros' in reply['answer']
        history.extend([{'role': 'user', 'content': question}, {'role': 'assistant', 'content': reply['answer']}])


@pytest.mark.parametrize('question', [
    'cuantos productos inactivos en enero', 'activos en 2025', 'inactivos hoy',
    'activos en sucursal Sur', 'inactivos de categoria Hogar', 'inactivos en Sur',
    'esta activo el producto Uno', 'producto Uno esta activo',
    'inactivos de Hogar', 'inactivos del Hogar', 'activos para Oficina',
])
def test_catalog_state_does_not_substitute_global_count_for_unknown_scope(question):
    reply = answer_for(question, metrics=catalog_metrics())
    assert reply['matched_key'] == 'metric_catalog_status_scope'
    assert '1 registros' not in reply['answer']


def test_catalog_status_missing_is_not_zero():
    metrics = catalog_metrics()
    metrics['analisis_productos'].update(inactivos=None, registros=None)
    reply = answer_for('porcentaje de productos inactivos', metrics=metrics)
    assert 'No hay un conteo' in reply['answer']
    assert 'No tengo una base completa' in reply['answer']
    assert '0%' not in reply['answer']


def test_catalog_status_zero_is_available():
    metrics = catalog_metrics()
    metrics['analisis_productos']['inactivos'] = 0
    reply = answer_for('porcentaje de productos inactivos', metrics=metrics)
    assert '0 registros inactivos' in reply['answer']
    assert '0%' in reply['answer']


@pytest.mark.parametrize('question', ['que filtros estan activos', 'estado de limpieza', 'estado de mi cuenta', 'que son activos corrientes'])
def test_other_status_questions_do_not_return_product_state(question):
    reply = answer_for(question, metrics=catalog_metrics())
    assert reply['matched_key'] != 'metric_catalog_status'


def test_catalog_state_followup_retains_unknown_scope():
    reply = answer_for('y los activos', metrics=catalog_metrics(), history=[
        {'role': 'user', 'content': 'inactivos en enero'}])
    assert reply['matched_key'] == 'metric_catalog_status_scope'


@pytest.mark.parametrize('previous', ['inactivos de Hogar', 'esta activo el producto Uno'])
def test_catalog_specific_status_followup_does_not_fall_back_to_global(previous):
    reply = answer_for('que porcentaje representa eso', metrics=catalog_metrics(), history=[
        {'role': 'user', 'content': previous}])
    assert reply['matched_key'] == 'metric_catalog_status_scope'


def test_catalog_invalid_denominator_does_not_make_percentage():
    metrics = catalog_metrics()
    metrics['analisis_productos']['registros'] = 1
    reply = answer_for('porcentaje de productos activos', metrics=metrics)
    assert 'No tengo una base completa' in reply['answer']
    assert '200%' not in reply['answer']


@pytest.mark.parametrize('question', [
    'entonces debo dejar de comprar esos productos',
    'debo dejar de comprar productos inactivos',
    'me conviene seguir comprando esos productos',
    'deberia reinvertir en otros productos',
])
def test_catalog_purchase_decision_uses_evidence_requirements_not_generic_counts(question):
    reply = answer_for(question, metrics=catalog_metrics(), history=[
        {'role': 'user', 'content': 'cuantos productos inactivos tengo'},
        {'role': 'assistant', 'content': '1 registro inactivo'},
    ])
    assert reply['matched_key'] == 'metric_catalog_purchase_decision'
    assert 'no justifica dejar de comprar' in reply['answer']
    assert 'ventas por ID' in reply['answer'] and 'stock disponible' in reply['answer']
    assert 'estacionalidad' in reply['answer']
    assert 'El catalogo contiene' not in reply['answer']


def test_subscription_purchase_question_is_not_a_product_recommendation():
    reply = answer_for('deberia comprar el plan analista', metrics=catalog_metrics())
    assert reply['matched_key'] != 'metric_catalog_purchase_decision'
