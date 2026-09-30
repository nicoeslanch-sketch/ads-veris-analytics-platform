"""MFA must fail closed for API data, but permit first-factor enrollment."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import account_security as security, auth
from app.config import Settings, get_settings
from app.routes import security as route

OWNER = '11111111-1111-4111-8111-111111111111'
SESSION = '22222222-2222-4222-8222-222222222222'
CLAIMS = {'session_id': SESSION, 'aal': 'aal1'}


def active_context(admin=False, mfa=False):
    return {'is_admin': admin, 'has_mfa': mfa, 'session_active': True}


def production():
    return Settings(_env_file=None, app_env="production", mfa_enforcement=False)


@pytest.mark.parametrize("admin,enrolled,denied", [
    (True, False, True), (True, True, True), (False, True, True), (False, False, False),
])
def test_first_factor_gate(monkeypatch, admin, enrolled, denied):
    monkeypatch.setattr(security, "commercial_rpc", lambda *a: active_context(admin, enrolled))
    if denied:
        with pytest.raises(HTTPException) as exc:
            security.require_account_mfa(OWNER, CLAIMS, production())
        assert exc.value.status_code == 403
        assert exc.value.headers == {"X-Auth-Action": "mfa_required"}
    else:
        security.require_account_mfa(OWNER, {**CLAIMS, "user_metadata": {"aal": "aal2"}}, production())


def test_current_request_context_does_not_repeat_database_roundtrip(monkeypatch):
    monkeypatch.setattr(security, "commercial_rpc", lambda *a: pytest.fail("Duplicate database lookup"))
    security.require_account_mfa(OWNER, {**CLAIMS, "aal": "aal2"}, production(), active_context(True, True))


@pytest.mark.parametrize("value", [None, [], {}, {"is_admin": "false", "has_mfa": False},
                                       {"is_admin": False, "has_mfa": 0}])
def test_malformed_database_context_fails_closed(monkeypatch, value):
    monkeypatch.setattr(security, "commercial_rpc", lambda *a: value)
    with pytest.raises(HTTPException) as exc:
        security.require_account_mfa(OWNER, CLAIMS, production())
    assert exc.value.status_code == 503


def test_mfa_context_is_not_negatively_cached(monkeypatch):
    states = iter([False, True])
    monkeypatch.setattr(security, "commercial_rpc", lambda *a: active_context(mfa=next(states)))
    security.require_account_mfa(OWNER, CLAIMS, production())
    with pytest.raises(HTTPException):
        security.require_account_mfa(OWNER, CLAIMS, production())


def test_current_user_always_checks_verified_claims(monkeypatch):
    checked = []
    user = auth.AuthenticatedUser(id="owner", email="owner@example.invalid", claims={"aal": "aal1"})
    monkeypatch.setattr(auth, "get_verified_user", lambda *a: user)
    monkeypatch.setattr(security, "require_account_mfa", lambda *a: checked.append(a))
    assert auth.get_current_user(None, production()) == user
    assert checked[0][:2] == ("owner", user.claims)


def test_security_setup_endpoint_reveals_only_own_booleans(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[auth.get_verified_user] = lambda: auth.AuthenticatedUser(
        id=OWNER, email="owner@example.invalid", claims=CLAIMS)
    app.dependency_overrides[get_settings] = production
    seen = []
    def context(uid, claims, settings):
        seen.append(uid)
        return active_context(admin=True)
    monkeypatch.setattr(route, "require_live_session", context)
    response = TestClient(app).get("/security/session?user_id=foreign")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert seen == [OWNER]
    assert response.json() == {"enforced": True, "has_mfa": False, "admin_required": True,
                               "verified": False, "needs_verification": True}


def test_setup_endpoint_still_requires_authentication():
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_settings] = production
    assert TestClient(app).get("/security/session").status_code == 401


@pytest.mark.parametrize('aal', ['aal1', 'aal2'])
def test_revoked_session_denied_even_after_second_factor(monkeypatch, aal):
    monkeypatch.setattr(security, 'commercial_rpc', lambda *a: {**active_context(), 'session_active': False})
    with pytest.raises(HTTPException) as denied:
        security.require_account_mfa(OWNER, {**CLAIMS, 'aal': aal}, production())
    assert denied.value.status_code == 401


@pytest.mark.parametrize('session_id', [None, '', 'not-a-uuid', [], 1])
def test_missing_or_malformed_session_is_denied_without_rpc(monkeypatch, session_id):
    monkeypatch.setattr(security, 'commercial_rpc', lambda *a: pytest.fail('Must reject before RPC'))
    with pytest.raises(HTTPException) as denied:
        security.require_live_session(OWNER, {'session_id': session_id}, production())
    assert denied.value.status_code == 401


def test_session_binding_uses_verified_identity_not_metadata(monkeypatch):
    calls = []
    def rpc(name, payload, settings):
        calls.append((name, payload))
        return active_context()
    monkeypatch.setattr(security, 'commercial_rpc', rpc)
    security.require_live_session(OWNER, {**CLAIMS, 'user_metadata': {'session_id': OWNER}}, production())
    assert calls == [('verified_session_context', {'p_user_id': OWNER, 'p_session_id': SESSION})]


def test_active_session_is_not_cached_past_revocation(monkeypatch):
    states = iter([True, False])
    monkeypatch.setattr(security, 'commercial_rpc', lambda *a: {**active_context(), 'session_active': next(states)})
    assert security.require_live_session(OWNER, CLAIMS, production())['session_active']
    with pytest.raises(HTTPException) as denied:
        security.require_live_session(OWNER, CLAIMS, production())
    assert denied.value.status_code == 401


def test_valid_jwt_cannot_bypass_live_session_validation(monkeypatch):
    from fastapi.security import HTTPAuthorizationCredentials
    monkeypatch.setattr(auth, '_decode', lambda *a: {'sub': OWNER, **CLAIMS, 'aal': 'aal2'})
    monkeypatch.setattr(security, 'commercial_rpc', lambda *a: {**active_context(), 'session_active': False})
    with pytest.raises(HTTPException) as denied:
        auth.get_verified_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials='synthetic'), production())
    assert denied.value.status_code == 401


def test_database_outage_is_not_reported_as_a_bad_password(monkeypatch):
    def unavailable(*args):
        raise HTTPException(503, 'Temporalmente no disponible')
    monkeypatch.setattr(security, 'commercial_rpc', unavailable)
    with pytest.raises(HTTPException) as denied:
        security.require_live_session(OWNER, CLAIMS, production())
    assert denied.value.status_code == 503
