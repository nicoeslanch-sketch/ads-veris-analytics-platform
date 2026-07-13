"""Fase 12, Bloque 6A: saga durable de eliminación de datasets."""

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.routes import datasets as route


USER_ID = "11111111-1111-1111-1111-111111111111"
DATASET_ID = "22222222-2222-2222-2222-222222222222"
JOB_ID = "33333333-3333-3333-3333-333333333333"


def _settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-test",
    )


def _dataset() -> dict:
    return {
        "id": DATASET_ID,
        "user_id": USER_ID,
        "name": "ventas.xlsx",
        "storage_path": f"{USER_ID}/ventas.xlsx",
    }


def _job(status: str = "pending", failed_stage: str | None = None) -> dict:
    return {
        "id": JOB_ID,
        "dataset_id": DATASET_ID,
        "user_id": USER_ID,
        "dataset_name": "ventas.xlsx",
        "storage_path": f"{USER_ID}/ventas.xlsx",
        "status": status,
        "failed_stage": failed_stage,
        "attempt_count": 0,
    }


def test_saga_persiste_antes_de_borrar_y_finaliza_en_orden(monkeypatch):
    events: list[str] = []

    def get_one(table, filters, settings):
        return None if table == "dataset_deletion_jobs" else _dataset()

    monkeypatch.setattr(route, "_get_one", get_one)
    monkeypatch.setattr(
        route,
        "_create_job",
        lambda dataset, user_id, settings: events.append("create_job") or _job(),
    )
    monkeypatch.setattr(
        route,
        "_update_job",
        lambda job_id, user_id, payload, settings: events.append(payload["status"]),
    )
    monkeypatch.setattr(
        route,
        "delete_from_storage",
        lambda storage_path: events.append(f"storage:{storage_path}"),
    )
    monkeypatch.setattr(
        route,
        "_finalize_job",
        lambda job_id, user_id, settings: events.append("finalize_database") or {"status": "completed"},
    )

    result = route._delete_dataset_saga(DATASET_ID, USER_ID, _settings())

    assert result == {"dataset_id": DATASET_ID, "status": "completed", "idempotente": False}
    assert events == [
        "create_job",
        "deleting_storage",
        f"storage:{USER_ID}/ventas.xlsx",
        "deleting_database",
        "finalize_database",
    ]


def test_reintento_desde_base_no_vuelve_a_tocar_storage(monkeypatch):
    events: list[str] = []

    monkeypatch.setattr(
        route,
        "_get_one",
        lambda table, filters, settings: (
            _job("failed", "deleting_database") if table == "dataset_deletion_jobs" else _dataset()
        ),
    )
    monkeypatch.setattr(
        route,
        "_update_job",
        lambda job_id, user_id, payload, settings: events.append(payload["status"]),
    )
    monkeypatch.setattr(route, "delete_from_storage", lambda path: events.append("storage"))
    monkeypatch.setattr(
        route,
        "_finalize_job",
        lambda job_id, user_id, settings: events.append("finalize") or {"status": "completed"},
    )

    result = route._delete_dataset_saga(DATASET_ID, USER_ID, _settings())

    assert result["status"] == "completed"
    assert events == ["deleting_database", "finalize"]


def test_fallo_storage_queda_persistido_para_reintento(monkeypatch):
    updates: list[dict] = []
    monkeypatch.setattr(
        route,
        "_get_one",
        lambda table, filters, settings: _job() if table == "dataset_deletion_jobs" else _dataset(),
    )
    monkeypatch.setattr(
        route,
        "_update_job",
        lambda job_id, user_id, payload, settings: updates.append(payload),
    )

    def fail_storage(path):
        raise HTTPException(status_code=502, detail="Storage temporalmente no disponible")

    monkeypatch.setattr(route, "delete_from_storage", fail_storage)

    with pytest.raises(HTTPException) as caught:
        route._delete_dataset_saga(DATASET_ID, USER_ID, _settings())

    assert caught.value.status_code == 502
    assert updates[-1]["status"] == "failed"
    assert updates[-1]["failed_stage"] == "deleting_storage"


def test_repeticion_completada_es_idempotente(monkeypatch):
    monkeypatch.setattr(
        route,
        "_get_one",
        lambda table, filters, settings: (
            _job("completed") if table == "dataset_deletion_jobs" else None
        ),
    )
    monkeypatch.setattr(
        route,
        "delete_from_storage",
        lambda path: pytest.fail("No debe tocar Storage si el trabajo ya terminó"),
    )

    result = route._delete_dataset_saga(DATASET_ID, USER_ID, _settings())

    assert result["status"] == "completed"
    assert result["idempotente"] is True


def test_404_solo_sin_dataset_ni_trabajo(monkeypatch):
    monkeypatch.setattr(route, "_get_one", lambda table, filters, settings: None)

    with pytest.raises(HTTPException) as caught:
        route._delete_dataset_saga(DATASET_ID, USER_ID, _settings())

    assert caught.value.status_code == 404


def test_endpoint_eliminar_dataset_requiere_auth_y_responde(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        route,
        "_delete_dataset_saga",
        lambda dataset_id, user_id, settings: {
            "dataset_id": dataset_id,
            "status": "completed",
            "idempotente": False,
        },
    )

    unauthenticated = client.delete(f"/datasets/{DATASET_ID}")
    authenticated = client.delete(f"/datasets/{DATASET_ID}", headers=auth_headers)

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json()["status"] == "completed"
