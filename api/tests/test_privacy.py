"""Privacy rights never trust a caller-supplied owner or a best-effort receipt."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.auth import AuthenticatedUser, get_current_user
from app.config import Settings, get_settings
from app.routes import privacy


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(privacy.router)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id='owner', email='owner@example.invalid', claims={})
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    calls = []
    def rpc(name, payload, settings):
        calls.append((name, payload))
        return {'id': 'receipt', 'accepted': True, 'version': privacy.LEGAL_VERSION, 'requests': []}
    monkeypatch.setattr(privacy, 'commercial_rpc', rpc)
    return TestClient(app), calls


def test_state_uses_authenticated_owner_and_no_cache(client):
    api, calls = client
    result = api.get('/privacy/account?user_id=foreign')
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'no-store'
    assert calls == [('account_privacy_state', {'p_user_id': 'owner'})]


@pytest.mark.parametrize('payload', [
    {'version': '2026-09-28', 'service_data_consent': False},
    {'version': '2026-09-28', 'service_data_consent': 1},
    {'version': '2026-09-27', 'service_data_consent': True},
    {'version': '2026-09-28'},
    {'version': '2026-09-28', 'service_data_consent': True, 'user_id': 'foreign'},
])
def test_acceptance_rejects_missing_consent_old_version_and_owner_override(client, payload):
    api, calls = client
    assert api.post('/privacy/acceptance', json=payload).status_code == 422
    assert not calls


def test_acceptance_records_version_from_current_form(client):
    api, calls = client
    assert api.post('/privacy/acceptance', json={'version': privacy.LEGAL_VERSION, 'service_data_consent': True}).status_code == 200
    assert calls[0] == ('accept_account_legal', {'p_user_id': 'owner', 'p_version': privacy.LEGAL_VERSION})


@pytest.mark.parametrize('kind', ['access', 'correction', 'erasure', 'objection'])
def test_rights_available_without_paid_capability_or_acceptance(client, kind):
    api, calls = client
    result = api.post('/privacy/requests', json={'kind': kind, 'confirmed': True, 'message': '  My request  '})
    assert result.status_code == 202  # Receipt, never a successful deletion claim.
    assert calls[0] == ('create_privacy_request', {'p_user_id': 'owner', 'p_kind': kind, 'p_message': 'My request'})


@pytest.mark.parametrize('payload', [
    {'kind': 'erasure'}, {'kind': 'erasure', 'confirmed': False},
    {'kind': 'erasure', 'confirmed': 1},
    {'kind': 'erasure', 'confirmed': True, 'user_id': 'foreign'},
    {'kind': 'erasure', 'confirmed': True, 'message': 'x' * 2001},
])
def test_request_validation(client, payload):
    api, calls = client
    assert api.post('/privacy/requests', json=payload).status_code == 422
    assert not calls


def test_failed_persistence_never_acknowledges_request(client, monkeypatch):
    def unavailable(*args): raise HTTPException(503, 'Unavailable')
    monkeypatch.setattr(privacy, 'commercial_rpc', unavailable)
    assert client[0].post('/privacy/requests', json={'kind': 'erasure', 'confirmed': True}).status_code == 503


def test_non_admin_cannot_list_or_answer(client, monkeypatch):
    def denied(*args): raise HTTPException(403, 'Forbidden')
    monkeypatch.setattr(privacy, '_require_admin_sync', denied)
    api, calls = client
    assert api.get('/privacy/admin/requests').status_code == 403
    assert api.post('/privacy/admin/requests/00000000-0000-0000-0000-000000000001',
                    json={'status': 'resolved', 'response': 'Documented response'}).status_code == 403
    assert not calls


def test_anonymous_cannot_submit():
    app = FastAPI()
    app.include_router(privacy.router)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, dev_auth_bypass=False)
    assert TestClient(app).post('/privacy/requests', json={'kind': 'erasure', 'confirmed': True}).status_code == 401
