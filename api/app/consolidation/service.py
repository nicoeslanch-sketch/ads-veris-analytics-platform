"""Puertas de acceso, ownership y utilidades de aplicación."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from fastapi import HTTPException, status

from ..auth import AuthenticatedUser
from ..capabilities import get_is_admin
from ..config import Settings


def require_consolidation_access(user: AuthenticatedUser, settings: Settings) -> None:
    if not settings.consolidation_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consolidación no está habilitada.")
    if not settings.consolidation_admin_only:
        return
    if settings.dev_auth_bypass and not settings.supabase_url:
        return
    if settings.admin_email and user.email and user.email.casefold() == settings.admin_email.casefold():
        return
    try:
        allowed = get_is_admin(user.id, settings)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "No se pudo verificar el acceso a consolidación.") from exc
    if not allowed:
        raise HTTPException(403, "Consolidación está disponible inicialmente solo para administradores.")


def owned_dataset_metadata(dataset_ids: list[str], user_id: str, settings: Settings) -> dict[str, dict[str, Any]]:
    if not dataset_ids:
        return {}
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "La asignación de fuentes requiere Supabase configurado.")
    headers = {"Authorization": f"Bearer {settings.supabase_service_role_key}", "apikey": settings.supabase_service_role_key}
    response = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/datasets",
        headers=headers,
        params={"id": f"in.({','.join(dataset_ids)})", "user_id": f"eq.{user_id}", "select": "id,name,storage_path"},
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    by_id = {str(row["id"]): row for row in rows}
    missing = sorted(set(dataset_ids) - set(by_id))
    if missing:
        raise HTTPException(403, "Una o más fuentes no pertenecen al usuario.")
    if any(not row.get("storage_path") for row in rows):
        raise HTTPException(422, "Una fuente no tiene archivo disponible en Storage.")
    return by_id


def idempotency_key(project_id: str, config_hash: str, sources: list[dict[str, Any]]) -> str:
    payload = {"project_id": project_id, "config_hash": config_hash, "datasets": sorted((source["role"], str(source["dataset_id"])) for source in sources)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
