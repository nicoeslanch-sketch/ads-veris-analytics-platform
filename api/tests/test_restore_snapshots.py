"""Fast restoration: persistent snapshot first, full pipeline as fallback."""

import json
import hashlib
import time
from statistics import median

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.engine.clean import DEFAULT_RULES
from app.restore_cache import (
    RESTORE_SNAPSHOT_VERSION,
    RestoreSnapshotUnavailable,
    build_restore_snapshot,
    store_restore_snapshot,
    valid_restore_snapshot,
)


SOURCE_SHA = "d" * 64


def test_cleaning_result_is_not_lost_when_guarded_snapshot_cannot_be_saved(
    client, auth_headers, monkeypatch
):
    from app.routes import pipeline as pl

    dataset_id = "00000000-0000-0000-0000-000000000099"
    monkeypatch.setattr(pl, "reserve_restore_snapshot_revision", lambda *_args: 99)

    def reject_snapshot(*_args, **_kwargs):
        raise HTTPException(
            status_code=503,
            detail="El resultado se calculó, pero no pudo confirmarse su persistencia.",
        )

    monkeypatch.setattr(pl, "_build_and_store_restore_snapshot", reject_snapshot)
    csv = (
        "SKU_Producto;Costo Unitario;Fecha Vigencia\n"
        "SKU-001;1200;01/01/2026\n"
        "SKU-002;1500;02/01/2026\n"
    ).encode("utf-8")

    response = client.post(
        "/clean",
        headers=auth_headers,
        data={"apply": "true", "dataset_id": dataset_id},
        files={"file": ("costos.csv", csv, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resumen"]["aplicado"] is True
    assert body["resumen"]["filas_despues"] == 2
    assert body["persistencia"] == {
        "guardada": False,
        "mensaje": "El resultado se calculó, pero no pudo confirmarse su persistencia.",
    }


def test_cleaning_stale_revision_is_still_rejected(
    client, auth_headers, monkeypatch
):
    from app.routes import pipeline as pl

    dataset_id = "00000000-0000-0000-0000-000000000098"
    monkeypatch.setattr(pl, "reserve_restore_snapshot_revision", lambda *_args: 98)
    def reject_snapshot(*_args, **_kwargs):
        raise HTTPException(
            status_code=409,
            detail=(
                "Esta limpieza quedó obsoleta porque ya existe una acción "
                "más reciente. Se conservó el resultado nuevo."
            ),
        )

    monkeypatch.setattr(pl, "_build_and_store_restore_snapshot", reject_snapshot)
    response = client.post(
        "/clean",
        headers=auth_headers,
        data={"apply": "true", "dataset_id": dataset_id},
        files={"file": ("ventas.csv", b"Monto\n1000\n", "text/csv")},
    )

    assert response.status_code == 409
    assert "acción más reciente" in response.json()["detail"]


def _snapshot(revision: int = 10, sheet: str | None = None) -> dict:
    return build_restore_snapshot(
        {"archivo": "ventas.csv", "filas": 2},
        {
            "archivo": "ventas.csv",
            "resumen": {"aplicado": True},
            "reglas_activas": dict(DEFAULT_RULES),
        },
        {
            "archivo": "ventas.csv",
            "periodo": {"desde": None, "hasta": None, "meses_disponibles": []},
        },
        {"monto": "Ventas"},
        False,
        revision=revision,
        source_sha256=SOURCE_SHA,
        rules=DEFAULT_RULES,
        sheet=sheet,
    )


def _expected(snapshot: dict) -> dict:
    return {
        "expected_revision": snapshot["revision"],
        "expected_source_sha256": snapshot["source_sha256"],
        "expected_rules_hash": snapshot["rules_hash"],
        "expected_mapping_hash": snapshot["mapping_hash"],
        "expected_sheet": snapshot["sheet"],
    }


def test_snapshot_versionado_exige_todas_las_etapas_para_dataset_limpio():
    snapshot = _snapshot()
    assert snapshot["version"] == RESTORE_SNAPSHOT_VERSION
    assert valid_restore_snapshot(snapshot, "limpio", **_expected(snapshot)) is snapshot

    stale = {**snapshot, "version": RESTORE_SNAPSHOT_VERSION - 1}
    assert valid_restore_snapshot(stale, "limpio", **_expected(snapshot)) is None
    assert valid_restore_snapshot(
        {**snapshot, "metrics": None}, "limpio", **_expected(snapshot)
    ) is None


def test_snapshot_de_otro_motor_solo_se_admite_para_restauracion_transitoria():
    snapshot = _snapshot()
    stale = {**snapshot, "engine_version": "0.21.0"}

    assert valid_restore_snapshot(stale, "limpio", **_expected(snapshot)) is None
    assert valid_restore_snapshot(
        stale,
        "limpio",
        **_expected(snapshot),
        allow_engine_mismatch=True,
    ) is stale
    changed_mapping = {**stale, "mapping": {"monto": "Otra"}}
    assert valid_restore_snapshot(
        changed_mapping,
        "limpio",
        **_expected(snapshot),
        allow_engine_mismatch=True,
    ) is None


def test_restore_stale_devuelve_limpieza_sin_metricas_y_sin_descargar(monkeypatch):
    from app.routes import pipeline as pl

    user_id = "user-test-123"
    snapshot = {**_snapshot(), "engine_version": "0.21.0"}
    state = {
        "active_sheet": None,
        "available_sheets": [],
        "excluded_sheets": [],
        "selected_sheets": [],
        "sheet_errors": {},
        "analysis_scope": {},
        "combine_sheets": False,
        "source_sha256": snapshot["source_sha256"],
        "engine_version": snapshot["engine_version"],
    }
    row = {
        "sheet_key": "__single__",
        "revision": snapshot["revision"],
        "source_sha256": snapshot["source_sha256"],
        "rules_hash": snapshot["rules_hash"],
        "mapping_hash": snapshot["mapping_hash"],
        "sheet": None,
        "engine_version": snapshot["engine_version"],
        "snapshot": snapshot,
    }
    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda _user_id: {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "ventas.csv",
            "source": "excel_csv",
            "storage_path": f"{user_id}/ventas.csv",
            "status": "limpio",
        },
    )
    monkeypatch.setattr(
        pl, "fetch_restore_state_bundle", lambda *_args, **_kwargs: {"state": state, "sheets": [row]}
    )
    monkeypatch.setattr(
        pl,
        "download_from_storage",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("La restauración transitoria no descarga el archivo")
        ),
    )

    body = pl._restore_latest_sync(user_id)

    assert body["source"] == "snapshot_stale"
    assert body["refresh_required"] is True
    assert body["cleaning"] is not None
    assert body["metrics"] is None


def test_refresh_recalcula_el_snapshot_guardado_con_una_revision_nueva(monkeypatch):
    from app.routes import pipeline as pl

    user_id = "user-test-123"
    dataset_id = "00000000-0000-0000-0000-000000000001"
    content = b"Fecha;Ventas;Producto\n01/05/2026;1000;Servicio A\n"
    source_sha = hashlib.sha256(content).hexdigest()
    old = {
        **_snapshot(),
        "engine_version": "0.21.0",
        "source_sha256": source_sha,
    }
    state = {
        "active_sheet": None,
        "available_sheets": [],
        "excluded_sheets": [],
        "selected_sheets": [],
        "sheet_errors": {},
        "analysis_scope": {},
        "combine_sheets": False,
        "source_sha256": source_sha,
        "engine_version": old["engine_version"],
    }
    row = {
        "sheet_key": "__single__",
        "revision": old["revision"],
        "source_sha256": source_sha,
        "rules_hash": old["rules_hash"],
        "mapping_hash": old["mapping_hash"],
        "sheet": None,
        "engine_version": old["engine_version"],
        "snapshot": old,
    }
    stored: list[dict] = []
    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda _user_id: {
            "id": dataset_id,
            "name": "ventas.csv",
            "source": "excel_csv",
            "storage_path": f"{user_id}/ventas.csv",
            "status": "limpio",
        },
    )
    monkeypatch.setattr(pl, "fetch_restore_state_metadata", lambda *_args: state)
    monkeypatch.setattr(
        pl, "fetch_restore_state_bundle", lambda *_args, **_kwargs: {"state": state, "sheets": [row]}
    )
    monkeypatch.setattr(pl, "reserve_restore_snapshot_revision", lambda *_args: 44)
    monkeypatch.setattr(pl, "download_from_storage", lambda _path: content)
    monkeypatch.setattr(
        pl,
        "store_restore_snapshot",
        lambda _dataset_id, _user_id, snapshot, **_kwargs: stored.append(snapshot) or True,
    )

    body = pl._refresh_restore_sync(user_id)

    assert body["source"] == "refreshed"
    assert body["cleaning"]["revision"] == 44
    assert body["metrics"]["kpis"]["ingresos_totales"]["valor"] == 1000
    assert len(stored) == 1
    assert stored[0]["revision"] == 44


def test_snapshot_recalcula_hashes_y_exige_sha256_real():
    snapshot = _snapshot()
    changed_mapping = {**snapshot, "mapping": {"monto": "Otra columna"}}
    assert valid_restore_snapshot(
        changed_mapping, "limpio", **_expected(snapshot)
    ) is None

    changed_rules = {
        **snapshot,
        "cleaning": {**snapshot["cleaning"], "reglas_activas": {"fechas": False}},
    }
    assert valid_restore_snapshot(changed_rules, "limpio", **_expected(snapshot)) is None

    invalid_sha = {**snapshot, "source_sha256": "x" * 64}
    invalid_expected = {**_expected(snapshot), "expected_source_sha256": "x" * 64}
    assert valid_restore_snapshot(invalid_sha, "limpio", **invalid_expected) is None


def test_restore_latest_requiere_autenticacion(client):
    response = client.post("/restore/latest", json={})
    assert response.status_code == 401


def test_store_snapshot_confirma_fila_y_filtra_por_propietario(monkeypatch):
    from app import restore_cache

    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(200, json=True)

    monkeypatch.setattr(restore_cache.httpx, "post", fake_post)
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )
    saved = store_restore_snapshot(
        "00000000-0000-0000-0000-000000000001",
        "owner-123",
        _snapshot(),
        settings,
    )

    assert saved is True
    assert captured["url"].endswith("/rpc/store_restore_snapshot_guarded")
    assert captured["json"]["p_user_id"] == "owner-123"
    assert captured["json"]["p_snapshot"]["version"] == RESTORE_SNAPSHOT_VERSION


def test_store_snapshot_distingue_indisponibilidad_de_revision_obsoleta(monkeypatch):
    from app import restore_cache

    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )

    def unavailable(*_args, **_kwargs):
        raise HTTPException(status_code=502, detail="Supabase no disponible")

    monkeypatch.setattr(restore_cache, "_post_rpc", unavailable)
    with pytest.raises(RestoreSnapshotUnavailable):
        store_restore_snapshot(
            "00000000-0000-0000-0000-000000000001",
            "owner-123",
            _snapshot(),
            settings,
            raise_on_unavailable=True,
        )

    monkeypatch.setattr(
        restore_cache,
        "_post_rpc",
        lambda *_args, **_kwargs: httpx.Response(200, json=False),
    )
    assert store_restore_snapshot(
        "00000000-0000-0000-0000-000000000001",
        "owner-123",
        _snapshot(),
        settings,
        raise_on_unavailable=True,
    ) is False


@pytest.mark.parametrize("selection_mode", ["all", "custom"])
def test_selection_mode_round_trip_uses_analysis_scope_json(
    monkeypatch, selection_mode
):
    from app import restore_cache
    from app.routes import pipeline as pl

    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(200, json=True)

    monkeypatch.setattr(restore_cache.httpx, "post", fake_post)
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )
    snapshot = _snapshot(sheet="Ventas")
    state = {
        "active_sheet": "Ventas",
        "available_sheets": ["Ventas", "Productos"],
        "excluded_sheets": [] if selection_mode == "all" else ["Productos"],
        "selected_sheets": (
            ["Ventas", "Productos"] if selection_mode == "all" else ["Ventas"]
        ),
        "sheet_errors": {},
        "analysis_scope": {
            "mode": "single",
            "sheets": ["Ventas"],
            "active_sheet": "Ventas",
        },
        "selection_mode": selection_mode,
    }

    assert store_restore_snapshot(
        "00000000-0000-0000-0000-000000000001",
        "owner-123",
        snapshot,
        settings,
        restore_state=state,
    ) is True
    persisted_scope = captured["json"]["p_analysis_scope"]
    assert persisted_scope["_selection_mode"] == selection_mode

    restored = pl._restore_response(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "libro.xlsx",
            "storage_path": "owner-123/libro.xlsx",
            "status": "limpio",
        },
        snapshot,
        "snapshot",
        restore_state={
            **state,
            "analysis_scope": persisted_scope,
            # La tabla no tiene una columna selection_mode: esta clave no
            # vuelve desde Supabase y debe reconstruirse desde el JSONB.
            "selection_mode": None,
        },
    )
    assert restored["selection_mode"] == selection_mode


def test_selection_mode_without_analysis_scope_does_not_expose_internal_marker(
    monkeypatch,
):
    from app import restore_cache
    from app.routes import pipeline as pl

    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(200, json=True)

    monkeypatch.setattr(restore_cache.httpx, "post", fake_post)
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )
    snapshot = _snapshot(sheet="Ventas")
    state = {
        "active_sheet": "Ventas",
        "available_sheets": ["Ventas"],
        "excluded_sheets": [],
        "selected_sheets": ["Ventas"],
        "sheet_errors": {},
        "analysis_scope": None,
        "selection_mode": "custom",
    }

    assert store_restore_snapshot(
        "00000000-0000-0000-0000-000000000001",
        "owner-123",
        snapshot,
        settings,
        restore_state=state,
    ) is True
    persisted_scope = captured["json"]["p_analysis_scope"]
    assert persisted_scope == {"_selection_mode": "custom"}

    restored = pl._restore_response(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "libro.xlsx",
            "storage_path": "owner-123/libro.xlsx",
            "status": "limpio",
        },
        snapshot,
        "snapshot",
        restore_state={**state, "analysis_scope": persisted_scope, "selection_mode": None},
    )
    assert restored["selection_mode"] == "custom"
    assert restored["analysis_scope"] is None


def test_restore_state_endpoint_persists_last_failed_sheet_and_recovers_it(
    client, auth_headers, monkeypatch
):
    from app.routes import pipeline as pl

    dataset_id = "00000000-0000-0000-0000-000000000031"
    source_sha = SOURCE_SHA
    existing = _snapshot(revision=30, sheet="Productos")
    existing_cleaning = existing["cleaning"]
    record = {
        "id": dataset_id,
        "name": "libro.xlsx",
        "source": "excel_csv",
        "storage_path": "user-test-123/libro.xlsx",
        "status": "limpio",
    }
    authoritative = {
        "dataset_id": dataset_id,
        "user_id": "user-test-123",
        "revision": 30,
        "active_sheet": "Ventas",
        "available_sheets": ["Ventas", "Productos"],
        "excluded_sheets": [],
        "selected_sheets": ["Ventas", "Productos"],
        "sheet_errors": {},
        "analysis_scope": {},
        "combine_sheets": False,
        "source_sha256": source_sha,
        "engine_version": existing["engine_version"],
    }

    def row(snapshot):
        return {
            "sheet_key": "Productos",
            "revision": snapshot["revision"],
            "source_sha256": snapshot["source_sha256"],
            "rules_hash": snapshot["rules_hash"],
            "mapping_hash": snapshot["mapping_hash"],
            "sheet": snapshot["sheet"],
            "engine_version": snapshot["engine_version"],
            "snapshot": snapshot,
        }

    stored: dict = {}
    monkeypatch.setattr(pl, "require_capability_for_user", lambda *_args: "ok")
    monkeypatch.setattr(pl, "reserve_restore_snapshot_revision", lambda *_args: 31)
    monkeypatch.setattr(pl, "fetch_restore_record", lambda *_args: record)
    monkeypatch.setattr(
        pl,
        "fetch_restore_state_bundle",
        lambda *_args, **_kwargs: {
            "state": authoritative,
            "sheets": [row(existing)],
        },
    )

    def fake_store(
        _dataset_id,
        _user_id,
        snapshot,
        settings=None,
        restore_state=None,
    ):
        stored.update({"snapshot": snapshot, "state": restore_state})
        return True

    monkeypatch.setattr(pl, "store_restore_snapshot", fake_store)
    requested_state = {
        "active_sheet": "Productos",
        "available_sheets": ["Ventas", "Productos"],
        "excluded_sheets": [],
        "selected_sheets": ["Ventas", "Productos"],
        "sheet_errors": {"Productos": "La limpieza falló en esta hoja."},
        "analysis_scope": {
            "mode": "single",
            "sheets": ["Productos"],
            "active_sheet": "Productos",
        },
        "selection_mode": "all",
        "combine_sheets": False,
    }

    response = client.post(
        "/restore/state",
        data={
            "dataset_id": dataset_id,
            "restore_state": json.dumps(requested_state),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 31
    assert stored["snapshot"]["revision"] == 31
    assert stored["snapshot"]["cleaning"] == existing_cleaning
    assert existing["revision"] == 30
    assert stored["state"]["sheet_errors"] == requested_state["sheet_errors"]

    cloned = stored["snapshot"]
    restored = pl._restore_response(
        record,
        cloned,
        "snapshot",
        sheet_sessions={
            "Productos": {
                "standardization": cloned["standardization"],
                "cleaning": cloned["cleaning"],
                "metrics": cloned["metrics"],
                "mapping": cloned["mapping"],
                "eliminar_duplicados": cloned["eliminar_duplicados"],
            }
        },
        restore_state=stored["state"],
    )
    assert restored["sheet_errors"] == requested_state["sheet_errors"]
    assert restored["active_sheet"] == "Productos"
    assert restored["cleaning"] == existing_cleaning


def test_restore_state_endpoint_blocks_when_no_valid_snapshot(
    client, auth_headers, monkeypatch
):
    from app.routes import pipeline as pl

    dataset_id = "00000000-0000-0000-0000-000000000032"
    monkeypatch.setattr(pl, "require_capability_for_user", lambda *_args: "ok")
    monkeypatch.setattr(pl, "reserve_restore_snapshot_revision", lambda *_args: 32)
    monkeypatch.setattr(
        pl,
        "fetch_restore_record",
        lambda *_args: {
            "id": dataset_id,
            "name": "libro.xlsx",
            "storage_path": "user-test-123/libro.xlsx",
            "status": "limpio",
        },
    )
    monkeypatch.setattr(
        pl,
        "fetch_restore_state_bundle",
        lambda *_args, **_kwargs: {
            "state": {
                "dataset_id": dataset_id,
                "user_id": "user-test-123",
                "available_sheets": ["Ventas"],
                "source_sha256": SOURCE_SHA,
                "engine_version": _snapshot()["engine_version"],
            },
            "sheets": [],
        },
    )
    monkeypatch.setattr(
        pl,
        "store_restore_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("no debe escribir sin snapshot válido")
        ),
    )

    response = client.post(
        "/restore/state",
        data={
            "dataset_id": dataset_id,
            "restore_state": json.dumps(
                {
                    "active_sheet": "Ventas",
                    "available_sheets": ["Ventas"],
                    "excluded_sheets": [],
                    "selected_sheets": ["Ventas"],
                    "sheet_errors": {"Ventas": "falló"},
                    "selection_mode": "all",
                }
            ),
        },
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "snapshot vigente" in response.json()["detail"]


def test_store_snapshot_grande_usa_tabla_dedicada_sin_limite_512k(monkeypatch):
    from app import restore_cache

    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(200, json=True)

    monkeypatch.setattr(restore_cache.httpx, "post", fake_post)
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )
    snapshot = _snapshot()
    snapshot["standardization"]["payload"] = "x" * (600 * 1024)
    assert store_restore_snapshot(
        "00000000-0000-0000-0000-000000000001",
        "owner-123",
        snapshot,
        settings,
    ) is True
    assert len(captured["json"]["p_snapshot"]["standardization"]["payload"]) > 512 * 1024


def test_store_snapshot_no_degrada_a_rpc_antiguo_si_falta_estado_completo(monkeypatch):
    from app import restore_cache

    calls: list[str] = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return httpx.Response(404, json={"message": "missing v2"})

    monkeypatch.setattr(restore_cache.httpx, "post", fake_post)
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )
    saved = store_restore_snapshot(
        "00000000-0000-0000-0000-000000000001",
        "owner-123",
        _snapshot(),
        settings,
        restore_state={
            "selected_sheets": ["Ventas"],
            "sheet_errors": {},
            "analysis_scope": {"mode": "single", "sheets": ["Ventas"], "active_sheet": "Ventas"},
        },
    )

    assert saved is False
    assert len(calls) == 1
    assert calls[0].endswith("/rpc/store_restore_snapshot_guarded_v2")


def test_restore_latest_usa_snapshot_sin_descargar_archivo(
    client, auth_headers, monkeypatch
):
    from app.routes import pipeline as pl

    snapshot = _snapshot()
    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda user_id: {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "ventas.csv",
            "source": "excel_csv",
            "storage_path": f"{user_id}/ventas.csv",
            "status": "limpio",
            "restore_snapshot": snapshot,
        },
    )
    monkeypatch.setattr(
        pl,
        "fetch_restore_state_bundle",
        lambda _dataset_id, _user_id: {
            "state": {
                "active_sheet": None,
                "available_sheets": [],
                "excluded_sheets": [],
                "combine_sheets": False,
                "source_sha256": snapshot["source_sha256"],
                "engine_version": snapshot["engine_version"],
            },
            "sheets": [
                {
                    "sheet_key": "__single__",
                    "revision": snapshot["revision"],
                    "source_sha256": snapshot["source_sha256"],
                    "rules_hash": snapshot["rules_hash"],
                    "mapping_hash": snapshot["mapping_hash"],
                    "sheet": snapshot["sheet"],
                    "engine_version": snapshot["engine_version"],
                    "snapshot": snapshot,
                }
            ],
        },
    )

    def should_not_download(_path):
        raise AssertionError("A valid snapshot must not download the source file")

    monkeypatch.setattr(pl, "download_from_storage", should_not_download)
    response = client.post("/restore/latest", json={}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "snapshot"
    assert body["dataset"]["name"] == "ventas.csv"
    assert body["metrics"]["archivo"] == "ventas.csv"


def test_restore_latest_recalcula_v2_y_lo_deja_intacto(monkeypatch):
    from app.routes import pipeline as pl

    user_id = "user-test-123"
    dataset_id = "00000000-0000-0000-0000-000000000002"
    content = (
        "Fecha;Ventas;Producto\n"
        "01/05/2026;1000;Servicio A\n"
        "02/05/2026;2000;Servicio B\n"
    ).encode()
    stored: list[dict] = []
    legacy_v2 = {
        "version": 2,
        "engine_version": "0.18.0",
        "sentinel": "snapshot legacy intacto",
    }

    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda _user_id: {
            "id": dataset_id,
            "name": "restaurar.csv",
            "source": "excel_csv",
            "storage_path": f"{user_id}/restaurar.csv",
            "status": "limpio",
            "restore_snapshot": legacy_v2,
        },
    )
    monkeypatch.setattr(pl, "download_from_storage", lambda _path: content)
    monkeypatch.setattr(pl, "fetch_restore_state_bundle", lambda *_args: None)
    monkeypatch.setattr(pl, "reserve_restore_snapshot_revision", lambda *_args: 77)
    monkeypatch.setattr(pl, "fetch_dataset_mapping", lambda _dataset_id: None)
    monkeypatch.setattr(
        pl,
        "fetch_latest_cleaning_config",
        lambda _dataset_id, _user_id: (dict(DEFAULT_RULES), False),
    )
    monkeypatch.setattr(
        pl,
        "store_restore_snapshot",
        lambda _dataset_id, _user_id, snapshot, restore_state=None, **_kwargs: stored.append(snapshot) or True,
    )

    body = pl._restore_latest_sync(user_id)

    assert body["source"] == "computed"
    assert body["standardization"]["filas"] == 2
    assert body["cleaning"]["resumen"]["aplicado"] is True
    assert body["metrics"]["kpis"]["ingresos_totales"]["valor"] == 3000.0
    assert stored and stored[0]["version"] == RESTORE_SNAPSHOT_VERSION
    assert legacy_v2 == {
        "version": 2,
        "engine_version": "0.18.0",
        "sentinel": "snapshot legacy intacto",
    }


def test_restore_recalculado_conserva_seleccion_multihoja(monkeypatch):
    from app.routes import pipeline as pl

    user_id = "user-test-123"
    dataset_id = "00000000-0000-0000-0000-000000000012"
    content = (
        "Fecha;Ventas;Producto\n"
        "01/05/2026;1000;Servicio A\n"
        "02/05/2026;2000;Servicio B\n"
    ).encode()
    stale = {**_snapshot(sheet=None), "engine_version": "0.0.0"}
    state = {
        "active_sheet": None,
        "available_sheets": ["Ventas", "Costos", "LEEME"],
        "excluded_sheets": ["LEEME"],
        "selected_sheets": ["Ventas", "Costos"],
        "sheet_errors": {},
        "analysis_scope": {"_selection_mode": "custom"},
        "combine_sheets": False,
        "source_sha256": stale["source_sha256"],
        "engine_version": "0.0.0",
    }
    stored_states: list[dict | None] = []

    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda _user_id: {
            "id": dataset_id,
            "name": "restaurar.csv",
            "source": "excel_csv",
            "storage_path": f"{user_id}/restaurar.csv",
            "status": "limpio",
        },
    )
    monkeypatch.setattr(
        pl,
        "fetch_restore_state_bundle",
        lambda *_args, **_kwargs: {
            "state": state,
            "sheets": [
                {
                    "sheet_key": "__single__",
                    "revision": stale["revision"],
                    "source_sha256": stale["source_sha256"],
                    "rules_hash": stale["rules_hash"],
                    "mapping_hash": stale["mapping_hash"],
                    "sheet": stale["sheet"],
                    "engine_version": stale["engine_version"],
                    "snapshot": stale,
                }
            ],
        },
    )
    monkeypatch.setattr(pl, "download_from_storage", lambda _path: content)
    monkeypatch.setattr(pl, "reserve_restore_snapshot_revision", lambda *_args: 78)
    monkeypatch.setattr(pl, "fetch_dataset_mapping", lambda _dataset_id: None)
    monkeypatch.setattr(
        pl,
        "fetch_latest_cleaning_config",
        lambda _dataset_id, _user_id: (dict(DEFAULT_RULES), False),
    )
    monkeypatch.setattr(
        pl,
        "store_restore_snapshot",
        lambda _dataset_id, _user_id, _snapshot, restore_state=None, **_kwargs: (
            stored_states.append(restore_state) or True
        ),
    )

    body = pl._restore_latest_sync(user_id)

    assert body["source"] == "snapshot_stale"
    assert body["refresh_required"] is True
    assert body["metrics"] is None
    assert body["selected_sheets"] == ["Ventas", "Costos"]
    assert body["excluded_sheets"] == ["LEEME"]
    assert body["selection_mode"] == "custom"
    assert body["available_sheets"] == ["Ventas", "Costos", "LEEME"]
    assert stored_states == []


def test_restore_multihoja_recupera_sesiones_activa_excluidas_y_combinacion(monkeypatch):
    from app.routes import pipeline as pl

    january = _snapshot(revision=20, sheet="Enero")
    february = _snapshot(revision=21, sheet="Febrero")
    stale = {
        **_snapshot(revision=19, sheet="Stale"),
        "source_sha256": "e" * 64,
    }
    february["standardization"] = {
        **february["standardization"],
        "archivo": "libro.xlsx",
        "carga": {"hoja_usada": "Febrero", "hojas_disponibles": ["Enero", "Febrero", "Notas"]},
    }
    january["standardization"] = {
        **january["standardization"],
        "archivo": "libro.xlsx",
        "carga": {"hoja_usada": "Enero", "hojas_disponibles": ["Enero", "Febrero", "Notas"]},
    }

    def row(key, snapshot):
        return {
            "sheet_key": key,
            "revision": snapshot["revision"],
            "source_sha256": snapshot["source_sha256"],
            "rules_hash": snapshot["rules_hash"],
            "mapping_hash": snapshot["mapping_hash"],
            "sheet": snapshot["sheet"],
            "engine_version": snapshot["engine_version"],
            "snapshot": snapshot,
        }

    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda _uid: {
            "id": "00000000-0000-0000-0000-000000000009",
            "name": "libro.xlsx",
            "source": "excel_csv",
            "storage_path": f"{_uid}/libro.xlsx",
            "status": "limpio",
        },
    )
    monkeypatch.setattr(
        pl,
        "fetch_restore_state_bundle",
        lambda *_args: {
            "state": {
                "active_sheet": "Febrero",
                "available_sheets": ["Enero", "Febrero", "Notas"],
                "excluded_sheets": ["Notas"],
                "combine_sheets": True,
                "source_sha256": SOURCE_SHA,
                "engine_version": february["engine_version"],
            },
            "sheets": [
                row("Enero", january),
                row("Febrero", february),
                row("Stale", stale),
            ],
        },
    )
    monkeypatch.setattr(
        pl,
        "download_from_storage",
        lambda _path: (_ for _ in ()).throw(AssertionError("no debe descargar")),
    )

    body = pl._restore_latest_sync("user-test-123")

    assert body["active_sheet"] == "Febrero"
    assert set(body["sheet_sessions"]) == {"Enero", "Febrero"}
    assert body["excluded_sheets"] == ["Notas"]
    assert body["combine_sheets"] is True


def test_restore_response_cache_isolated_and_invalidated_by_user(monkeypatch):
    from app.routes import pipeline as pl

    monkeypatch.setattr(
        pl,
        "get_settings",
        lambda: Settings(app_env="production", _env_file=None),
    )
    with pl._RESTORE_RESPONSE_CACHE_LOCK:
        pl._RESTORE_RESPONSE_CACHE.clear()

    key = "owner-1:00000000-0000-0000-0000-000000000001:limpio:10:t1"
    other_key = "owner-2:00000000-0000-0000-0000-000000000002:limpio:20:t2"
    response = {"dataset": {"id": "dataset-1"}, "source": "snapshot"}
    pl._restore_response_cache_store(key, response)
    pl._restore_response_cache_store(other_key, response)

    restored = pl._restore_response_cache_get(key)
    assert restored == response
    assert restored is not response

    pl._restore_response_cache_invalidate("owner-1")
    assert pl._restore_response_cache_get(key) is None
    assert pl._restore_response_cache_get(other_key) == response


def _authoritative_bundle(snapshot: dict, state: dict) -> dict:
    return {
        "state": state,
        "sheets": [
            {
                "sheet_key": "__single__",
                "revision": snapshot["revision"],
                "source_sha256": snapshot["source_sha256"],
                "rules_hash": snapshot["rules_hash"],
                "mapping_hash": snapshot["mapping_hash"],
                "sheet": snapshot["sheet"],
                "engine_version": snapshot["engine_version"],
                "snapshot": snapshot,
            }
        ],
    }


def _configure_production_restore(monkeypatch, pl, revision: dict, bundle_delay: float = 0):
    user_id = "owner-cache-test"
    dataset_id = "00000000-0000-0000-0000-000000000010"
    bundle_calls: list[int] = []

    monkeypatch.setattr(
        pl,
        "get_settings",
        lambda: Settings(app_env="production", _env_file=None),
    )
    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda _user_id: {
            "id": dataset_id,
            "name": "fixture.csv",
            "source": "excel_csv",
            "storage_path": f"{user_id}/fixture.csv",
            "status": "limpio",
        },
    )

    def metadata(_dataset_id, _user_id):
        current = revision["value"]
        return {
            "dataset_id": dataset_id,
            "user_id": user_id,
            "revision": current,
            "active_sheet": None,
            "available_sheets": [],
            "excluded_sheets": [],
            "combine_sheets": False,
            "source_sha256": SOURCE_SHA,
            "engine_version": _snapshot(current)["engine_version"],
            "updated_at": f"2026-07-17T00:00:{current:02d}+00:00",
        }

    def bundle(_dataset_id, _user_id, *, state=None):
        if bundle_delay:
            time.sleep(bundle_delay)
        current = revision["value"]
        bundle_calls.append(current)
        snapshot = _snapshot(current)
        snapshot["standardization"] = {
            **snapshot["standardization"],
            "revision_marker": current,
        }
        return _authoritative_bundle(snapshot, state or metadata(_dataset_id, _user_id))

    monkeypatch.setattr(pl, "fetch_restore_state_metadata", metadata)
    monkeypatch.setattr(pl, "fetch_restore_state_bundle", bundle)
    monkeypatch.setattr(
        pl,
        "download_from_storage",
        lambda _path: (_ for _ in ()).throw(AssertionError("no debe descargar")),
    )
    with pl._RESTORE_RESPONSE_CACHE_LOCK:
        pl._RESTORE_RESPONSE_CACHE.clear()
    return user_id, bundle_calls


def test_restore_cache_descarta_respuesta_si_cambia_revision(monkeypatch):
    from app.routes import pipeline as pl

    revision = {"value": 10}
    user_id, bundle_calls = _configure_production_restore(monkeypatch, pl, revision)

    first = pl._restore_latest_sync(user_id)
    repeated = pl._restore_latest_sync(user_id)
    revision["value"] = 11
    changed = pl._restore_latest_sync(user_id)

    assert first["standardization"]["revision_marker"] == 10
    assert repeated["standardization"]["revision_marker"] == 10
    assert changed["standardization"]["revision_marker"] == 11
    assert bundle_calls == [10, 11]


def test_restore_timing_initial_and_repeated_same_fixture(monkeypatch):
    from app.routes import pipeline as pl

    revision = {"value": 12}
    user_id, bundle_calls = _configure_production_restore(
        monkeypatch, pl, revision, bundle_delay=0.03
    )

    initial_samples: list[float] = []
    repeated_samples: list[float] = []
    for _ in range(5):
        pl._restore_response_cache_invalidate(user_id)
        started = time.perf_counter()
        pl._restore_latest_sync(user_id)
        initial_samples.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        pl._restore_latest_sync(user_id)
        repeated_samples.append((time.perf_counter() - started) * 1000)

    initial_ms = median(initial_samples)
    repeated_ms = median(repeated_samples)

    print(
        f"restore_fixture initial_ms={initial_ms:.3f} repeated_ms={repeated_ms:.3f}"
    )
    assert bundle_calls == [12] * 5
    assert repeated_ms < initial_ms
