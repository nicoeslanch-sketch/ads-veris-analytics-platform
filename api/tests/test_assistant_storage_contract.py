import pytest

from app.support_knowledge import answer_for
from tests.assistant_scenarios import sales_metrics


@pytest.mark.parametrize('question,key,part', [
    ('caducan mis archivos', 'file_retention', 'sin borrado automatico'),
    ('caducanmisarchivos', 'file_retention', 'cinco archivos'),
    ('retenciondearchivos', 'file_retention', '60 dias'),
    ('mi cuenta inactiva', 'file_retention', 'modo de revision'),
    ('descargueunzip', 'download_audit_zip', 'manifest'),
    ('csvvieneenzip', 'download_audit_zip', 'auditoria'),
    ('zip en vez de csv', 'download_audit_zip', 'Descomprimelo'),
])
def test_storage_answers_do_not_fall_through_to_sales(question, key, part):
    reply = answer_for(question, metrics=sales_metrics())
    assert reply['matched_key'] == key, reply
    assert part in reply['answer'] and '$600' not in reply['answer']


def test_conversation_keeps_expiry_erasure_download_and_recovery_separate():
    history = []
    for question, key in [
        ('caducanmisarchivos', 'file_retention'),
        ('y si no entro', 'file_retention'),
        ('quiero eliminar mi cuenta', 'privacy_erasure'),
        ('ya lo borraste', 'privacy_erasure'),
        ('descargueunzip', 'download_audit_zip'),
        ('olvide mi contrasena', 'password_recovery'),
        ('y no me llega el correo', 'password_recovery'),
        ('necesito hablar con un humano', 'human_support'),
        ('csvvieneenzip', 'download_audit_zip'),
        ('retenciondearchivos', 'file_retention'),
        ('y es un respaldo', 'file_retention'),
    ]:
        reply = answer_for(question, metrics=sales_metrics(), history=history[-12:])
        assert reply['matched_key'] == key, (question, reply)
        assert not any(claim in reply['answer'].lower() for claim in ('he borrado', 'te envie un correo', 'tu respaldo esta listo'))
        history.extend([dict(role='user', content=question), dict(role='assistant', content=reply['answer'])])
