"""Fast restoration: persistent snapshot first, full pipeline as fallback."""

import httpx

from app.config import Settings
from app.engine.clean import DEFAULT_RULES
from app.restore_cache import (
    RESTORE_SNAPSHOT_VERSION,
    build_restore_snapshot,
    store_restore_snapshot,
    valid_restore_snapshot,
)


SOURCE_SHA = "d" * 64


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
        lambda _dataset_id, _user_id, snapshot, restore_state=None: stored.append(snapshot) or True,
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
