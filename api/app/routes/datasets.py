"""Operaciones durables sobre datasets guardados en Supabase."""

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ..auth import AuthenticatedUser, get_current_user
from ..config import Settings, get_settings
from ..storage import delete_from_storage, normalize_user_storage_path

router = APIRouter(prefix="/datasets", tags=["datasets"])
_TIMEOUT = 30


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings, *, representation: bool = False) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    if representation:
        headers["Prefer"] = "return=representation"
    return headers


def _rest(settings: Settings, resource: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{resource}"


def _ensure_response(response: httpx.Response, operation: str) -> None:
    if response.status_code < 400:
        return
    if response.status_code == 404 and "dataset_deletion_jobs" in str(response.request.url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falta aplicar la migración 0013_dataset_deletion_saga.sql en Supabase.",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Supabase no pudo {operation} (estado {response.status_code}). Puedes reintentar.",
    )


def _get_one(table: str, filters: dict[str, str], settings: Settings) -> dict | None:
    response = httpx.get(
        _rest(settings, table),
        params={
            **{key: f"eq.{value}" for key, value in filters.items()},
            "select": "*",
            "limit": "1",
        },
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    _ensure_response(response, f"leer {table}")
    rows = response.json()
    return rows[0] if rows else None


def _create_job(dataset: dict, user_id: str, settings: Settings) -> dict:
    response = httpx.post(
        _rest(settings, "dataset_deletion_jobs"),
        json={
            "dataset_id": dataset["id"],
            "user_id": user_id,
            "dataset_name": dataset["name"],
            "storage_path": dataset.get("storage_path"),
            "status": "pending",
        },
        headers=_headers(settings, representation=True),
        timeout=_TIMEOUT,
    )
    if response.status_code == 409:
        concurrent = _get_one(
            "dataset_deletion_jobs",
            {"dataset_id": dataset["id"], "user_id": user_id},
            settings,
        )
        if concurrent:
            return concurrent
    _ensure_response(response, "crear el trabajo de eliminación")
    rows = response.json()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase no confirmó el trabajo de eliminación. Puedes reintentar.",
        )
    return rows[0]


def _update_job(job_id: str, user_id: str, payload: dict, settings: Settings) -> None:
    response = httpx.patch(
        _rest(settings, "dataset_deletion_jobs"),
        params={"id": f"eq.{job_id}", "user_id": f"eq.{user_id}"},
        json=payload,
        headers={**_headers(settings), "Prefer": "return=minimal"},
        timeout=_TIMEOUT,
    )
    _ensure_response(response, "actualizar el trabajo de eliminación")


def _mark_failed(
    job_id: str,
    user_id: str,
    stage: str,
    error: Exception,
    settings: Settings,
) -> None:
    detail = error.detail if isinstance(error, HTTPException) else error.__class__.__name__
    try:
        _update_job(
            job_id,
            user_id,
            {
                "status": "failed",
                "failed_stage": stage,
                "last_error": str(detail)[:500],
            },
            settings,
        )
    except Exception as update_error:
        print(
            "[eliminacion] No se pudo persistir el error de la saga: "
            f"{update_error.__class__.__name__}"
        )


def _finalize_job(job_id: str, user_id: str, settings: Settings) -> dict:
    response = httpx.post(
        _rest(settings, "rpc/finalize_dataset_deletion"),
        json={"p_job_id": job_id, "p_user_id": user_id},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    _ensure_response(response, "finalizar la eliminación en la base de datos")
    return response.json()


def _delete_dataset_saga(dataset_id: str, user_id: str, settings: Settings) -> dict:
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene configurado el acceso a Supabase.",
        )

    job = _get_one(
        "dataset_deletion_jobs",
        {"dataset_id": dataset_id, "user_id": user_id},
        settings,
    )
    dataset = _get_one("datasets", {"id": dataset_id, "user_id": user_id}, settings)
    if job is None:
        if dataset is None:
            raise HTTPException(status_code=404, detail="El dataset no existe.")
        # Este registro durable se crea antes de tocar Storage o PostgreSQL.
        job = _create_job(dataset, user_id, settings)

    if job["status"] == "completed":
        return {"dataset_id": dataset_id, "status": "completed", "idempotente": True}

    stage = job.get("failed_stage") if job["status"] == "failed" else job["status"]
    stage = stage or "pending"
    attempts = int(job.get("attempt_count") or 0) + 1

    if stage in {"pending", "deleting_storage"}:
        try:
            _update_job(
                job["id"],
                user_id,
                {
                    "status": "deleting_storage",
                    "failed_stage": None,
                    "last_error": None,
                    "attempt_count": attempts,
                },
                settings,
            )
            storage_path = job.get("storage_path")
            if storage_path:
                safe_path = normalize_user_storage_path(storage_path, user_id)
                delete_from_storage(safe_path)
            _update_job(
                job["id"],
                user_id,
                {
                    "status": "deleting_database",
                    "failed_stage": None,
                    "last_error": None,
                },
                settings,
            )
            stage = "deleting_database"
        except Exception as exc:
            _mark_failed(job["id"], user_id, "deleting_storage", exc, settings)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo eliminar el archivo de Storage. El trabajo quedó guardado para reintentar.",
            )

    if stage == "deleting_database":
        try:
            if job["status"] in {"deleting_database", "failed"}:
                _update_job(
                    job["id"],
                    user_id,
                    {
                        "status": "deleting_database",
                        "failed_stage": None,
                        "last_error": None,
                        "attempt_count": attempts,
                    },
                    settings,
                )
            _finalize_job(job["id"], user_id, settings)
        except Exception as exc:
            _mark_failed(job["id"], user_id, "deleting_database", exc, settings)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage ya fue procesado, pero falta cerrar la eliminación en la base. Puedes reintentar.",
            )

    return {"dataset_id": dataset_id, "status": "completed", "idempotente": False}


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Elimina Storage + base mediante una saga durable e idempotente."""
    try:
        return await run_in_threadpool(
            _delete_dataset_saga,
            str(dataset_id),
            user.id,
            settings,
        )
    except httpx.HTTPError as exc:
        print(f"[eliminacion] Falló la conexión con Supabase: {exc.__class__.__name__}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo contactar a Supabase. Ninguna fase confirmada se perderá; puedes reintentar.",
        )
