"""Durable, idempotent account erasure across Storage, Auth and runtime caches."""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from fastapi import HTTPException

from .commercial_rpc import commercial_rpc
from .config import Settings

logger = logging.getLogger(__name__)
_TIMEOUT = 30
_DELETE_BATCH = 100
_MAX_OBJECTS = 20_000


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "Content-Type": "application/json",
    }


def _control(
    admin_id: str,
    request_id: str,
    action: str,
    settings: Settings,
    payload: dict | None = None,
) -> dict:
    result = commercial_rpc(
        "account_erasure_control",
        {
            "p_admin_id": admin_id,
            "p_request_id": request_id,
            "p_action": action,
            "p_payload": payload or {},
        },
        settings,
    )
    if not isinstance(result, dict):
        raise HTTPException(503, "Supabase no confirmó el estado de la eliminación.")
    return result


def _storage_entries(prefix: str, settings: Settings) -> list[dict]:
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/list/"
        f"{settings.supabase_storage_bucket}"
    )
    result: list[dict] = []
    offset = 0
    while True:
        response = httpx.post(
            url,
            headers=_headers(settings),
            json={
                "prefix": prefix,
                "limit": _DELETE_BATCH,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Invalid Storage listing")
        result.extend(entry for entry in page if isinstance(entry, dict))
        if len(page) < _DELETE_BATCH:
            return result
        offset += len(page)


def list_user_storage_objects(user_id: str, settings: Settings) -> list[str]:
    """List exactly one user's folder, including internal analysis artifacts."""
    pending = [user_id]
    objects: list[str] = []
    visited: set[str] = set()
    while pending:
        prefix = pending.pop()
        if prefix in visited:
            continue
        visited.add(prefix)
        for entry in _storage_entries(prefix, settings):
            name = str(entry.get("name") or "")
            if not name or "/" in name or name in {".", ".."}:
                raise ValueError("Unsafe Storage listing entry")
            full_path = f"{prefix}/{name}"
            if not full_path.startswith(f"{user_id}/"):
                raise ValueError("Storage prefix escaped account folder")
            if entry.get("id") is None:
                pending.append(full_path)
            else:
                objects.append(full_path)
            if len(objects) + len(pending) > _MAX_OBJECTS:
                raise ValueError("Account Storage object limit exceeded")
    return objects


def delete_user_storage_objects(user_id: str, settings: Settings) -> int:
    objects = list_user_storage_objects(user_id, settings)
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_storage_bucket}"
    )
    for start in range(0, len(objects), _DELETE_BATCH):
        batch = objects[start : start + _DELETE_BATCH]
        response = httpx.request(
            "DELETE",
            url,
            headers=_headers(settings),
            json={"prefixes": batch},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    # A second listing is the deletion acknowledgement; never delete Auth
    # while an object remains under the account prefix.
    remaining = list_user_storage_objects(user_id, settings)
    if remaining:
        raise RuntimeError("Storage deletion was not fully acknowledged")
    return len(objects)


def _auth_request(method: str, user_id: str, settings: Settings, **kwargs) -> httpx.Response:
    return httpx.request(
        method,
        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
        headers=_headers(settings),
        timeout=_TIMEOUT,
        **kwargs,
    )


def _ban_account(user_id: str, settings: Settings) -> None:
    response = _auth_request("PUT", user_id, settings, json={"ban_duration": "876000h"})
    if response.status_code == 404:
        return
    response.raise_for_status()


def _delete_auth_account(user_id: str, settings: Settings) -> None:
    response = _auth_request("DELETE", user_id, settings)
    if response.status_code == 404:
        return
    response.raise_for_status()


def _purge_runtime(user_id: str, settings: Settings) -> None:
    # Imports are intentionally local to avoid loading pandas on API startup.
    from .analysis_jobs import purge_user_jobs
    from .routes.pipeline import purge_user_runtime_caches
    from .shared_analysis import coordinator_for
    from .storage import invalidate_storage_user_cache

    purge_user_jobs(user_id)
    purge_user_runtime_caches(user_id)
    invalidate_storage_user_cache(user_id)
    coordinator_for(settings).purge_user(user_id)


def execute_account_erasure(
    admin_id: str,
    request_id: str,
    settings: Settings,
    *,
    storage_delete: Callable[[str, Settings], int] = delete_user_storage_objects,
) -> dict:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "La eliminación integral no está configurada.")
    job = _control(admin_id, request_id, "prepare", settings)
    if job.get("status") == "completed":
        return {"status": "completed", "idempotent": True, "receipt": job.get("id")}
    user_id = str(job.get("target_user_id") or "")
    if not user_id:
        raise HTTPException(503, "El trabajo no conserva un destinatario válido.")

    try:
        _ban_account(user_id, settings)
    except (httpx.HTTPError, ValueError) as exc:
        _control(admin_id, request_id, "fail", settings, {
            "stage": "deleting_account", "error": exc.__class__.__name__,
        })
        raise HTTPException(502, "No se pudo bloquear la cuenta antes de eliminarla.") from exc

    try:
        deleted = storage_delete(user_id, settings)
        job = _control(admin_id, request_id, "storage_deleted", settings, {"count": deleted})
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        _control(admin_id, request_id, "fail", settings, {
            "stage": "deleting_storage", "error": exc.__class__.__name__,
        })
        raise HTTPException(
            502,
            "La cuenta quedó bloqueada, pero Storage no confirmó el borrado completo. Puedes reintentar.",
        ) from exc

    try:
        _purge_runtime(user_id, settings)
        _delete_auth_account(user_id, settings)
        completed = _control(admin_id, request_id, "complete", settings)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        _control(admin_id, request_id, "fail", settings, {
            "stage": "deleting_account", "error": exc.__class__.__name__,
        })
        raise HTTPException(
            502,
            "Los archivos fueron eliminados, pero falta confirmar el cierre de Auth. Puedes reintentar.",
        ) from exc
    logger.info("account_erasure_completed receipt=%s objects=%d", completed.get("id"), deleted)
    return {
        "status": "completed",
        "idempotent": False,
        "receipt": completed.get("id"),
        "storage_objects_deleted": int(completed.get("storage_objects_deleted") or deleted),
    }
