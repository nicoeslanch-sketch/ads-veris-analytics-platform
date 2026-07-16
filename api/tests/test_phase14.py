"""Pruebas de la Fase 14: prueba gratuita (RUT), cierres P0 y parcialidad.

Cubre la matriz acordada en el análisis de calidad definitivo:
- RUT: normalización idempotente, módulo 11, enmascarado, sin piso arbitrario.
- Capacidades: el trial desbloquea TRIAL_CAPABILITIES (sin IA) solo vigente.
- Cuota: sin_plan → límite 0 sin 500; check_quota responde 403 con CTA.
- Gates P0: /ai/*, /metrics y /restore/latest rechazan cuentas sin acceso.
- Métricas: parcialidad POR MES, proyección sin el mes parcial y sin
  superposición con meses reales.
- format_number: repr() (round-trip float64) con guardas de finitud.
- Rate limiting de activación y privacidad de errores.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi import HTTPException

from app import quota
from app.capabilities import (
    Capability,
    TRIAL_CAPABILITIES,
    effective_capabilities,
    require_capability_for_user,
)
from app.engine.clean import analyze_and_clean
from app.engine.loader import load_dataframe_with_report
from app.engine.metrics import compute_metrics
from app.engine.standardize import format_number
from app.rut import compute_dv, is_valid_rut, mask_rut, normalize_rut
from app.trials import trial_state_from_row


class FakeSettings:
    plan_enforcement = True
    supabase_url = "https://example.supabase.co"
    supabase_service_role_key = "clave"
    ai_monthly_limit_basico = 20
    ai_monthly_limit_analista = 200
    ai_monthly_limit_gold = 200


def _run(csv: str):
    df, report = load_dataframe_with_report("t.csv", csv.encode("utf-8"))
    return analyze_and_clean(df, None, apply=True), report


# ── RUT: normalización y validación ──────────────────────────────────────────


def test_normalizacion_rut_formatos_equivalentes():
    assert normalize_rut("12.345.678-k") == "12345678-K"
    assert normalize_rut("12345678K") == "12345678-K"
    assert normalize_rut("12 345 678 K") == "12345678-K"
    assert normalize_rut(" 012.345.678-K ") == "12345678-K"


def test_normalizacion_rut_es_idempotente():
    for raw in ["12.345.678-k", "9.123.456-7", "76543210-0"]:
        once = normalize_rut(raw)
        assert once is not None
        assert normalize_rut(once) == once


def test_rut_invalido_estructuralmente():
    assert normalize_rut("") is None
    assert normalize_rut(None) is None
    assert normalize_rut("ABC-K") is None
    assert normalize_rut("12.345.678-X") is None
    assert normalize_rut("0-0") is None
    assert normalize_rut("123456789012") is None  # demasiado largo


def test_digito_verificador_modulo_11():
    # DVs conocidos del algoritmo oficial
    assert compute_dv("12345678") == "5"
    assert compute_dv("7654321") == "6"
    assert is_valid_rut("12.345.678-5")
    assert not is_valid_rut("12.345.678-9")


def test_sin_piso_arbitrario_de_cuerpo():
    """RUN antiguos bajo 1.000.000 son legítimos: solo manda el módulo 11."""
    body = "999999"
    assert is_valid_rut(f"{body}-{compute_dv(body)}")


def test_patron_llamativo_con_dv_valido_se_acepta():
    """11.111.111-1 pasa módulo 11: un patrón repetitivo no prueba falsedad."""
    assert compute_dv("11111111") == "1"
    assert is_valid_rut("11.111.111-1")


def test_mask_rut_solo_muestra_prefijo_y_dv():
    assert mask_rut("12345678-5") == "12.***.***-5"
    assert mask_rut("999999-K") == "9.***.***-K"
    assert "345" not in mask_rut("12345678-5")


# ── Trial: estado y capacidades ───────────────────────────────────────────────


def _trial_row(days_ago_start: int, days_from_now_end: int, revoked: bool = False):
    now = datetime.now(timezone.utc)
    return {
        "started_at": (now - timedelta(days=days_ago_start)).isoformat(),
        "ends_at": (now + timedelta(days=days_from_now_end)).isoformat(),
        "revoked_at": now.isoformat() if revoked else None,
    }


def test_trial_vigente_expirado_y_revocado():
    assert trial_state_from_row(None) == {
        "used": False, "active": False, "started_at": None,
        "ends_at": None, "days_remaining": 0,
    }
    vigente = trial_state_from_row(_trial_row(5, 10))
    assert vigente["used"] and vigente["active"]
    assert vigente["days_remaining"] == 10
    expirado = trial_state_from_row(_trial_row(20, -5))
    assert expirado["used"] and not expirado["active"]
    assert expirado["days_remaining"] == 0
    revocado = trial_state_from_row(_trial_row(5, 10, revoked=True))
    assert revocado["used"] and not revocado["active"]


def test_trial_capabilities_es_basico_sin_ia():
    assert Capability.STANDARDIZE in TRIAL_CAPABILITIES
    assert Capability.CLEAN in TRIAL_CAPABILITIES
    assert Capability.VIEW_DASHBOARD in TRIAL_CAPABILITIES
    assert Capability.DOWNLOAD_REPORTS in TRIAL_CAPABILITIES
    # Exclusiones comerciales: la IA es la diferencia entre probar y contratar
    assert Capability.ASK_DATA_AI not in TRIAL_CAPABILITIES
    assert Capability.AI_CLEANING not in TRIAL_CAPABILITIES
    assert Capability.DOWNLOAD_CLEAN_DATASET not in TRIAL_CAPABILITIES
    assert Capability.CONNECT_SQL not in TRIAL_CAPABILITIES
    assert Capability.COMMUNITY_ACCESS not in TRIAL_CAPABILITIES


def test_capacidades_efectivas_del_servidor():
    # sin plan + trial vigente = TRIAL_CAPABILITIES
    assert effective_capabilities("sin_plan", False, True, True) == TRIAL_CAPABILITIES
    # sin plan sin trial = nada
    assert effective_capabilities("sin_plan", False, False, True) == set()
    # admin y enforcement apagado = todo
    assert effective_capabilities("sin_plan", True, False, True) == set(Capability)
    assert effective_capabilities("sin_plan", False, False, False) == set(Capability)


def test_gate_deja_pasar_trial_vigente(monkeypatch):
    from app import capabilities, trials

    monkeypatch.setattr(
        capabilities, "get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    monkeypatch.setattr(
        trials, "get_trial_state",
        lambda uid, st: {"used": True, "active": True},
    )
    plan = require_capability_for_user("u1", Capability.STANDARDIZE, FakeSettings())
    assert plan == "trial"


def test_gate_trial_no_desbloquea_ia(monkeypatch):
    from app import capabilities, trials

    monkeypatch.setattr(
        capabilities, "get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    # Si el gate consultara el trial para IA, este stub lo delataría
    monkeypatch.setattr(
        trials, "get_trial_state",
        lambda uid, st: {"used": True, "active": True},
    )
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u1", Capability.ASK_DATA_AI, FakeSettings())
    assert excinfo.value.status_code == 403


def test_gate_trial_expirado_mensaje_propio(monkeypatch):
    from app import capabilities, trials

    monkeypatch.setattr(
        capabilities, "get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    monkeypatch.setattr(
        trials, "get_trial_state",
        lambda uid, st: {"used": True, "active": False},
    )
    with pytest.raises(HTTPException) as excinfo:
        require_capability_for_user("u1", Capability.STANDARDIZE, FakeSettings())
    assert excinfo.value.status_code == 403
    assert "prueba gratuita" in excinfo.value.detail
    assert "terminó" in excinfo.value.detail


# ── Cuota de IA: sin_plan → 0, jamás un 500 ──────────────────────────────────


def test_limit_for_sin_plan_es_cero_no_keyerror():
    assert quota.limit_for("sin_plan", FakeSettings()) == 0
    assert quota.limit_for("basico", FakeSettings()) == 20


def test_check_quota_sin_plan_responde_403_con_cta(monkeypatch):
    monkeypatch.setattr(
        quota, "get_profile_flags", lambda uid, st: ("sin_plan", False)
    )
    monkeypatch.setattr(quota, "count_month_usage", lambda uid, st, kinds=None: 0)
    with pytest.raises(HTTPException) as excinfo:
        quota.check_quota("u1", FakeSettings())
    assert excinfo.value.status_code == 403
    assert "Plan Básico" in excinfo.value.detail


# ── Gates P0 en los endpoints (el bypass más caro era la IA) ─────────────────


def test_endpoints_de_ia_metricas_y_restore_tienen_puerta():
    """Regresión estructural: si alguien borra el gate, esto falla."""
    import inspect

    from app.routes import ai, pipeline

    for func in (ai.ai_summary, ai.ai_chat, ai.ai_recommendation):
        assert "require_capability_for_user" in inspect.getsource(func), func.__name__
    assert "require_capability_for_user" in inspect.getsource(pipeline.metrics)
    assert "require_capability_for_user" in inspect.getsource(pipeline.restore_latest)


def test_rate_limit_de_activacion():
    from app.routes.me import _TRIAL_ATTEMPT_MAX, _attempts, _guard_activation_rate

    _attempts.clear()
    for _ in range(_TRIAL_ATTEMPT_MAX):
        _guard_activation_rate("user-rate-test")
    with pytest.raises(HTTPException) as excinfo:
        _guard_activation_rate("user-rate-test")
    assert excinfo.value.status_code == 429
    _attempts.clear()


def test_errores_de_terceros_son_genericos():
    """RUT usado por OTRA cuenta jamás revela quién: mensaje genérico."""
    from app.trials import _ERROR_RESPONSES

    status_rut, msg_rut = _ERROR_RESPONSES["RUT_ALREADY_USED_TRIAL"]
    assert "no es elegible" in msg_rut
    assert "cuenta" not in msg_rut.lower() or "contacta" in msg_rut
    # El error del PROPIO usuario sí es específico (no involucra a terceros)
    _, msg_user = _ERROR_RESPONSES["USER_ALREADY_USED_TRIAL"]
    assert "Tu cuenta" in msg_user


# ── Parcialidad POR MES en evolucion_mensual (Fase 14) ───────────────────────


def _csv_meses_con_junio_parcial() -> str:
    filas = [f"{d:02d}/04/2026;1000" for d in range(1, 31)]
    filas += [f"{d:02d}/05/2026;1200" for d in range(1, 32)]
    filas += [f"{d:02d}/06/2026;1500" for d in range(1, 16)]  # junio hasta el 15
    return "Fecha;Ventas\n" + "\n".join(filas)


def test_evolucion_marca_solo_el_ultimo_mes_como_parcial():
    result, _ = _run(_csv_meses_con_junio_parcial())
    m = compute_metrics(result["_df_limpio"])
    evo = {e["mes"]: e for e in m["evolucion_mensual"]}
    assert evo["2026-04"]["parcial"] is False
    assert evo["2026-04"]["dias_del_mes"] == 30
    assert evo["2026-05"]["parcial"] is False
    assert evo["2026-06"]["parcial"] is True
    assert evo["2026-06"]["cobertura_hasta_dia"] == 15
    assert evo["2026-06"]["dias_del_mes"] == 30
    # Fase 14b: el aviso declara el HECHO (último registro), no una causa
    assert any("último registro disponible" in a for a in m["advertencias"])


def test_proyeccion_excluye_mes_parcial_y_no_se_superpone():
    result, _ = _run(_csv_meses_con_junio_parcial())
    m = compute_metrics(result["_df_limpio"])
    # La tasa nace de abril→mayo (30×1000=30.000 → 31×1200=37.200 = +24%),
    # NO de la "caída" ficticia del junio a medio llenar.
    assert m["proyeccion"]["crecimiento_pct"] == 24.0
    # Y los meses proyectados empiezan DESPUÉS del final real (julio).
    assert [x["mes"] for x in m["proyeccion"]["meses"]] == [
        "2026-07", "2026-08", "2026-09",
    ]


def test_mes_final_completo_no_se_marca_parcial():
    filas = [f"{d:02d}/04/2026;1000" for d in range(1, 31)]
    filas += [f"{d:02d}/05/2026;1200" for d in range(1, 32)]  # mayo completo
    csv = "Fecha;Ventas\n" + "\n".join(filas)
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    assert all(e["parcial"] is False for e in m["evolucion_mensual"])
    assert m["proyeccion"]["meses"][0]["mes"] == "2026-06"


# ── format_number: repr() con guardas ─────────────────────────────────────────


def test_format_number_round_trip_float64():
    assert format_number(0.0049) == "0.0049"
    assert format_number(1.23456) == "1.23456"
    assert format_number(850000.0) == "850000"
    # La promesa: no truncar más allá de float64 (el .9f anterior cortaba esto)
    assert format_number(0.1234567891234) == "0.1234567891234"
    assert float(format_number(0.1234567891234)) == 0.1234567891234


def test_format_number_no_explota_con_no_finitos():
    assert format_number(float("nan")) == "nan"
    assert format_number(float("inf")) == "inf"
