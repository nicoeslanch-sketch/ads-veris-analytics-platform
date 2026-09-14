"""Managed source uploads: authenticated ownership and durable quota admission."""

import re
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import Capability, require_capability_for_user
from ..config import Settings, get_settings
from ..storage import MAX_DOWNLOAD_BYTES, _storage_object_url
from ..storage_capacity import capacity_rpc, safe_storage_write

router = APIRouter(prefix="/storage")


def _upload_source(file: UploadFile, user_id: str, settings: Settings) -> dict:
    require_capability_for_user(user_id, Capability.STANDARDIZE, settings)
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "El almacenamiento no esta configurado.")
    size = file.size
    if not size or size > MAX_DOWNLOAD_BYTES:
        raise HTTPException(413, "El archivo debe contener datos y no superar 15 MB.")
    name = file.filename or "datos.xlsx"
    if not re.search(r"\.(xlsx|xls|csv|tsv|txt)$", name, re.I):
        raise HTTPException(422, "Formato no admitido para guardar el archivo.")
    safe_name = re.sub(r"[^\w.\-]+", "_", name, flags=re.ASCII)[-180:]
    path = f"{user_id}/{uuid4().hex}_{safe_name}"
    file.file.seek(0)
    try:
        response = safe_storage_write(path, size, "source", settings, lambda: httpx.post(
            _storage_object_url(path), content=iter(lambda: file.file.read(64 * 1024), b""),
            headers={"Authorization": f"Bearer {settings.supabase_service_role_key}",
                     "apikey": settings.supabase_service_role_key, "Content-Type": "application/octet-stream",
                     "Content-Length": str(size), "x-upsert": "false"}, timeout=120,
        ))
    except httpx.HTTPError as exc:
        raise HTTPException(503, "No se pudo confirmar la subida. Revisa el historial antes de reintentar.") from exc
    if response.status_code not in {200, 201}:
        raise HTTPException(502, "El almacenamiento no pudo guardar el archivo.")
    return {"storage_path": path, "bytes": size}


@router.post("/upload")
async def upload_source(file: UploadFile = File(...), user: AuthenticatedUser = Depends(get_current_user),
                        settings: Settings = Depends(get_settings)) -> dict:
    try:
        return await run_in_threadpool(_upload_source, file, user.id, settings)
    finally:
        await file.close()


@router.get("/quota")
async def storage_quota(user: AuthenticatedUser = Depends(get_current_user),
                        settings: Settings = Depends(get_settings)) -> dict:
    result = await run_in_threadpool(capacity_rpc, "storage_capacity", {"p_user_id": user.id}, settings)
    # Project-wide usage is operational information, not another customer's data.
    return {key: value for key, value in result.items() if not key.startswith("project_")}
