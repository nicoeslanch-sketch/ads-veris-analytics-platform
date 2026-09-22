import pytest
from fastapi import HTTPException

from app import request_budget
from app.config import Settings
from app.routes import me, support


@pytest.mark.parametrize('value,code', [(None, 503), ({}, 503), ({'allowed': 'true'}, 503),
    ({'allowed': False, 'retry_after': -1}, 503), ({'allowed': False, 'retry_after': 45}, 429)])
def test_request_budget_fail_closed(monkeypatch, value, code):
    monkeypatch.setattr(request_budget, 'commercial_rpc', lambda *a: value)
    with pytest.raises(HTTPException) as exc:
        request_budget.consume_budget('trial:rut:private', Settings(_env_file=None), limit=5, window=600)
    assert exc.value.status_code == code
    if code == 429:
        assert exc.value.headers == {'Retry-After': '45'}


def test_budget_does_not_store_rut(monkeypatch):
    def rpc(name, payload, settings):
        assert name == 'consume_request_budget'
        assert len(payload['p_bucket_hash']) == 64
        assert '12345678' not in str(payload)
        return {'allowed': True, 'retry_after': 0}
    monkeypatch.setattr(request_budget, 'commercial_rpc', rpc)
    request_budget.consume_budget('trial:rut:12345678-5', Settings(_env_file=None), limit=5, window=600)


def test_production_does_not_fall_back_to_memory(monkeypatch):
    seen = []
    monkeypatch.setattr(me, 'consume_budget', lambda *a, **kw: seen.append(a))
    me._guard_activation_rate('trial:user:owner', Settings(_env_file=None, app_env='production'))
    assert seen[0][0] == 'trial:user:owner'


def test_support_stops_before_insert_if_budget_unavailable(monkeypatch):
    def unavailable(*a, **kw):
        raise HTTPException(503, 'Unavailable')
    monkeypatch.setattr(support, 'consume_budget', unavailable)
    monkeypatch.setattr(support, 'commercial_rpc', lambda *a: pytest.fail('No insert permitted'))
    with pytest.raises(HTTPException) as exc:
        support._insert_sync('owner', support.SupportRequestBody(mensaje='Help'), Settings(_env_file=None))
    assert exc.value.status_code == 503
