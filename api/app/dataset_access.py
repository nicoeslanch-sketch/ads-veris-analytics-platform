"""Owner-scoped dataset access for privileged backend operations."""

from uuid import UUID

import httpx
from fastapi import HTTPException

from .config import Settings


def require_owned_dataset(dataset_id: str, user_id: str, settings: Settings) -> None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "No se pudo verificar el acceso al archivo.")
    try:
        canonical_id = str(UUID(dataset_id))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "El identificador del archivo no es valido.") from exc
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/datasets",
            params={"id": f"eq.{canonical_id}", "user_id": f"eq.{user_id}",
                    "select": "id", "limit": "1"},
            headers={"Authorization": f"Bearer {settings.supabase_service_role_key}",
                     "apikey": settings.supabase_service_role_key},
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "No se pudo verificar el acceso al archivo.") from exc
    # Missing and foreign IDs are deliberately indistinguishable.
    if not isinstance(rows, list) or not rows or rows[0].get("id") != canonical_id:
        raise HTTPException(404, "No existe ese archivo en tu cuenta.")
