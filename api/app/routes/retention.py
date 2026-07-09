"""Retención de archivos en Supabase Storage (Fase 8).

Cada usuario puede conservar hasta N archivos según su plan (10 Básico /
25 Analista / 50 Gold). Al subir un archivo nuevo, el frontend dispara
POST /storage/retention (fire-and-forget) y el backend poda la carpeta
{user_id}/ del bucket:

1. Los `storage_keep_last` archivos más recientes JAMÁS se borran.
2. Se elimina el excedente sobre el tope del plan (los más antiguos primero).
3. Se elimina lo no usado hace más de `storage_retention_days` días
   ("uso" = subida, modificación o último acceso registrado por Storage).

Los datasets cuyo archivo se purga conservan su fila en el historial, pero
con storage_path en null (la UI muestra "archivo ya no disponible" en vez
de fallar con 404 al retomar). Así el Storage no crece sin control y la
plataforma se mantiene rápida y barata de operar.
"""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import get_profile_flags
from ..config import Settings, get_settings

router = APIRouter(prefix="/storage")

_TIMEOUT = 30


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def max_files_for(plan: str, is_admin: bool, settings: Settings) -> int:
    if is_admin:
        return settings.storage_max_files_gold
    return {
        "basico": settings.storage_max_files_basico,
        "analista": settings.storage_max_files_analista,
        "gold": settings.storage_max_files_gold,
    }.get(plan, settings.storage_max_files_basico)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _last_use(item: dict) -> datetime:
    """Último uso conocido del archivo: subida, modificación o acceso."""
    candidates = [
        _parse_ts(item.get("created_at")),
        _parse_ts(item.get("updated_at")),
        _parse_ts(item.get("last_accessed_at")),
    ]
    valid = [c for c in candidates if c is not None]
    return max(valid) if valid else datetime.now(timezone.utc)


def _list_user_files(user_id: str, settings: Settings) -> list[dict]:
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/list/"
        f"{settings.supabase_storage_bucket}"
    )
    response = httpx.post(
        url,
        json={
            "prefix": f"{user_id}/",
            "limit": 1000,
            "offset": 0,
            "sortBy": {"column": "created_at", "order": "desc"},
        },
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    items = response.json()
    # Storage devuelve también "carpetas" virtuales (id null): se ignoran.
    return [i for i in items if i.get("id")]


def _delete_files(user_id: str, names: list[str], settings: Settings) -> None:
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_storage_bucket}"
    )
    response = httpx.request(
        "DELETE",
        url,
        json={"prefixes": [f"{user_id}/{name}" for name in names]},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()


def _unlink_datasets(user_id: str, names: list[str], settings: Settings) -> None:
    """Deja storage_path en null en los datasets purgados (best-effort):
    el historial conserva la fila, pero la UI sabe que el archivo ya no está."""
    rest = f"{settings.supabase_url.rstrip('/')}/rest/v1/datasets"
    for name in names:
        try:
            httpx.patch(
                rest,
                params={
                    "user_id": f"eq.{user_id}",
                    "storage_path": f"eq.{user_id}/{name}",
                },
                json={"storage_path": None},
                headers={**_headers(settings), "Prefer": "return=minimal"},
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            print(f"[retencion] No se pudo desvincular el dataset ({exc.__class__.__name__}).")


def _retention_sync(user_id: str, settings: Settings) -> dict:
    plan, is_admin = get_profile_flags(user_id, settings)
    limit = max_files_for(plan, is_admin, settings)
    keep_last = settings.storage_keep_last
    max_age_days = settings.storage_retention_days

    files = _list_user_files(user_id, settings)
    files.sort(key=_last_use, reverse=True)  # más reciente primero

    now = datetime.now(timezone.utc)
    to_delete: list[str] = []
    for index, item in enumerate(files):
        if index < keep_last:
            continue  # los más recientes jamás se tocan
        over_limit = index >= limit
        expired = (now - _last_use(item)).days > max_age_days
        if over_limit or expired:
            to_delete.append(item["name"])

    if to_delete:
        _delete_files(user_id, to_delete, settings)
        _unlink_datasets(user_id, to_delete, settings)

    return {
        "eliminados": len(to_delete),
        "conservados": len(files) - len(to_delete),
        "limite": limit,
        "plan": plan,
    }


@router.post("/retention")
async def apply_retention(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Poda los archivos guardados del usuario según su plan (ver docstring)."""
    if not _configured(settings):
        return {"eliminados": 0, "conservados": 0, "limite": 0, "plan": "basico"}
    try:
        return await run_in_threadpool(_retention_sync, user.id, settings)
    except httpx.HTTPError as exc:
        # La retención jamás debe romper el flujo de carga del usuario.
        print(f"[retencion] Falló la poda de Storage ({exc.__class__.__name__}).")
        return {"eliminados": 0, "conservados": 0, "limite": 0, "plan": "basico", "error": True}
