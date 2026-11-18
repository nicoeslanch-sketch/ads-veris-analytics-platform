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
