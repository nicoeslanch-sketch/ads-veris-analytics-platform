import hashlib
import hmac
import json
from contextlib import contextmanager
import base64
from email import policy
from email.parser import BytesParser
import httpx

import pytest
from pydantic import ValidationError

from app.config import Settings
from app import operational_notifications as mod
from app import operational_health as health


def settings():
    return Settings(_env_file=None, operations_webhook_url='https://alerts.example.test/events',
                    operations_webhook_secret='private-key-only-for-tests-123456789')


@pytest.mark.parametrize('url', ['http://example.test', 'https://user:password@example.test',
                               'https://example.test:444/path', 'https://example.test/path#secret'])
def test_invalid_config_does_not_print_secret(url):
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, operations_webhook_url=url, operations_webhook_secret='secret-value')
    assert 'secret-value' not in str(exc.value)


def test_unconfigured_notifications_do_not_touch_network(monkeypatch):
    monkeypatch.setattr(mod, 'commercial_rpc', lambda *a: pytest.fail('not configured'))
    mod.deliver(Settings(_env_file=None), {'HTTP_ERRORS'})


@pytest.mark.parametrize('status,ip,expected', [(204, '8.8.8.8', True), (302, '8.8.8.8', False),
                                              (200, '127.0.0.1', False)])
def test_signed_minimal_notification_and_safe_delivery(monkeypatch, status, ip, expected):
    rpc_calls, sends = [], []
    def rpc(name, p, s):
        rpc_calls.append(p)
        if p['p_action'] == 'claim' and sum(x['p_action'] == 'claim' for x in rpc_calls) == 1:
            return dict(code='HTTP_ERRORS', active=True, revision=1, lease='lease')
    class Client:
        def __init__(self, **kw):
            assert kw['follow_redirects'] is False and kw['trust_env'] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        @contextmanager
        def stream(self, method, url, **kw):
            sends.append(kw)
            yield type('Response', (), {'status_code': status})()
    monkeypatch.setattr(mod, 'commercial_rpc', rpc)
    monkeypatch.setattr(mod.httpx, 'Client', Client)
    monkeypatch.setattr(mod.socket, 'getaddrinfo', lambda *a, **kw: [(2, 1, 6, '', (ip, 443))])
    config = settings()
    mod.deliver(config, {'HTTP_ERRORS'})
    ack = next(c for c in rpc_calls if c['p_action'] == 'ack')
    assert ack['p_success'] is expected
    if sends:
        body = sends[0]['content']
        event = json.loads(body)
        assert set(event) == {'event_id', 'service', 'code', 'state', 'sent_at'}
        signature = hmac.new(config.operations_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        assert sends[0]['headers']['X-ADS-Signature'] == 'sha256=' + signature
        assert event['state'] == 'active'
    else:
        assert ip == '127.0.0.1'


@pytest.mark.parametrize('report,code', [({'errors': 1}, 'RETENTION_FAILED'),
    ({'mode': 'audit', 'candidates': 2}, 'RETENTION_PENDING'), ({'mode': 'apply', 'candidates': 2}, None)])
def test_retention_health_reports_only_actionable_states(monkeypatch, report, code):
    monkeypatch.setattr(health, 'commercial_rpc', lambda *a: {'report': report})
    data, alerts = health.maintenance_status(Settings(_env_file=None))
    assert data['report'] == report
    assert [a['code'] for a in alerts] == ([code] if code else [])


@pytest.mark.parametrize('token_status,send_status,expected', [(200, 200, True), (400, 200, False), (200, 429, False)])
def test_gmail_uses_only_send_api_and_fixed_recipient(monkeypatch, token_status, send_status, expected):
    config = Settings(_env_file=None, operations_email_from='servicios@adsveris.com',
        operations_gmail_client_id='client', operations_gmail_client_secret='secret', operations_gmail_refresh_token='refresh')
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == 'oauth2.googleapis.com':
            return httpx.Response(token_status, json={'access_token': 'short-lived-token'})
        assert str(request.url) == 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        assert request.headers['Authorization'] == 'Bearer short-lived-token'
        msg = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(json.loads(request.content)['raw']))
        assert msg['To'] == 'servicios@adsveris.com' and msg['From'] == 'servicios@adsveris.com'
        assert 'HTTP_ERRORS' in msg['Subject'] and msg['Message-ID'] == '<event-1@adsveris.com>'
        assert 'secret' not in msg.get_content() and 'refresh' not in msg.get_content()
        return httpx.Response(send_status, json={'id': 'provider-id'})
    real_client = httpx.Client
    monkeypatch.setattr(mod.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    assert mod.email_configured(config)
    assert mod._send_email(config, dict(event_id='event-1', code='HTTP_ERRORS', state='active', sent_at='2026-10-18')) is expected
    assert len(calls) == (1 if token_status != 200 else 2)


def test_gmail_partial_configuration_fails_closed():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, operations_email_from='servicios@adsveris.com')


def test_email_has_priority_over_optional_webhook(monkeypatch):
    config = settings()
    config.operations_email_from = 'servicios@adsveris.com'
    config.operations_gmail_client_id = 'client'
    config.operations_gmail_client_secret = 'secret'
    config.operations_gmail_refresh_token = 'refresh'
    claims, sent = [], []
    def rpc(name, p, s):
        if p['p_action'] == 'claim':
            claims.append(p)
            if len(claims) == 1:
                return dict(code='HTTP_ERRORS', active=True, revision=1, lease='lease')
    monkeypatch.setattr(mod, 'commercial_rpc', rpc)
    monkeypatch.setattr(mod, '_send_email', lambda s, e: sent.append(e) or True)
    monkeypatch.setattr(mod.socket, 'getaddrinfo', lambda *a, **k: pytest.fail('webhook must not be used'))
    mod.deliver(config, {'HTTP_ERRORS'})
    assert len(sent) == 1
