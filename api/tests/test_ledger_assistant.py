import pytest
from pydantic import ValidationError

from app.engine.relational_ledger import analyze_relational_ledger
from app.metric_assistant import answer_metrics_question
from app.routes.assistant import BotRequest
from app.support_knowledge import answer_for
from tests.test_relational_ledger import workbook_frames


@pytest.fixture
def metrics():
    return {'analisis_negocio': {'conciliacion': analyze_relational_ledger(workbook_frames())},
            'kpis': {'ingresos_totales': {'valor': 999999}}}


@pytest.mark.parametrize('question,expected', [
    ('Cuanto vendi', '$200'), ('mis ingresos totales', '$200'), ('ventasnetas', '$200'),
    ('Cuantas ventas hubo', '2'), ('cuantas ventas anuladas', '1'), ('mi utilidad bruta', '$120'),
    ('mis costos', '$80'), ('mi margen', '60%'), ('cuanto me deben', '$238'),
    ('cxc', '$238'), ('cuentas por pagar', '$0'), ('mi inventario', '8'),
    ('valor del inventario', '$320'), ('unidades vendidas', '3'),
    ('ventas antes de devoluciones', '$300'), ('notas de credito', '$100'),
    ('ventas de enero 2025', '$100'), ('ventas 2026', '$100'),
    ('ventas de febrero 2026', '$-100'), ('utilidad de 2026', '$60'),
    ('mi ticket promedio', '$150'), ('el producto mas rentable', '$120'),
    ('la sucursal con mas ventas', '$200'), ('mejor mes', '2026-01'),
    ('peor mes', '2026-02'), ('que tal esta mi negocio', '$200'),
    ('mi saldo bancario', 'balance completo'), ('mi liquidez', 'balance completo'),
    ('ventas enero', 'filtro de fechas'), ('ventas de 2024', 'filtro de fechas'),
    ('gastos 2026', 'filtro de fechas'), ('producto principal 2026', 'filtro de fechas'),
    ('productos sin ventas', 'estacionalidad'), ('que moneda tienen mis datos', 'CLP'),
])
def test_conversation_uses_ledger_not_legacy_totals(metrics, question, expected):
    answer = answer_metrics_question(question, metrics)
    assert answer is not None
    assert expected in answer['answer']
    assert '999.999' not in answer['answer']


def test_followup_changes_period_and_human_support_remains_reachable(metrics):
    history = []
    for question, expected in [('cuanto vendi', '$200'), ('y en 2025', '$100'),
                               ('producto mas rentable', '$120'), ('como contacto a un humano', 'Abre Ayuda')]:
        answer = answer_for(question, metrics=metrics, history=history)
        assert expected in answer['answer']
        history.extend([{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer['answer']}])


def test_blocked_ledger_never_leaks_older_estimates(metrics):
    metrics['analisis_negocio']['conciliacion'] = {'available': False, 'advertencias': ['ID conflictivo']}
    answer = answer_metrics_question('mis ingresos', metrics)
    assert 'bloqueada' in answer['answer']
    assert '999.999' not in answer['answer']


def test_long_conversation_switches_intents_without_dragging_old_values(metrics):
    history = []
    turns = [('cuanto vendi', '$200'), ('y en 2025', '$100'), ('y en 2026', '$100'),
        ('mi utilidad bruta', '$120'), ('y mis costos', '$80'), ('y mi margen', '60%'),
        ('y mi utilidad', '$120'), ('mi ticket promedio', '$150'), ('cuantas ventas emitidas', '2'),
        ('cuentas por cobrar', '$238'), ('y las cuentas por pagar', '$0'), ('valor inventario', '$320'),
        ('que producto es mas rentable', '$120'), ('y el menos rentable', '$120'),
        ('mejor mes', '2026-01'), ('y el peor', '2026-02'), ('ventas antes de devoluciones', '$300'),
        ('notas de credito', '$100'), ('productos sin ventas', 'estacionalidad'),
        ('entonces que hago', 'precio'), ('mi saldo bancario', 'balance completo'),
        ('que conclusion sacas de mi negocio', '$200'), ('como consigo ayuda humana', 'Abre Ayuda'),
        ('gracias', 'De nada')]
    for question, expected in turns:
        answer = answer_for(question, metrics=metrics, history=history[-12:])
        assert expected in answer['answer'], (question, answer)
        history.extend([{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer['answer']}])


@pytest.mark.parametrize('key,value', [('kpis', []), ('mensual', ['bad']), ('periodo', 'bad'), ('productos', 'bad')])
def test_rejects_malformed_ledger_context(key, value):
    with pytest.raises(ValidationError):
        BotRequest(message='ventas', metrics={'analisis_negocio': {'conciliacion': {key: value}}})
