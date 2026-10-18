"""Product/account questions must not become unrelated financial advice."""

import pytest

from app.language_normalization import normalize_query
from app.support_knowledge import answer_for, rank_articles
from tests.assistant_scenarios import sales_metrics


@pytest.mark.parametrize('question,key,required', [
    ('no me llega el correo para recuperar la cuenta', 'password_recovery', 'spam'),
    ('no me llega el corero para recuperar mi cuenta', 'password_recovery', 'spam'),
    ('como recupero mi cuenta', 'password_recovery', 'correo'),
    ('quiero recuperar acceso', 'password_recovery', 'correo'),
    ('puedo pagar con tarjeta', 'payment_availability', 'desactivados'),
    ('puedopagarcontarjeta', 'payment_availability', 'desactivados'),
    ('puedo pagar con tarjtea', 'payment_availability', 'desactivados'),
    ('como pagar el plan analista', 'payment_availability', 'No se hacen cargos'),
    ('renovar mi suscripcion', 'payment_availability', 'desactivados'),
    ('cuanto vale una ads coin', 'coin_value', 'No hay una equivalencia'),
    ('convertir coins a pesos', 'coin_value', 'no dinero retirable'),
    ('mis datos los puede ver otro usuario', 'data_access', 'otro cliente no debe'),
    ('otros clientes pueden ver mis archivos', 'data_access', 'permisos separados'),
    ('quien puede acceder a mis archivos', 'data_access', 'controles de acceso'),
    ('me borraste mi archivo', 'missing_file', 'Este chat no borra'),
    ('mi archivo desaparecio', 'missing_file', 'Historial'),
    ('no aparece mi archivo', 'missing_file', 'No elimines el registro'),
])
def test_product_support_does_not_guess_from_common_words(question, key, required):
    reply = answer_for(question, metrics=sales_metrics())
    assert reply['matched_key'] == key, (question, reply)
    assert required in reply['answer']


def test_normalization_preserves_valid_account_words():
    assert normalize_query('no me llega el correo') == 'no me llega el correo'


def test_account_support_topic_changes_with_financial_context():
    history = []
    for question, key in [
        ('cuanto vale una ads coin', 'coin_value'),
        ('puedo pagar con tarjeta', 'payment_availability'),
        ('mis datos los puede ver otro usuario', 'data_access'),
        ('no me llega el correo para recuperar la cuenta', 'password_recovery'),
        ('y no me llega el correo', 'password_recovery'),
        ('me borraste mi archivo', 'missing_file'),
        ('quiero eliminar mi cuenta', 'privacy_erasure'),
        ('necesito hablar con un humano', 'human_support'),
    ]:
        reply = answer_for(question, metrics=sales_metrics(), history=history)
        assert reply['matched_key'] == key, (question, reply)
        history.extend([dict(role='user', content=question), dict(role='assistant', content=reply['answer'])])


@pytest.mark.parametrize('question', ['mis datos', 'recuperar mi cuenta', 'acceder a mi cuenta'])
def test_erasure_article_requires_erasure_intent(question):
    assert 'privacy_erasure' not in [article['key'] for _, article in rank_articles(question)]


@pytest.mark.parametrize('question', ['mis ventas pagadas con tarjeta', 'pagar a proveedores',
                                    'mis clientes pueden pagar con tarjeta'])
def test_business_payments_are_not_product_checkout(question):
    assert answer_for(question, metrics=sales_metrics())['matched_key'] != 'payment_availability'


def test_unknown_question_does_not_suggest_account_erasure():
    reply = answer_for('zxcvbnmqwer')
    assert reply['confidence'] == 'low'
    assert 'Eliminar cuenta y datos' not in reply['suggestions']
    assert 'Soporte humano' in reply['suggestions']
