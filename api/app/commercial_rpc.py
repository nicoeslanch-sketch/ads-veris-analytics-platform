"""Fail-closed backend boundary for atomic money/entitlement operations."""

import logging

import httpx
from fastapi import HTTPException

from .config import Settings

logger = logging.getLogger(__name__)


def commercial_rpc(name: str, payload: dict, settings: Settings):
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "No se pudo verificar la operacion. Intenta mas tarde.")
    try:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/rpc/{name}",
            json=payload,
            headers={"Authorization": f"Bearer {settings.supabase_service_role_key}",
                     "apikey": settings.supabase_service_role_key},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            code = exc.response.json().get("code")
        except (ValueError, AttributeError):
            code = None
        if code == "42501":
            raise HTTPException(403, "No tienes permiso para esta operacion.") from exc
        if code == "P0002":
            raise HTTPException(404, "No se encontro el registro solicitado.") from exc
        if code in {"22023", "23505"}:
            raise HTTPException(409, "La operacion ya existe o sus datos no son validos.") from exc
        logger.warning("Commercial RPC %s failed (%s)", name, exc.response.status_code)
        raise HTTPException(503, "No se pudo confirmar la operacion. Revisa el estado antes de reintentar.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Commercial RPC %s unavailable (%s)", name, type(exc).__name__)
        raise HTTPException(503, "No se pudo confirmar la operacion. Revisa el estado antes de reintentar.") from exc
