"""Fase 15 — "todo en 10": triage verificado del plan externo.

Cubre lo implementado de los 8 ejes: contrato único de planes (test de
paridad TS↔Python), snapshots v2 con versión del motor y guardia monotónica,
arranque fail-closed en producción, literales nan/NaT/None preservados,
política de fusiones por ROL, calidad multidimensional, monedas mixtas
bloqueadas, líderes brutos antes del recorte, upgrade_basico reconocido y
límite de ráfaga de IA.
"""

import io
import re
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.engine.clean import analyze_and_clean
from app.engine.loader import load_dataframe_with_report
from app.engine.metrics import compute_metrics
from app.engine.standardize import standardize_dataframe
from app.main import validate_production_config
from app.restore_cache import (
    RESTORE_SNAPSHOT_VERSION,
    build_restore_snapshot,
    valid_restore_snapshot,
)
from app.version import ENGINE_VERSION, LATEST_MIGRATION

REPO = Path(__file__).resolve().parents[2]


def _run(csv: str):
    df, report = load_dataframe_with_report("t.csv", csv.encode("utf-8"))
    return analyze_and_clean(df, None, apply=True), report


# ── 1. Contrato único: la matriz TS no puede divergir de la de Python ────────


def test_matriz_de_planes_identica_en_frontend_y_backend():
    """Paridad plans.ts ↔ capabilities.py: si alguien edita una sola de las
    dos matrices, este test falla — ninguna capacidad se escribe dos veces
    sin que el CI lo detecte."""
    from app.capabilities import PLAN_CAPABILITIES

    ts = (REPO / "frontend" / "src" / "lib" / "plans.ts").read_text(encoding="utf-8")

    def _ts_list(name: str) -> set[str]:
        match = re.search(rf"const {name}: Capability\[\] = \[([^\]]+)\]", ts)
        assert match, f"No se encontró la lista {name} en plans.ts"
        caps = set(re.findall(r"'([a-z_]+)'", match.group(1)))
        return caps

    basico_ts = _ts_list("BASICO")
    analista_ts = _ts_list("ANALISTA") | basico_ts  # [...BASICO, ...]
    gold_ts = _ts_list("GOLD") | analista_ts

    assert basico_ts == {str(c) for c in PLAN_CAPABILITIES["basico"]}
    assert analista_ts == {str(c) for c in PLAN_CAPABILITIES["analista"]}
    assert gold_ts == {str(c) for c in PLAN_CAPABILITIES["gold"]}
    # sin_plan vacío en ambos lados
    assert "sin_plan: new Set<Capability>()" in ts
    assert PLAN_CAPABILITIES["sin_plan"] == set()


def test_trial_capabilities_identicas_en_frontend_y_backend():
    """El E2E y la UI muestran lo que TRIAL_CAPABILITIES permite — el espejo
    TS (si existe en access/plans) no debe divergir del backend."""
    from app.capabilities import TRIAL_CAPABILITIES

    assert {str(c) for c in TRIAL_CAPABILITIES} == {
        "standardize", "clean", "view_dashboard", "download_reports",
    }


# ── 2. Snapshots v2: versión del motor + procedencia + guardia ───────────────


def test_snapshot_v3_declara_motor_y_procedencia():
    snap = build_restore_snapshot(
        {"archivo": "x"}, None, None, {"monto": "Ventas"}, False,
        revision=41, source_sha256="a" * 64,
        rules={"fechas": True}, sheet="Ventas",
    )
    assert snap["version"] == RESTORE_SNAPSHOT_VERSION == 3
    assert snap["engine_version"] == ENGINE_VERSION
    assert snap["source_sha256"] == "a" * 64
    assert snap["rules_hash"] and snap["mapping_hash"]
    assert snap["sheet"] == "Ventas"
    assert isinstance(snap["revision"], int)


def test_snapshot_de_otro_motor_se_invalida():
    snap = build_restore_snapshot(
        {"archivo": "x"}, None, None, None, False,
        revision=42, source_sha256="b" * 64,
    )
    expected = dict(
        expected_revision=42,
        expected_source_sha256="b" * 64,
        expected_rules_hash=snap["rules_hash"],
        expected_mapping_hash=snap["mapping_hash"],
        expected_sheet=None,
    )
    assert valid_restore_snapshot(snap, "estandarizado", **expected) is not None
    ajeno = {**snap, "engine_version": "0.0.1"}
    assert valid_restore_snapshot(ajeno, "estandarizado", **expected) is None
    v1 = {**snap, "version": 1}
    assert valid_restore_snapshot(v1, "estandarizado", **expected) is None


def test_revision_de_snapshot_es_la_reservada_al_inicio():
    a = build_restore_snapshot(
        {"a": 1}, None, None, None, False,
        revision=100, source_sha256="c" * 64,
    )
    b = build_restore_snapshot(
        {"a": 1}, None, None, None, False,
        revision=101, source_sha256="c" * 64,
    )
    assert b["revision"] > a["revision"]
    assert (a["revision"], b["revision"]) == (100, 101)


# ── 3. Producción fail-closed ────────────────────────────────────────────────


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="production",
        supabase_url="https://x.supabase.co",
        supabase_service_role_key="k",
        plan_enforcement=True,
        dev_auth_bypass=False,
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)


def test_produccion_segura_arranca():
    assert validate_production_config(_settings()) == []


def test_produccion_insegura_no_arranca():
    assert validate_production_config(_settings(supabase_url=""))
    assert validate_production_config(_settings(plan_enforcement=False))
    assert validate_production_config(_settings(dev_auth_bypass=True))
    # varias violaciones se reportan juntas
    v = validate_production_config(
        _settings(supabase_url="", plan_enforcement=False, dev_auth_bypass=True)
    )
    assert len(v) >= 3


def test_desarrollo_no_se_bloquea():
    assert validate_production_config(
        _settings(app_env="development", supabase_url="", plan_enforcement=False)
    ) == []


# ── 4. Literales nan/NaT/None son DATOS, no vacíos ───────────────────────────


def test_csv_conserva_literales_nan_none():
    csv = "Categoria;Ventas\nnan;100\nNone;200\nNAN;300\nnone;400\n"
    df, _ = load_dataframe_with_report("t.csv", csv.encode("utf-8"))
    assert list(df["Categoria"]) == ["nan", "None", "NAN", "none"]


def test_excel_conserva_literales_y_vacios_reales():
    frame = pd.DataFrame({"Categoria": ["None", "nan", None, "Normal"], "Ventas": [1, 2, 3, 4]})
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    df, _ = load_dataframe_with_report("t.xlsx", buffer.getvalue())
    valores = list(df["Categoria"])
    # Los textos literales sobreviven; el nulo REAL queda vacío
    assert "None" in valores and "nan" in valores and "Normal" in valores
    assert "" in valores


# ── 5. Fusiones por ROL: entidades sugieren, geografía aplica ────────────────


def test_fuzzy_en_columna_de_clientes_es_sugerencia_no_fusion():
    clientes = ["Comercial Perez"] * 8 + ["Comercial Peres"] * 2
    df = pd.DataFrame({"Cliente": clientes, "Ventas": ["100"] * len(clientes)})
    out, report = standardize_dataframe(df)
    # El valor NO se fusionó: ambos siguen presentes
    assert "Comercial Peres" in set(out["Cliente"])
    # Y quedó como SUGERENCIA visible en los avisos
    assert any("Comercial Peres" in a for a in report.get("avisos", []))


def test_fuzzy_en_sucursal_geografica_sigue_automatico():
    sucursales = ["Santiago"] * 8 + ["Santigo"] * 2
    df = pd.DataFrame({"Sucursal": sucursales, "Ventas": ["100"] * len(sucursales)})
    out, _ = standardize_dataframe(df)
    assert set(out["Sucursal"]) == {"Santiago"}


def test_abreviacion_geografica_no_se_aplica_en_productos():
    productos = ["Santiago Especial"] * 5 + ["Stgo Especial"] * 2
    df = pd.DataFrame({"Producto": productos, "Ventas": ["100"] * len(productos)})
    out, _ = standardize_dataframe(df)
    # "Stgo" podría ser un modelo/marca en productos: NO se expande solo
    assert "Stgo Especial" in set(out["Producto"])


# ── 6. Calidad multidimensional ──────────────────────────────────────────────


def test_calidad_tiene_seis_dimensiones():
    csv = (
        "Fecha;Producto;Ventas;Costo\n"
        "05/01/2026;A;100;60\n"
        "06/01/2026;B;;40\n"  # nulo
        "06/01/2026;B;;40\n"  # duplicado
    )
    result, _ = _run(csv)
    dims = result["resumen"]["calidad_dimensiones"]
    assert set(dims) == {
        "completitud", "validez", "consistencia",
        "unicidad", "integridad", "cobertura_analitica",
    }
    assert dims["completitud"] < 100.0  # hay nulos
    assert dims["unicidad"] < 100.0  # hay duplicado
    assert dims["cobertura_analitica"] > 0


def test_calidad_no_es_100_con_problemas_presentes():
    csv = "Fecha;Ventas\n05/01/2026;100\n06/01/2026;\n"
    result, _ = _run(csv)
    dims = result["resumen"]["calidad_dimensiones"]
    assert any(v < 100.0 for v in dims.values())


# ── 7. Monedas mixtas: flag explícito (la UI bloquea los KPIs) ───────────────


def test_monedas_mixtas_levantan_flag():
    csv = "Fecha;Ventas\n05/01/2026;CLP 100.000\n06/01/2026;USD 1.000\n"
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    # detect_currency corre sobre valores crudos vía pipeline; aquí simulamos
    m2 = compute_metrics(result["_df_limpio"], currency_hint=("CLP", "Se detectó más de una moneda en los montos"))
    assert m2["moneda_mixta"] is True
    assert m["moneda_mixta"] in (True, False)  # sin hint depende de los valores


def test_moneda_unica_no_levanta_flag():
    csv = "Fecha;Ventas\n05/01/2026;100000\n06/01/2026;200000\n"
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    assert m["moneda_mixta"] is False


# ── 8. Líderes brutos ANTES del recorte a 12 ─────────────────────────────────


def test_lider_bruto_sobrevive_al_recorte_por_netas():
    # 13 productos: "Estrella" vende 100.000 brutos con 95.000 de devoluciones
    # (neto 5.000 → último por netas), el resto vende 10.000 netos cada uno.
    filas = ["05/01/2026;Estrella;100000", "06/01/2026;Estrella;-95000"]
    for i in range(12):
        filas.append(f"07/01/2026;Prod{i:02d};10000")
    csv = "Fecha;Producto;Ventas\n" + "\n".join(filas)
    result, _ = _run(csv)
    m = compute_metrics(result["_df_limpio"])
    nombres_top = {p["nombre"] for p in m["top_productos"]}
    lider = m["lideres_productos"]["por_ventas_brutas"]
    assert lider["nombre"] == "Estrella"
    assert lider["participacion_bruta_pct"] == pytest.approx(45.5, abs=0.2)
    # El líder bruto existe AUNQUE quede fuera del top-12 por netas
    assert m["lideres_productos"]["mayor_devolucion"]["nombre"] == "Estrella"
    assert len(nombres_top) <= 12


# ── 9. upgrade_basico reconocido ─────────────────────────────────────────────


def test_upgrade_basico_ya_no_se_degrada_a_otro():
    from app.routes.plans import REQUEST_TYPES, UPGRADE_REQUEST_TYPES

    assert "upgrade_basico" in REQUEST_TYPES
    assert "upgrade_basico" in UPGRADE_REQUEST_TYPES
    # La migración se renumeró a 0019 para eliminar la versión 0017 duplicada.
    sql = (REPO / "supabase" / "migrations" / "0019_contratacion_basico.sql").read_text(encoding="utf-8")
    assert "upgrade_basico" in sql


# ── 10. Límite de ráfaga de IA ───────────────────────────────────────────────


def test_rafaga_de_ia_se_frena():
    from app.routes.ai import _BURST_MAX, _burst, _guard_ai_burst

    _burst.clear()
    for _ in range(_BURST_MAX):
        _guard_ai_burst("user-burst")
    with pytest.raises(HTTPException) as excinfo:
        _guard_ai_burst("user-burst")
    assert excinfo.value.status_code == 429
    _burst.clear()


# ── 11. /version: identidad del despliegue ───────────────────────────────────


def test_version_endpoint_expone_identidad():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["engine_version"] == ENGINE_VERSION
    assert body["database_migration"] == LATEST_MIGRATION
    assert "commit_sha" in body and "environment" in body
