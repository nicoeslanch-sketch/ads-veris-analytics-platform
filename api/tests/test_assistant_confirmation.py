import pytest

from app.support_knowledge import answer_for
from tests.assistant_scenarios import sales_metrics


@pytest.mark.parametrize('question', [
    'como confirmo mi correo', 'no me llega el correo de confirmacion',
    'reenviarconfirmacion', 'como confirmar mi email',
    'el enlace de confirmacion vencio', 'correo no confirmado',
    'no me llega el correo de confirmacoin',
])
def test_confirmation_help_is_not_financial_or_missing_file(question):
    result = answer_for(question, metrics=sales_metrics())
    assert result['matched_key'] == 'signup_confirmation', result
    assert 'Reenviar confirmacion' in result['answer']
    assert 'no puedo activar tu cuenta' in result['answer']


def test_confirmation_followups_release_context_on_financial_and_password_topics():
    history = []
    for question, expected in [
        ('como confirmo mi correo', 'signup_confirmation'),
        ('y si no llega', 'signup_confirmation'),
        ('quiero recuperar mi contrasena', 'password_recovery'),
        ('cuanto vendi', None),
        ('necesito un humano', 'human_support'),
    ]:
        result = answer_for(question, metrics=sales_metrics(), history=history)
        if expected:
            assert result['matched_key'] == expected, result
        else:
            assert result['matched_key'] not in {'signup_confirmation', 'password_recovery'}
        history.extend([{'role': 'user', 'content': question},
                        {'role': 'assistant', 'content': result['answer']}])


@pytest.mark.parametrize('question', ['confirmar ventas', 'correo del cliente', 'confirmar mis costos'])
def test_other_confirmation_words_do_not_trigger_account_help(question):
    assert answer_for(question, metrics=sales_metrics())['matched_key'] != 'signup_confirmation'


def test_confirmation_context_survives_short_delivery_followups_and_releases():
    history = []
    for question in ['como confirmo mi correo', 'no me ha llegado nada', 'no recibi nada',
                     'no llego', 'donde lo reenvio', 'lo intente otra vez']:
        result = answer_for(question, metrics=sales_metrics(), history=history)
        assert result['matched_key'] == 'signup_confirmation', (question, result)
        history.extend([{'role': 'user', 'content': question},
                        {'role': 'assistant', 'content': result['answer']}])
    for question in ['mis ventas otra vez', 'no llego a mi meta', 'cuanto vendi', 'necesito un humano']:
        result = answer_for(question, metrics=sales_metrics(), history=history)
        assert result['matched_key'] != 'signup_confirmation', (question, result)


@pytest.mark.parametrize('previous', ['confirmar ventas', 'quiero recuperar mi contrasena'])
def test_unrelated_context_does_not_become_signup_confirmation(previous):
    history = [{'role': 'user', 'content': previous}]
    for question in ['no me ha llegado nada', 'donde lo reenvio', 'otra vez']:
        result = answer_for(question, metrics=sales_metrics(), history=history)
        assert not result or result['matched_key'] != 'signup_confirmation'
