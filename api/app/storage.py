"""Lectura de archivos desde Supabase Storage (SPEC §2 — flujo de archivos).

El navegador sube el archivo directo a Storage; la API lo descarga con la
service_role key para procesarlo. Nunca al revés: el archivo pesado no viaja
por el frontend hacia la API salvo el modo multipart para archivos pequeños.
"""

import httpx
from fastapi import HTTPException, status

from .config import get_settings


def download_from_storage(storage_path: str) -> bytes:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene configurado el acceso a Supabase Storage.",
        )
    path = storage_path.lstrip("/")
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_storage_bucket}/{path}"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    try:
        response = httpx.get(url, headers=headers, timeout=60)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar a Supabase Storage: {exc.__class__.__name__}",
        )
    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El archivo '{storage_path}' no existe en el bucket "
            f"'{settings.supabase_storage_bucket}'.",
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase Storage respondió {response.status_code} al descargar el archivo.",
        )
    return response.content
