"""Authentication stays closed during temporary key-service failures."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from app import auth
from app.config import Settings


@pytest.fixture
def signed_session():
    private_key = ec.generate_private_key(ec.SECP256R1())
    settings = Settings(_env_file=None, app_env="production", supabase_url="https://synthetic.supabase.co")
    claims = {
        "sub": "synthetic-user", "aud": "authenticated", "role": "authenticated",
        "iss": "https://synthetic.supabase.co/auth/v1", "exp": int(time.time()) + 60,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "synthetic-key"})
    return private_key, claims, settings, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.parametrize("failure,status", [
    (PyJWKClientConnectionError("private diagnostic URL"), 503),
    (PyJWKClientError("key not found; private diagnostic"), 401),
])
def test_key_failure_preserves_authentication_and_hides_diagnostics(monkeypatch, signed_session, failure, status):
    _, _, settings, credentials = signed_session

    def lookup(_token):
        raise failure

    monkeypatch.setattr(auth, "_jwks_client", lambda _url: SimpleNamespace(get_signing_key_from_jwt=lookup))
    with pytest.raises(HTTPException) as rejected:
        auth.get_current_user(credentials, settings)
    assert rejected.value.status_code == status
    assert "private diagnostic" not in rejected.value.detail
    if status == 503:
        assert rejected.value.headers == {"Retry-After": "5"}
        assert "no necesitas cerrar sesion" in rejected.value.detail


@pytest.mark.parametrize("wrong_issuer", [False, True])
def test_production_es256_validates_project_after_key_recovery(monkeypatch, signed_session, wrong_issuer):
    key, claims, settings, credentials = signed_session
    monkeypatch.setattr(auth, "_jwks_client", lambda _url: SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=key.public_key()),
    ))
    if wrong_issuer:
        credentials.credentials = jwt.encode({**claims, "iss": "https://other.supabase.co/auth/v1"}, key, algorithm="ES256")
        with pytest.raises(HTTPException) as rejected:
            auth.get_current_user(credentials, settings)
        assert rejected.value.status_code == 401
    else:
        assert auth.get_current_user(credentials, settings).id == "synthetic-user"
