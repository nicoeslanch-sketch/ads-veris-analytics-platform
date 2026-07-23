"""P0-4 (fix/qa-motor-empresarial-024): control de planes fail-closed.

Antes de este cambio, dos rutas silenciosas otorgaban Plan Básico por
defecto: (1) `get_profile_flags` cuando `profiles` no tenía fila para el
usuario, y (2) `normalize_plan` cuando el valor guardado no calzaba con
ningún plan conocido. Ambas quedan resueltas a `sin_plan` (cero
capacidades) — la ausencia o corrupción de datos de plan nunca debe leerse
como "dale acceso básico por si acaso".
"""

import httpx
import pytest
from fastapi import HTTPException

from app import capabilities, quota
from app.capabilities import (
    Capability,
    is_known_plan_value,
    normalize_plan,
    require_capability_for_user,
)


class FakeSettings:
    plan_enforcement = True
    supabase_url = "https://example.supabase.co"
    supabase_service_role_key = "clave"
    ai_monthly_limit_basico = 20
    ai_monthly_limit_analista = 200
    ai_monthly_limit_gold = 200


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._payload


# ── 1. Perfil inexistente ────────────────────────────────────────────────────


def test_perfil_inexistente_no_es_basico_sino_sin_plan(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse([]))
    plan, is_admin = capabilities.get_profile_flags("u-huerfano", FakeSettings())
    assert plan == "sin_plan"
    assert is_admin is False


def test_perfil_inexistente_bloquea_la_puerta_de_capacidad(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse([]))
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u-huerfano", Capability.STANDARDIZE, FakeSettings())
    assert excinfo.value.status_code == 403


# ── 2. Plan null en una fila existente ───────────────────────────────────────


def test_profile_con_plan_null_resuelve_sin_plan():
    assert normalize_plan(None) == "sin_plan"


def test_perfil_con_plan_null_en_la_fila(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: _FakeResponse([{"plan": None, "is_admin": False}])
    )
    plan, is_admin = capabilities.get_profile_flags("u1", FakeSettings())
    assert plan == "sin_plan"
    assert is_admin is False


# ── 3. Plan desconocido (dato corrupto o plan nuevo sin agregar aún) ────────


def test_plan_desconocido_no_se_normaliza_como_basico():
    assert normalize_plan("premium_legacy_2019") == "sin_plan"
    assert is_known_plan_value("premium_legacy_2019") is False


def test_perfil_con_plan_desconocido_bloquea_capacidades(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: _FakeResponse([{"plan": "premium_legacy_2019", "is_admin": False}]),
    )
    plan, _is_admin = capabilities.get_profile_flags("u1", FakeSettings())
    assert plan == "sin_plan"
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u1", Capability.STANDARDIZE, FakeSettings())
    assert excinfo.value.status_code == 403


def test_sin_plan_explicito_se_distingue_de_plan_desconocido():
    # sin_plan es un valor reconocido: no es lo mismo que basura en la columna,
    # aunque ambos resuelvan a la misma capacidad (cero) — la distinción vive
    # en el log de anomalía, no en el resultado de negocio.
    assert is_known_plan_value("sin_plan") is True
    assert is_known_plan_value("premium_legacy_2019") is False
    assert normalize_plan("sin_plan") == normalize_plan("premium_legacy_2019") == "sin_plan"


# ── 4. sin_plan (cuenta nueva legítima) ──────────────────────────────────────


def test_sin_plan_responde_403_con_cta_no_500(monkeypatch):
    monkeypatch.setattr(
        capabilities, "get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u1", Capability.STANDARDIZE, FakeSettings())
    assert excinfo.value.status_code == 403
    assert "Planes" in excinfo.value.detail


# ── 5. Trial activo (incluye el caso perfil-ausente + trial vigente) ────────


def test_trial_activo_desbloquea_pese_a_perfil_inexistente(monkeypatch):
    from app import trials

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse([]))
    monkeypatch.setattr(
        trials, "get_trial_state", lambda uid, st: {"used": True, "active": True}
    )
    plan = require_capability_for_user("u-huerfano", Capability.STANDARDIZE, FakeSettings())
    assert plan == "trial"


# ── 6. Trial vencido ──────────────────────────────────────────────────────────


def test_trial_vencido_bloquea_con_mensaje_propio(monkeypatch):
    from app import trials

    monkeypatch.setattr(
        capabilities, "get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    monkeypatch.setattr(
        trials, "get_trial_state", lambda uid, st: {"used": True, "active": False}
    )
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u1", Capability.STANDARDIZE, FakeSettings())
    assert excinfo.value.status_code == 403
    assert "terminó" in excinfo.value.detail


# ── 7. Admin ──────────────────────────────────────────────────────────────────


def test_admin_pasa_pese_a_plan_corrupto_en_su_propia_fila(monkeypatch):
    """is_admin manda ANTES de mirar el plan (línea `if is_admin or plan_allows`):
    una fila de admin con un valor de plan corrupto no debe perder acceso."""
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: _FakeResponse([{"plan": "algo_invalido", "is_admin": True}]),
    )
    plan = require_capability_for_user("u-admin", Capability.CONNECT_SQL, FakeSettings())
    assert plan == "sin_plan"  # el plan normalizado no importa: is_admin ya dejó pasar


# ── 8. Supabase temporalmente no disponible ──────────────────────────────────


def test_supabase_caido_responde_503_no_bypass_silencioso(monkeypatch):
    def _boom(*args, **kwargs):
        raise httpx.ConnectError("timeout")

    monkeypatch.setattr(httpx, "get", _boom)
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u1", Capability.STANDARDIZE, FakeSettings())
    assert excinfo.value.status_code == 503


def test_supabase_caido_en_cuota_ia_es_fail_open_documentado(monkeypatch):
    """Distinto de la puerta de capacidad: la cuota de IA sí es fail-open ante
    un error de red (ver docstring de quota.py) — no debe convertirse en 500."""

    def _boom(*args, **kwargs):
        raise httpx.ConnectError("timeout")

    monkeypatch.setattr(httpx, "get", _boom)
    assert quota.check_quota("u1", FakeSettings()) is None
