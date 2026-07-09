"""Solicitudes de ayuda del usuario (Fase 8) — botón "¿Necesitas ayuda?".

POST /support/request — cualquier usuario autenticado escribe qué necesita;
queda en support_requests (migración 0010) y aparece en rojo en la bandeja
del administrador (página Administrar cuentas). Sin IA: una persona de
ADS Veris responde.

GET /support/mine — las solicitudes del propio usuario con su estado y la
respuesta del administrador (para mostrar "te respondimos" en el futuro).
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import AuthenticatedUser, get_current_user
from ..config import Settings, get_settings

router = APIRouter(prefix="/support")

_TIMEOUT = 10
MAX_MESSAGE_CHARS = 2000


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


class SupportRequestBody(BaseModel):
    mensaje: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    pagina: str = Field(default="", max_length=120)


def _insert_sync(user_id: str, body: SupportRequestBody, settings: Settings) -> None:
    try:
        response = httpx.post(
            _rest(settings, "support_requests"),
            json={
                "user_id": user_id,
                "mensaje": body.mensaje.strip(),
                "pagina": body.pagina.strip() or None,
            },
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo registrar tu solicitud: {exc.__class__.__name__}",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase respondió {response.status_code} al guardar la solicitud "
            "(¿está ejecutada la migración 0010?).",
        )


@router.post("/request")
async def create_support_request(
    body: SupportRequestBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Registra una solicitud de ayuda; el equipo ADS Veris la ve en su bandeja."""
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Las solicitudes de ayuda requieren Supabase configurado en el servidor.",
        )
    if not body.mensaje.strip():
        raise HTTPException(status_code=422, detail="Escribe en qué necesitas ayuda.")
    await run_in_threadpool(_insert_sync, user.id, body, settings)
    return {
        "registrado": True,
        "mensaje": "Recibimos tu solicitud. Te responderemos lo antes posible.",
    }


def _mine_sync(user_id: str, settings: Settings) -> list:
    response = httpx.get(
        _rest(settings, "support_requests"),
        params={
            "user_id": f"eq.{user_id}",
            "select": "id,mensaje,status,respuesta,created_at,attended_at",
            "order": "created_at.desc",
            "limit": "20",
        },
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


@router.get("/mine")
async def my_support_requests(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Solicitudes del propio usuario (estado + respuesta del administrador)."""
    if not _configured(settings):
        return {"disponible": False, "solicitudes": []}
    try:
        rows = await run_in_threadpool(_mine_sync, user.id, settings)
    except httpx.HTTPError:
        return {"disponible": False, "solicitudes": []}
    return {"disponible": True, "solicitudes": rows}
