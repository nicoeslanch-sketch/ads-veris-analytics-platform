"""P1-10 (fix/qa-motor-empresarial-024): endurecimiento de seguridad.

- JWT: valida `iss` cuando el token lo declara (rechaza el de otro proyecto
  Supabase) y exige `sub` no vacío -- antes un token sin `sub` autenticaba
  igual con un id vacío en vez de rechazarse.
- Los errores de PyJWT/JWKS nunca llegan al cliente con su texto interno.
- El fallback administrativo por correo (ADMIN_EMAIL) queda detrás de un
  flag explícito, apagado por defecto -- ya no es un bypass permanente si
  alguien olvida vaciar la variable en producción tras confirmar is_admin.
"""

import time

import jwt as pyjwt
import pytest
from fastapi import HTTPException

TEST_SECRET = "secreto-de-prueba-suficientemente-largo-32b"


def _token(claims: dict, secret: str = TEST_SECRET) -> str:
    return pyjwt.encode(claims, secret, algorithm="HS256")


# ── JWT: issuer ──────────────────────────────────────────────────────────────


def test_jwt_con_issuer_incorrecto_es_rechazado(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-real.supabase.co")
    token = _token({
        "sub": "user-1",
        "aud": "authenticated",
        "iss": "https://proyecto-ajeno.supabase.co/auth/v1",
        "exp": int(time.time()) + 3600,
    })
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_jwt_con_issuer_correcto_pasa(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-real.supabase.co")
    token = _token({
        "sub": "user-1",
        "aud": "authenticated",
        "iss": "https://proyecto-real.supabase.co/auth/v1",
        "exp": int(time.time()) + 3600,
    })
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_jwt_sin_issuer_sigue_pasando_compatibilidad(client, monkeypatch):
    """No se exige que el claim exista (compatibilidad con tokens legítimos
    que no siempre lo incluyeron) -- solo se rechaza si está y no coincide."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto-real.supabase.co")
    token = _token({
        "sub": "user-1",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    })
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


# ── JWT: sub no vacío ─────────────────────────────────────────────────────────


def test_jwt_sin_sub_es_rechazado(client):
    token = _token({"aud": "authenticated", "exp": int(time.time()) + 3600})
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_jwt_con_sub_vacio_es_rechazado(client):
    token = _token({"sub": "   ", "aud": "authenticated", "exp": int(time.time()) + 3600})
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ── JWT: el detalle interno nunca llega al cliente ───────────────────────────


def test_jwt_invalido_no_expone_detalle_interno_de_pyjwt(client):
    response = client.get(
        "/me", headers={"Authorization": "Bearer no-es-un-jwt-valido"}
    )
    assert response.status_code == 401
    detail = response.json()["detail"]
    # Nunca el texto crudo de PyJWT (nombres de excepción, rutas de librería).
    assert "DecodeError" not in detail
    assert "jwt" not in detail.lower()
    assert detail == "Token inválido o expirado. Inicia sesión nuevamente."


def test_jwt_firma_invalida_no_expone_detalle_interno(client):
    token = _token(
        {"sub": "user-1", "aud": "authenticated", "exp": int(time.time()) + 3600},
        secret="otro-secreto-completamente-distinto-32b",
    )
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Token inválido o expirado. Inicia sesión nuevamente."


# ── Fallback administrativo por correo: detrás de un flag explícito ─────────


class _FakeSettingsAdminBootstrap:
    supabase_url = "https://proyecto-real.supabase.co"
    supabase_service_role_key = "clave"
    admin_email = "servicios@adsveris.com"
    admin_email_bootstrap_enabled = False


def test_admin_bootstrap_por_correo_apagado_por_defecto(monkeypatch):
    """Sin el flag explícito, ni siquiera el correo bootstrap configurado
    otorga acceso -- profiles.is_admin es la única fuente de verdad."""
    from app.routes import admin as admin_module

    monkeypatch.setattr(admin_module, "get_is_admin", lambda uid, s: False)
    with pytest.raises(HTTPException) as excinfo:
        admin_module._require_admin_sync(
            "u1", _FakeSettingsAdminBootstrap(), email="servicios@adsveris.com"
        )
    assert excinfo.value.status_code == 403


def test_admin_bootstrap_por_correo_funciona_con_el_flag_explicito(monkeypatch):
    from app.routes import admin as admin_module

    class Enabled(_FakeSettingsAdminBootstrap):
        admin_email_bootstrap_enabled = True

    monkeypatch.setattr(admin_module, "get_is_admin", lambda uid, s: False)
    # No debe lanzar: el correo coincide y el flag de recuperación está activo.
    admin_module._require_admin_sync("u1", Enabled(), email="servicios@adsveris.com")


def test_admin_is_admin_real_sigue_funcionando_sin_el_flag(monkeypatch):
    """profiles.is_admin=true sigue siendo el camino normal, sin depender
    del flag de bootstrap en absoluto."""
    from app.routes import admin as admin_module

    monkeypatch.setattr(admin_module, "get_is_admin", lambda uid, s: True)
    admin_module._require_admin_sync(
        "u1", _FakeSettingsAdminBootstrap(), email="otra@persona.cl"
    )


# ── FastAPI.version refleja el motor real ────────────────────────────────────


def test_fastapi_version_es_engine_version():
    from app.main import app
    from app.version import ENGINE_VERSION

    assert app.version == ENGINE_VERSION
    assert app.version != "0.1.0"
