"""Fase 14b — pruebas HTTP REALES de las puertas comerciales y del trial.

El test estructural de la Fase 14 (grep del código fuente) solo probaba que
la puerta EXISTE. Estas pruebas ejercitan los endpoints por HTTP y verifican:
- respuesta 403 real para cuentas sin acceso;
- que Anthropic NO se llama, que el motor NO procesa y que restore NO corre;
- que el trial vigente SÍ pasa las puertas que le corresponden (y la IA no);
- la elegibilidad de activación (plan pagado/admin NO reservan RUT ajeno);
- la vinculación de identidad en solicitudes de contratación;
- la participación bruta como distribución que suma 100%.
"""

import pytest
from fastapi.testclient import TestClient

from app import trials
from app.auth import AuthenticatedUser, get_current_user
from app.config import Settings, get_settings
from app.engine.clean import analyze_and_clean
from app.engine.loader import load_dataframe_with_report
from app.engine.metrics import compute_metrics
from app.main import app

TRIAL_ACTIVO = {
    "used": True, "active": True, "started_at": "2026-07-01T00:00:00+00:00",
    "ends_at": "2026-07-30T00:00:00+00:00", "days_remaining": 14,
}
TRIAL_INACTIVO = {
    "used": False, "active": False, "started_at": None,
    "ends_at": None, "days_remaining": 0,
}

CSV = b"Fecha;Ventas\n05/01/2026;100\n06/01/2026;200\n"


def _settings_enforced() -> Settings:
    return Settings(
        plan_enforcement=True,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="clave",
        supabase_jwt_secret="",
        anthropic_api_key="sk-falsa",
        _env_file=None,
    )


@pytest.fixture()
def client(monkeypatch):
    app.dependency_overrides[get_settings] = _settings_enforced
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="user-test", email="t@example.cl", claims={}
    )
    # Ninguna prueba debe salir a la red: cualquier intento revienta.
    monkeypatch.setattr(
        "app.routes.ai._client",
        lambda settings: (_ for _ in ()).throw(AssertionError("Anthropic NO debía llamarse")),
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _sin_plan(monkeypatch, trial=TRIAL_INACTIVO):
    monkeypatch.setattr(
        "app.capabilities.get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    monkeypatch.setattr("app.trials.get_trial_state", lambda uid, st: dict(trial))


def test_correo_designado_recupera_rol_admin_en_contexto_de_acceso(monkeypatch):
    """El JWT verificado cierra la ventana entre el alta y la migracion 0018.

    P1-10: el bootstrap por correo ahora exige el flag explícito
    admin_email_bootstrap_enabled (apagado por defecto) — esta prueba
    ejercita justamente el modo de recuperación, así que lo prende."""
    from app.routes import me as me_module

    monkeypatch.setattr(
        me_module, "get_profile_flags", lambda uid, st: ("basico", False)
    )
    monkeypatch.setattr(me_module, "_billing_identity_sync", lambda uid, st: None)
    settings = _settings_enforced()
    settings.admin_email_bootstrap_enabled = True
    result = me_module._build_access_sync(
        "admin-test", "servicios@adsveris.com", settings
    )
    assert result["is_admin"] is True
    assert result["plan_display"] == "Administrador"
    from app.capabilities import Capability

    assert set(result["capabilities"]) == {cap.value for cap in Capability}


def test_correo_designado_no_recupera_admin_sin_el_flag_de_bootstrap(monkeypatch):
    """Sin el flag explícito (el valor por defecto), ni el correo designado
    otorga is_admin -- profiles.is_admin es la única fuente de verdad."""
    from app.routes import me as me_module

    monkeypatch.setattr(
        me_module, "get_profile_flags", lambda uid, st: ("basico", False)
    )
    monkeypatch.setattr(me_module, "_billing_identity_sync", lambda uid, st: None)
    result = me_module._build_access_sync(
        "admin-test", "servicios@adsveris.com", _settings_enforced()
    )
    assert result["is_admin"] is False


# ── Gates por HTTP: 403 real y CERO trabajo ejecutado ────────────────────────


def test_ai_summary_403_sin_plan_y_anthropic_no_se_llama(client, monkeypatch):
    _sin_plan(monkeypatch)
    response = client.post("/ai/summary", json={"metrics": {}})
    assert response.status_code == 403
    assert "plan" in response.json()["detail"].lower()


def test_ai_chat_y_recommendation_403_sin_plan(client, monkeypatch):
    _sin_plan(monkeypatch)
    chat = client.post("/ai/chat", json={"pregunta": "hola", "metrics": {}})
    assert chat.status_code == 403
    reco = client.post("/ai/recommendation", json={"metrics": {}})
    assert reco.status_code == 403


def test_metrics_403_sin_plan_y_el_motor_no_procesa(client, monkeypatch):
    _sin_plan(monkeypatch)
    monkeypatch.setattr(
        "app.routes.pipeline._metrics_sync",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("el motor NO debía correr")),
    )
    response = client.post("/metrics", files={"file": ("v.csv", CSV, "text/csv")})
    assert response.status_code == 403


def test_restore_403_sin_plan_y_no_descarga_nada(client, monkeypatch):
    _sin_plan(monkeypatch)
    monkeypatch.setattr(
        "app.routes.pipeline._restore_latest_sync",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("restore NO debía correr")),
    )
    response = client.post("/restore/latest")
    assert response.status_code == 403


def test_trial_vigente_pasa_metrics_pero_no_ia(client, monkeypatch):
    """La prueba gratuita desbloquea el dashboard; la IA sigue cerrada."""
    _sin_plan(monkeypatch, trial=TRIAL_ACTIVO)
    ok = client.post("/metrics", files={"file": ("v.csv", CSV, "text/csv")})
    assert ok.status_code == 200
    assert ok.json()["kpis"]["ingresos_totales"]["valor"] == 300.0
    ia = client.post("/ai/summary", json={"metrics": {}})
    assert ia.status_code == 403


def test_trial_expirado_403_con_mensaje_propio(client, monkeypatch):
    _sin_plan(
        monkeypatch,
        trial={**TRIAL_INACTIVO, "used": True},
    )
    response = client.post("/metrics", files={"file": ("v.csv", CSV, "text/csv")})
    assert response.status_code == 403
    assert "prueba gratuita" in response.json()["detail"]


# ── Elegibilidad de activación (P0.1 del informe: verificada) ────────────────


def _reset_rate_limit():
    from app.routes.me import _attempts

    _attempts.clear()


def test_usuario_con_plan_no_puede_activar_trial(client, monkeypatch):
    """Un Básico/Analista/Gold no reserva el RUT de otra empresa."""
    _reset_rate_limit()
    monkeypatch.setattr(
        "app.routes.me.get_profile_flags", lambda uid, st: ("basico", False)
    )
    monkeypatch.setattr(
        "app.trials.activate_trial",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("la RPC NO debía llamarse")),
    )
    response = client.post(
        "/me/trial", json={"rut_type": "empresa", "rut": "12.345.678-5"}
    )
    assert response.status_code == 403
    assert "cuentas nuevas" in response.json()["detail"]


def test_admin_no_puede_activar_trial(client, monkeypatch):
    _reset_rate_limit()
    monkeypatch.setattr(
        "app.routes.me.get_profile_flags", lambda uid, st: ("sin_plan", True)
    )
    response = client.post(
        "/me/trial", json={"rut_type": "empresa", "rut": "12.345.678-5"}
    )
    assert response.status_code == 403


def test_correo_sin_confirmar_no_activa_trial(client, monkeypatch):
    _reset_rate_limit()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="user-test",
        email="t@example.cl",
        claims={"user_metadata": {"email_verified": True}},
    )
    monkeypatch.setattr(
        "app.routes.me.get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    class AuthResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"email_confirmed_at": None}

    monkeypatch.setattr("app.routes.me.httpx.get", lambda *a, **k: AuthResponse())
    response = client.post(
        "/me/trial", json={"rut_type": "empresa", "rut": "12.345.678-5"}
    )
    assert response.status_code == 403
    assert "correo" in response.json()["detail"].lower()


def test_correo_confirmado_en_auth_es_la_fuente_autoritativa(monkeypatch):
    from app.routes.me import _guard_trial_eligibility_sync

    monkeypatch.setattr(
        "app.routes.me.get_profile_flags", lambda uid, st: ("sin_plan", False)
    )

    class AuthResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"email_confirmed_at": "2026-07-16T00:00:00Z"}

    monkeypatch.setattr("app.routes.me.httpx.get", lambda *a, **k: AuthResponse())
    user = AuthenticatedUser(
        id="user-test",
        email="t@example.cl",
        claims={"user_metadata": {"email_verified": False}},
    )
    _guard_trial_eligibility_sync(user, _settings_enforced())


def test_rate_limit_tambien_por_rut(client, monkeypatch):
    """Alternar cuentas no permite sondear el mismo RUT sin límite."""
    from app.routes.me import _TRIAL_ATTEMPT_MAX, _attempts, _guard_activation_rate

    _attempts.clear()
    for _ in range(_TRIAL_ATTEMPT_MAX):
        _guard_activation_rate("trial:rut:12345678-5")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        _guard_activation_rate("trial:rut:12345678-5")
    assert excinfo.value.status_code == 429
    _attempts.clear()


def test_rate_limits_de_trial_y_facturacion_no_se_mezclan():
    from app.routes.me import _TRIAL_ATTEMPT_MAX, _attempts, _guard_activation_rate

    _attempts.clear()
    for _ in range(_TRIAL_ATTEMPT_MAX):
        _guard_activation_rate("billing:user:user-test")
    _guard_activation_rate("trial:user:user-test")
    assert len(_attempts["trial:user:user-test"]) == 1
    _attempts.clear()


# ── Identidad de facturación en la contratación (P0.3 del informe) ───────────


def test_billing_identity_rechaza_rut_invalido(client):
    _reset_rate_limit()
    response = client.post(
        "/me/billing-identity", json={"rut_type": "empresa", "rut": "12.345.678-9"}
    )
    assert response.status_code == 422


def test_solicitud_con_identidad_ajena_es_422(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.plans._verify_identity_ownership", lambda *a, **k: False
    )
    response = client.post(
        "/addons/request",
        json={
            "tipo": "upgrade_analista",
            "mensaje": "Quiero contratar",
            "billing_identity_id": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("tipo", ["upgrade_analista", "upgrade_gold"])
def test_upgrade_sin_identidad_es_422(client, tipo):
    response = client.post(
        "/addons/request",
        json={"tipo": tipo, "mensaje": "Quiero contratar"},
    )
    assert response.status_code == 422
    assert "identidad de facturación" in response.json()["detail"]


def test_migracion_0016_contiene_elegibilidad_y_limpieza_de_identidad():
    """La RPC es la AUTORIDAD FINAL: elegibilidad por plan y reversa de la
    identidad recién creada cuando el trial falla (minimización de datos).
    (La ejecución real contra PostgreSQL queda para el smoke test operativo.)"""
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[2]
        / "supabase" / "migrations" / "0016_prueba_gratuita_rut.sql"
    ).read_text(encoding="utf-8")
    assert "USER_HAS_ACTIVE_PLAN" in sql
    assert "v_identity_creada" in sql
    assert "delete from public.billing_identities where id = v_identity" in sql
    assert "billing_identity_id" in sql  # addon_requests vinculado


# ── Participación bruta: una distribución que SÍ suma 100% ───────────────────


def _metrics_de(csv: str) -> dict:
    df, _ = load_dataframe_with_report("t.csv", csv.encode("utf-8"))
    result = analyze_and_clean(df, None, apply=True)
    return compute_metrics(result["_df_limpio"])


def test_participacion_bruta_suma_100_con_devoluciones():
    m = _metrics_de(
        "Fecha;Producto;Ventas\n"
        "05/01/2026;A;100000\n"
        "06/01/2026;B;-90000\n"  # B solo devuelve: neto -90%, bruta 0%
    )
    productos = {p["nombre"]: p for p in m["top_productos"]}
    assert productos["A"]["participacion_bruta_pct"] == 100.0
    assert productos["B"]["participacion_bruta_pct"] == 0.0
    assert productos["B"]["porcentaje"] == -90.0  # el % neto se conserva
    assert productos["B"]["devoluciones"] == -90000.0
    total = sum(p["participacion_bruta_pct"] for p in m["top_productos"])
    assert abs(total - 100.0) < 0.2


def test_participacion_bruta_invariante_en_caso_mixto():
    m = _metrics_de(
        "Fecha;Producto;Ventas\n"
        "05/01/2026;A;60000\n"
        "06/01/2026;B;40000\n"
        "07/01/2026;B;-10000\n"
    )
    productos = {p["nombre"]: p for p in m["top_productos"]}
    assert productos["A"]["participacion_bruta_pct"] == 60.0
    assert productos["B"]["participacion_bruta_pct"] == 40.0
    assert productos["B"]["ventas_brutas"] == 40000.0
    assert productos["B"]["ventas_netas"] == 30000.0
    total = sum(p["participacion_bruta_pct"] for p in m["top_productos"])
    assert abs(total - 100.0) < 0.2


def test_concentracion_de_clientes_usa_la_bruta():
    m = _metrics_de(
        "Fecha;Cliente;Ventas\n"
        "05/01/2026;ACME;100000\n"
        "06/01/2026;Beta;-90000\n"
    )
    # Con el % neto, ACME "concentraba" un absurdo 100% sobre neto 10.000;
    # la concentración ahora es distribución bruta.
    assert m["clientes"]["concentracion_top_pct"] == 100.0


def test_cliente_principal_se_elige_por_bruta_sin_reordenar_tablas_netas():
    m = _metrics_de(
        "Fecha;Cliente;Producto;Ventas\n"
        "05/01/2026;A;A;100000\n"
        "06/01/2026;A;A;-90000\n"
        "07/01/2026;B;B;50000\n"
    )
    # Productos sigue siendo una tabla por neto: B=50.000 supera A=10.000.
    assert m["top_productos"][0]["nombre"] == "B"
    # Clientes es un ranking de concentración: A concentra 2/3 de la bruta.
    assert m["clientes"]["top"][0]["nombre"] == "A"
    assert m["clientes"]["concentracion_top_pct"] == pytest.approx(66.7, abs=0.1)


def test_admin_support_expone_solo_identidad_enmascarada(monkeypatch):
    from app.routes import admin as admin_module

    monkeypatch.setattr(admin_module, "_require_admin_sync", lambda *a, **k: None)

    def fake_fetch(settings, url, params):
        if url.endswith("/support_requests"):
            return []
        if url.endswith("/addon_requests"):
            return [
                {
                    "id": "request-1",
                    "user_id": "user-test",
                    "tipo": "upgrade_analista",
                    "mensaje": "Quiero contratar",
                    "status": "pendiente",
                    "created_at": "2026-07-16T00:00:00Z",
                    "billing_identity_id": "identity-1",
                }
            ]
        if url.endswith("/billing_identities"):
            assert "rut_normalized" not in params["select"]
            return [
                {
                    "id": "identity-1",
                    "rut_type": "empresa",
                    "rut_masked": "12.***.***-5",
                }
            ]
        raise AssertionError(f"Consulta inesperada: {url}")

    monkeypatch.setattr(admin_module, "_fetch_json", fake_fetch)
    result = admin_module._support_inbox_sync("admin", _settings_enforced())
    item = result["solicitudes"][0]
    assert item["billing_identity"]["rut_masked"] == "12.***.***-5"
    assert "rut_normalized" not in item["billing_identity"]


def test_migracion_0017_permite_desvincular_identidad():
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[2]
        / "supabase" / "migrations" / "0017_billing_identity_retention.sql"
    ).read_text(encoding="utf-8").lower()
    assert sql.count("on delete set null") == 2


def test_migracion_0018_mantiene_cuenta_administradora():
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[2]
        / "supabase" / "migrations" / "0018_designated_admin_access.sql"
    ).read_text(encoding="utf-8").lower()
    assert "servicios@adsveris.com" in sql
    assert "profiles_enforce_designated_admin" in sql
    assert "new.is_admin := true" in sql
    assert "set is_admin = true" in sql


def test_copy_de_parcialidad_no_afirma_causa():
    filas = [f"{d:02d}/06/2026;1000" for d in range(1, 31)]
    filas += [f"{d:02d}/07/2026;1000" for d in range(1, 16)]
    m = _metrics_de("Fecha;Ventas\n" + "\n".join(filas))
    aviso = next(a for a in m["advertencias"] if "último registro" in a)
    assert "día 15" in aviso
    # Declara el HECHO y la regla, jamás "faltan datos" como causa.
    assert "faltan" not in aviso.lower()
