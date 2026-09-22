"""MFA must fail closed for API data, but permit first-factor enrollment."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import account_security as security, auth
from app.config import Settings, get_settings
from app.routes import security as route


def production():
    return Settings(_env_file=None, app_env="production", mfa_enforcement=False)


@pytest.mark.parametrize("admin,enrolled,denied", [
    (True, False, True), (True, True, True), (False, True, True), (False, False, False),
])
def test_first_factor_gate(monkeypatch, admin, enrolled, denied):
    monkeypatch.setattr(security, "security_context", lambda uid, s: {"is_admin": admin, "has_mfa": enrolled})
    if denied:
        with pytest.raises(HTTPException) as exc:
            security.require_account_mfa("owner", {"aal": "aal1"}, production())
        assert exc.value.status_code == 403
        assert exc.value.headers == {"X-Auth-Action": "mfa_required"}
    else:
        security.require_account_mfa("owner", {"user_metadata": {"aal": "aal2"}}, production())


def test_verified_session_does_not_repeat_database_roundtrip(monkeypatch):
    monkeypatch.setattr(security, "security_context", lambda *a: pytest.fail("Unnecessary database lookup"))
    security.require_account_mfa("owner", {"aal": "aal2"}, production())


@pytest.mark.parametrize("value", [None, [], {}, {"is_admin": "false", "has_mfa": False},
                                       {"is_admin": False, "has_mfa": 0}])
def test_malformed_database_context_fails_closed(monkeypatch, value):
    monkeypatch.setattr(security, "commercial_rpc", lambda *a: value)
    with pytest.raises(HTTPException) as exc:
        security.require_account_mfa("owner", {}, production())
    assert exc.value.status_code == 503


def test_mfa_context_is_not_negatively_cached(monkeypatch):
    states = iter([False, True])
    monkeypatch.setattr(security, "commercial_rpc", lambda *a: {"is_admin": False, "has_mfa": next(states)})
    security.require_account_mfa("owner", {}, production())
    with pytest.raises(HTTPException):
        security.require_account_mfa("owner", {}, production())


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
        id="owner", email="owner@example.invalid", claims={"aal": "aal1"})
    app.dependency_overrides[get_settings] = production
    seen = []
    def context(uid, settings):
        seen.append(uid)
        return {"is_admin": True, "has_mfa": False}
    monkeypatch.setattr(route, "security_context", context)
    response = TestClient(app).get("/security/session?user_id=foreign")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert seen == ["owner"]
    assert response.json() == {"enforced": True, "has_mfa": False, "admin_required": True,
                               "verified": False, "needs_verification": True}


def test_setup_endpoint_still_requires_authentication():
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_settings] = production
    assert TestClient(app).get("/security/session").status_code == 401
