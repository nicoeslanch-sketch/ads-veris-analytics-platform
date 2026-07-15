"""Fast restoration: persistent snapshot first, full pipeline as fallback."""

import httpx

from app.config import Settings
from app.engine.clean import DEFAULT_RULES
from app.restore_cache import (
    MAX_RESTORE_SNAPSHOT_BYTES,
    RESTORE_SNAPSHOT_VERSION,
    build_restore_snapshot,
    store_restore_snapshot,
    valid_restore_snapshot,
)


def _snapshot() -> dict:
    return build_restore_snapshot(
        {"archivo": "ventas.csv", "filas": 2},
        {"archivo": "ventas.csv", "resumen": {"aplicado": True}},
        {
            "archivo": "ventas.csv",
            "periodo": {"desde": None, "hasta": None, "meses_disponibles": []},
        },
        {"monto": "Ventas"},
        False,
    )


def test_snapshot_versionado_exige_todas_las_etapas_para_dataset_limpio():
    snapshot = _snapshot()
    assert snapshot["version"] == RESTORE_SNAPSHOT_VERSION
    assert valid_restore_snapshot(snapshot, "limpio") is snapshot

    stale = {**snapshot, "version": RESTORE_SNAPSHOT_VERSION - 1}
    assert valid_restore_snapshot(stale, "limpio") is None
    assert valid_restore_snapshot({**snapshot, "metrics": None}, "limpio") is None


def test_restore_latest_requiere_autenticacion(client):
    response = client.post("/restore/latest", json={})
    assert response.status_code == 401


def test_store_snapshot_confirma_fila_y_filtra_por_propietario(monkeypatch):
    from app import restore_cache

    captured: dict = {}

    def fake_patch(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(200, json=[{"id": "00000000-0000-0000-0000-000000000001"}])

    monkeypatch.setattr(restore_cache.httpx, "patch", fake_patch)
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
    assert captured["params"]["user_id"] == "eq.owner-123"
    assert captured["params"]["select"] == "id"
    assert captured["json"]["restore_snapshot"]["version"] == RESTORE_SNAPSHOT_VERSION


def test_store_snapshot_demasiado_grande_no_toca_supabase(monkeypatch):
    from app import restore_cache

    def should_not_patch(*_args, **_kwargs):
        raise AssertionError("An oversized snapshot must not reach Supabase")

    monkeypatch.setattr(restore_cache.httpx, "patch", should_not_patch)
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )
    assert store_restore_snapshot(
        "00000000-0000-0000-0000-000000000001",
        "owner-123",
        {"payload": "x" * MAX_RESTORE_SNAPSHOT_BYTES},
        settings,
    ) is False


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

    def should_not_download(_path):
        raise AssertionError("A valid snapshot must not download the source file")

    monkeypatch.setattr(pl, "download_from_storage", should_not_download)
    response = client.post("/restore/latest", json={}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "snapshot"
    assert body["dataset"]["name"] == "ventas.csv"
    assert body["metrics"]["archivo"] == "ventas.csv"


def test_restore_latest_reconstruye_y_guarda_snapshot_si_falta(monkeypatch):
    from app.routes import pipeline as pl

    user_id = "user-test-123"
    dataset_id = "00000000-0000-0000-0000-000000000002"
    content = (
        "Fecha;Ventas;Producto\n"
        "01/05/2026;1000;Servicio A\n"
        "02/05/2026;2000;Servicio B\n"
    ).encode()
    stored: list[dict] = []

    monkeypatch.setattr(
        pl,
        "fetch_latest_restore_record",
        lambda _user_id: {
            "id": dataset_id,
            "name": "restaurar.csv",
            "source": "excel_csv",
            "storage_path": f"{user_id}/restaurar.csv",
            "status": "limpio",
            "restore_snapshot": None,
        },
    )
    monkeypatch.setattr(pl, "download_from_storage", lambda _path: content)
    monkeypatch.setattr(pl, "fetch_dataset_mapping", lambda _dataset_id: None)
    monkeypatch.setattr(
        pl,
        "fetch_latest_cleaning_config",
        lambda _dataset_id, _user_id: (dict(DEFAULT_RULES), False),
    )
    monkeypatch.setattr(
        pl,
        "store_restore_snapshot",
        lambda _dataset_id, _user_id, snapshot: stored.append(snapshot) or True,
    )

    body = pl._restore_latest_sync(user_id)

    assert body["source"] == "computed"
    assert body["standardization"]["filas"] == 2
    assert body["cleaning"]["resumen"]["aplicado"] is True
    assert body["metrics"]["kpis"]["ingresos_totales"]["valor"] == 3000.0
    assert stored and stored[0]["version"] == RESTORE_SNAPSHOT_VERSION
