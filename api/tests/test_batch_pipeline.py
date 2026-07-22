"""Multi-sheet batch endpoints open and process the workbook as one action."""

import io
import json
import threading
import time

from openpyxl import Workbook

from app.routes.pipeline import _store_restore_snapshots_parallel


def _book() -> bytes:
    workbook = Workbook()
    january = workbook.active
    january.title = "Enero"
    january.append(["Fecha", "Ventas", "Producto"])
    january.append(["01/01/2026", "$ 1.000", "Servicio A"])
    january.append(["02/01/2026", "$ 2.000", "Servicio B"])
    february = workbook.create_sheet("Febrero")
    february.append(["Fecha", "Ventas", "Producto"])
    february.append(["01/02/2026", "$ 3.000", "Servicio A"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _restore_state() -> dict:
    return {
        "active_sheet": "Enero",
        "available_sheets": ["Enero", "Febrero"],
        "excluded_sheets": [],
        "selected_sheets": ["Enero", "Febrero"],
        "sheet_errors": {},
        "analysis_scope": {
            "mode": "single",
            "sheets": ["Enero"],
            "active_sheet": "Enero",
        },
        "combine_sheets": False,
        "selection_mode": "all",
    }


def test_standardize_batch_returns_every_requested_sheet(client, auth_headers):
    response = client.post(
        "/standardize/batch",
        headers=auth_headers,
        data={
            "sheets": json.dumps(["Enero", "Febrero"]),
            "restore_state": json.dumps(_restore_state()),
        },
        files={
            "file": (
                "ventas.xlsx",
                _book(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert list(body["resultados"]) == ["Enero", "Febrero"]
    assert body["errores"] == {}
    assert body["resultados"]["Enero"]["filas"] == 2
    assert body["resultados"]["Febrero"]["filas"] == 1


def test_clean_batch_applies_every_sheet_without_individual_requests(client, auth_headers):
    manifest = {
        "hojas": [
            {
                "nombre": name,
                "procesar": True,
                "rules": {},
                "mapping": {},
                "scope": {},
                "eliminar_duplicados": False,
                "status": "estandarizada",
                "error": "",
                "revision": 0,
            }
            for name in ("Enero", "Febrero")
        ]
    }
    response = client.post(
        "/clean/batch",
        headers=auth_headers,
        data={
            "manifest": json.dumps(manifest),
            "restore_state": json.dumps(_restore_state()),
        },
        files={
            "file": (
                "ventas.xlsx",
                _book(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert list(body["resultados"]) == ["Enero", "Febrero"]
    assert body["errores"] == {}
    assert all(
        result["resumen"]["aplicado"] is True
        for result in body["resultados"].values()
    )
    assert body["resultados"]["Enero"]["carga"]["hoja_usada"] == "Enero"
    assert body["resultados"]["Febrero"]["carga"]["hoja_usada"] == "Febrero"


def test_clean_batch_reuses_frames_prepared_by_standardization(
    client, auth_headers, monkeypatch
):
    from app.routes import pipeline

    content = _book()
    with pipeline._FRAME_CACHE_LOCK:
        pipeline._FRAME_CACHE.clear()
    standardized = client.post(
        "/standardize/batch",
        headers=auth_headers,
        data={
            "sheets": json.dumps(["Enero", "Febrero"]),
            "restore_state": json.dumps(_restore_state()),
        },
        files={
            "file": (
                "ventas.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert standardized.status_code == 200

    def unexpected_workbook_reopen(*_args, **_kwargs):
        raise AssertionError("clean batch reopened an already cached workbook")

    monkeypatch.setattr(
        pipeline, "load_dataframes_with_reports", unexpected_workbook_reopen
    )
    manifest = {
        "hojas": [
            {
                "nombre": name,
                "procesar": True,
                "rules": {},
                "mapping": {},
                "scope": {},
                "eliminar_duplicados": False,
                "status": "estandarizada",
                "error": "",
                "revision": 0,
            }
            for name in ("Enero", "Febrero")
        ]
    }
    cleaned = client.post(
        "/clean/batch",
        headers=auth_headers,
        data={
            "manifest": json.dumps(manifest),
            "restore_state": json.dumps(_restore_state()),
        },
        files={
            "file": (
                "ventas.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert cleaned.status_code == 200
    assert set(cleaned.json()["resultados"]) == {"Enero", "Febrero"}


def test_multi_sheet_metrics_open_workbook_once(monkeypatch):
    from app.routes import pipeline

    content = _book()
    manifest = {
        "hojas": [
            {
                "nombre": name,
                "procesar": True,
                "rules": {},
                "mapping": {},
                "scope": {},
                "eliminar_duplicados": False,
                "revision": 41,
            }
            for name in ("Enero", "Febrero")
        ]
    }
    with pipeline._FRAME_CACHE_LOCK:
        pipeline._FRAME_CACHE.clear()
    with pipeline._CACHE_LOCK:
        pipeline._CLEAN_CACHE.clear()

    original_loader = pipeline.load_dataframes_with_reports
    calls = 0

    def counted_loader(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_loader(*args, **kwargs)

    monkeypatch.setattr(pipeline, "load_dataframes_with_reports", counted_loader)
    frames, _mappings, _results = pipeline._processed_manifest_frames(
        "ventas.xlsx",
        content,
        manifest,
        cache_dataset_id="00000000-0000-0000-0000-000000000099",
    )

    assert set(frames) == {"Enero", "Febrero"}
    assert calls == 1


def test_batch_snapshot_persistence_is_bounded_and_concurrent(monkeypatch):
    from app.routes import pipeline

    lock = threading.Lock()
    active = 0
    peak = 0

    def fake_store(*_args, **_kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        return True

    monkeypatch.setattr(pipeline, "store_restore_snapshot", fake_store)
    errors = _store_restore_snapshots_parallel(
        "00000000-0000-0000-0000-000000000001",
        "user-1",
        {
            name: {"sheet": name, "revision": 1}
            for name in ("Enero", "Febrero", "Marzo", "Abril", "Mayo")
        },
        {"selected_sheets": ["Enero", "Febrero", "Marzo", "Abril", "Mayo"]},
    )

    assert errors == {}
    assert 2 <= peak <= 4
