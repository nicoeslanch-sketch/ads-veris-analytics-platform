"""Conversational account support must distinguish recovery, MFA and erasure."""

import pytest

from app.support_knowledge import answer_for


@pytest.mark.parametrize('question,key,required', [
    ('olvide mi contrasena', 'password_recovery', 'correo'),
    ('como recupero mi clave', 'password_recovery', 'correo'),
    ('olvide mi password', 'password_recovery', 'correo'),
    ('olvidecontrasena', 'password_recovery', 'correo'),
    ('recuperarcontrasena', 'password_recovery', 'correo'),
    ('no llega el correo de recuperacion', 'password_recovery', 'spam'),
    ('necesito autenticador para entrar', 'mfa_optional', 'opcional'),
    ('necesito autentificador para entrar', 'mfa_optional', 'opcional'),
    ('necesito autentcador para entrar', 'mfa_optional', 'opcional'),
    ('la autenticacion de dos pasos es obligatoria', 'mfa_optional', 'administrador'),
    ('que app uso para escanear el QR', 'mfa_optional', 'Authenticator'),
    ('google authenticator es obligatorio', 'mfa_optional', 'opcional'),
    ('perdi mi autenticador', 'mfa_recovery', 'soporte'),
    ('no tengo el codigo de dos pasos', 'mfa_recovery', 'soporte'),
    ('perdielautenticador', 'mfa_recovery', 'soporte'),
    ('perdielautentcador', 'mfa_recovery', 'soporte'),
    ('cerrar sesion borra mis archivos', 'session_logout', 'no elimina'),
    ('cerre sesion pero mi token funciona', 'session_logout', 'sesion'),
    ('cerrarsesion', 'session_logout', 'no elimina'),
])
def test_account_help_routes(question, key, required):
    reply = answer_for(question, metrics={'total_ingresos': 669700})
    assert reply['matched_key'] == key, reply
    assert required.lower() in reply['answer'].lower()
    assert '669700' not in reply['answer']


def test_long_account_conversation_tracks_topic_without_claiming_actions():
    history = []
    turns = [
        ('necesito autenticador para entrar', 'mfa_optional'),
        ('y para mis clientes es obligatorio', 'mfa_optional'),
        ('perdi mi autenticador', 'mfa_recovery'),
        ('lo puedes quitar tu', 'mfa_recovery'),
        ('olvide mi contrasena', 'password_recovery'),
        ('y no me llega el correo', 'password_recovery'),
        ('cerrar sesion borra mis archivos', 'session_logout'),
        ('quiero eliminar mi cuenta', 'privacy_erasure'),
        ('ya lo borraste', 'privacy_erasure'),
        ('borrar mis datos duplicados', 'duplicates'),
    ]
    for question, key in turns:
        reply = answer_for(question, history=history)
        assert reply['matched_key'] == key, (question, reply)
        assert not any(claim in reply['answer'].lower() for claim in (
            'he borrado', 'ya borre', 'he desactivado', 'te envie un correo',
        ))
        history.extend([{'role': 'user', 'content': question},
                        {'role': 'assistant', 'content': reply['answer']}])


@pytest.mark.parametrize('question', ['mi clave bancaria', 'te envio mi cvv', 'guardar tarjeta'])
def test_recovery_help_does_not_capture_payment_secrets(question):
    assert answer_for(question)['matched_key'] == 'privacy_card_data'
