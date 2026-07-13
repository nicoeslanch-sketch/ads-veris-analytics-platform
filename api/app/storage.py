"""Lectura de archivos desde Supabase Storage (SPEC §2 — flujo de archivos).

El navegador sube el archivo directo a Storage; la API lo descarga con la
service_role key para procesarlo. Nunca al revés: el archivo pesado no viaja
por el frontend hacia la API salvo el modo multipart para archivos pequeños.

La descarga aplica el MISMO límite de tamaño que el multipart (15 MB) para
proteger la memoria del servidor: se revisa Content-Length y, como respaldo,
se corta la descarga en streaming si el archivo lo supera.
"""

from urllib.parse import quote, unquote

import httpx
from fastapi import HTTPException, status

from .config import get_settings

MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024


def normalize_user_storage_path(storage_path: str, user_id: str) -> str:
    """Valida que una ruta pertenezca exactamente a la carpeta del usuario."""
    raw = str(storage_path or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="storage_path vacío.")
    normalized = raw.lstrip("/")
    decoded = normalized
    for _ in range(3):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    parts = decoded.split("/")
    invalid = (
        "\\" in normalized
        or decoded != normalized
        or "%" in decoded
        or len(parts) < 2
        or parts[0] != user_id
        or any(part in {"", ".", ".."} for part in parts)
    )
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a ese archivo.",
        )
    return "/".join(parts)


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail="El archivo supera los 15 MB. Divide la base en archivos más pequeños "
        "o quita columnas/hojas que no se usen.",
    )


def _storage_object_url(storage_path: str) -> str:
    settings = get_settings()
    encoded_path = "/".join(quote(part, safe="") for part in storage_path.split("/"))
    return (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_storage_bucket}/{encoded_path}"
    )


def download_from_storage(storage_path: str) -> bytes:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene configurado el acceso a Supabase Storage.",
        )
    url = _storage_object_url(storage_path)
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


def delete_from_storage(storage_path: str) -> None:
    """Elimina un objeto de forma idempotente; una ausencia ya cumple el objetivo."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene configurado el acceso a Supabase Storage.",
        )
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{settings.supabase_storage_bucket}"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    try:
        response = httpx.request(
            "DELETE",
            url,
            json={"prefixes": [storage_path]},
            headers=headers,
            timeout=60,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar a Supabase Storage: {exc.__class__.__name__}",
        )
    if response.status_code in {200, 204, 404}:
        return
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Supabase Storage respondió {response.status_code} al eliminar el archivo.",
    )
