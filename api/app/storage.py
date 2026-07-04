"""Lectura de archivos desde Supabase Storage (SPEC §2 — flujo de archivos).

El navegador sube el archivo directo a Storage; la API lo descarga con la
service_role key para procesarlo. Nunca al revés: el archivo pesado no viaja
por el frontend hacia la API salvo el modo multipart para archivos pequeños.

La descarga aplica el MISMO límite de tamaño que el multipart (15 MB) para
proteger la memoria del servidor: se revisa Content-Length y, como respaldo,
se corta la descarga en streaming si el archivo lo supera.
"""

import httpx
from fastapi import HTTPException, status

from .config import get_settings

MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail="El archivo supera los 15 MB. Divide la base en archivos más pequeños "
        "o quita columnas/hojas que no se usen.",
    )


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
        with httpx.stream("GET", url, headers=headers, timeout=60) as response:
            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"El archivo '{storage_path}' no existe en el bucket "
                    f"'{settings.supabase_storage_bucket}'.",
                )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Supabase Storage respondió {response.status_code} "
                    "al descargar el archivo.",
                )
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                raise _too_large()
            chunks: list[bytes] = []
            received = 0
            for chunk in response.iter_bytes():
                received += len(chunk)
                if received > MAX_DOWNLOAD_BYTES:
                    raise _too_large()
                chunks.append(chunk)
            return b"".join(chunks)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar a Supabase Storage: {exc.__class__.__name__}",
        )
