import pytest

from app.support_knowledge import answer_for
from tests.assistant_scenarios import sales_metrics


@pytest.mark.parametrize('question,key', [
    ('cuantos usuarios pueden usar la plataforma al mismo tiempo', 'platform_capacity'),
    ('cuantosusuariospuedenusarlaplataforma', 'platform_capacity'),
    ('cuantosusauriospuedenusarlaplataforma', 'platform_capacity'),
    ('cuantas personas al mismo tiempo', 'platform_capacity'),
    ('cuantos usuarios soporta', 'platform_capacity'),
    ('usuarios simultaneoss', 'platform_capacity'),
    ('la capacidad depende de Render?', 'platform_capacity'),
    ('si reinicia el servidor pierdo la limpieza', 'queue_recovery'),
    ('reinicio del servidor', 'queue_recovery'),
    ('reinico del servidor', 'queue_recovery'),
    ('si se interrumpe el proceso que pasa', 'queue_recovery'),
    ('la cola hace la limpieza mas rapida', 'queue_speed'),
    ('que hace la cola', 'queue_speed'),
    ('cola de prosesamiento', 'queue_speed'),
    ('coladeprocesamiento', 'queue_speed'),
    ('la cola afecta la limpieza?', 'queue_correctness'),
    ('la cola elimina duplicados?', 'queue_correctness'),
    ('la cola afecta la descarga?', 'queue_correctness'),
    ('sigue limpiando igual?', 'queue_correctness'),
])
@pytest.mark.parametrize('metrics', [None, sales_metrics()])
def test_operational_questions_are_not_financial_ratios(question, key, metrics):
    result = answer_for(question, metrics=metrics)
    assert result['matched_key'] == key, result
    assert 'valor presente' not in result['answer'].lower()
    if key == 'platform_capacity':
        assert 'No hay una cifra certificada' in result['answer']
        assert 'no significa un único usuario' in result['answer']
    elif key == 'queue_recovery':
        assert 'no se continúa desde una celda exacta' in result['answer']
    elif key == 'queue_speed':
        assert 'no añade CPU' in result['answer']
    else:
        assert 'No omite pasos' in result['answer']
        assert 'no se promete' in result['answer']


def test_capacity_conversation_can_change_back_to_data():
    history = []
    for question, key in [
        ('cuantos usuarios soporta', 'platform_capacity'),
        ('que hace la cola', 'queue_speed'),
        ('y eso cambia la limpieza', 'queue_correctness'),
        ('y puedo descargar bien', 'queue_correctness'),
        ('si reinicia el servidor pierdo la limpieza', 'queue_recovery'),
        ('la cola afecta la descarga', 'queue_correctness'),
        ('cuantos archivos puedo guardar', 'storage_quota'),
    ]:
        result = answer_for(question, metrics=sales_metrics(), history=history)
        assert result['matched_key'] == key
        history.extend([{'role': 'user', 'content': question}, {'role': 'assistant', 'content': result['answer']}])
    result = answer_for('cuanto vendi en enero', metrics=sales_metrics(), history=history)
    assert '$100' in result['answer']
    assert result['matched_key'].startswith('metric_')


def test_queue_followup_does_not_hide_a_duplicate_count():
    result = answer_for('y cuantos duplicados hay', metrics=sales_metrics(), history=[
        {'role': 'user', 'content': 'que hace la cola'},
    ])
    assert result['matched_key'] == 'metric_quality'
    assert '1 duplicados' in result['answer']
