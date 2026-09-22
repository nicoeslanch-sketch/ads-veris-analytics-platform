import pytest
from fastapi import HTTPException
from app.config import Settings
from app import commercial_readiness as readiness
from app.main import validate_production_config
from app.routes import admin


def test_readiness_is_not_a_payment_or_capacity_certificate(monkeypatch):
    monkeypatch.setattr(readiness, 'security_context', lambda *a: {'has_mfa': True, 'is_admin': True})
    result = readiness.commercial_readiness('owner', Settings(_env_file=None, app_env='production'))
    assert result['payment_activation_available'] is False
    assert result['purchases_enabled'] is False
    states = {i['id']: i['state'] for i in result['items']}
    assert states['mfa'] == 'ready'
    assert states['payments'] == 'deferred'
    assert states['capacity'] == states['recovery'] == states['catalog'] == 'pending'


def test_readiness_checks_admin_before_fetching(client, auth_headers, monkeypatch):
    def deny(*a):
        raise HTTPException(403, 'No permitido')
    monkeypatch.setattr(admin, '_require_admin_sync', deny)
    monkeypatch.setattr(admin, 'commercial_readiness', lambda *a: pytest.fail('Unauthorized read'))
    assert client.get('/admin/readiness', headers=auth_headers).status_code == 403


def test_payment_flag_cannot_enable_unimplemented_checkout():
    violations = validate_production_config(Settings(_env_file=None, app_env='production', ads_coin_purchases_enabled=True))
    assert any('ADS_COIN_PURCHASES_ENABLED' in item for item in violations)
