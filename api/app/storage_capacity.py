"""Durable byte reservations for trusted writers, shared across instances."""

import logging

import httpx
from fastapi import HTTPException

from .config import Settings

logger = logging.getLogger(__name__)


def capacity_rpc(name: str, payload: dict, settings: Settings):
    try:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/rpc/{name}", json=payload,
            headers={"Authorization": f"Bearer {settings.supabase_service_role_key}",
                     "apikey": settings.supabase_service_role_key}, timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "No se pudo verificar la cuota de almacenamiento. No se guardo el archivo; vuelve a intentar.") from exc


def reserve_capacity(path: str, size: int, kind: str, settings: Settings) -> None:
    result = capacity_rpc("reserve_storage_capacity", {
        "p_user_id": path.split('/')[0], "p_path": path, "p_bytes": size, "p_kind": kind,
    }, settings)
    if not isinstance(result, dict) or result.get("ok") is not True:
        detail = result.get("detail") if isinstance(result, dict) else None
        raise HTTPException(507, detail or "No hay espacio disponible para guardar el archivo.")


def settle_capacity(path: str, written: bool, settings: Settings) -> None:
    try:
        capacity_rpc("settle_storage_capacity", {"p_path": path, "p_written": written}, settings)
    except HTTPException:
        # Keep the reservation on ambiguous outcomes. Do not undo a successful upload.
        logger.warning("storage_reservation_settlement_pending")


def safe_storage_write(path: str, size: int, kind: str, settings: Settings, write):
    reserve_capacity(path, size, kind, settings)
    try:
        response = write()
    except httpx.HTTPError:
        # A timeout can happen after Storage accepted bytes. Hold the reservation.
        raise
    if response.status_code in {200, 201}:
        settle_capacity(path, True, settings)
    elif 400 <= response.status_code < 500:
        settle_capacity(path, False, settings)
    return response
