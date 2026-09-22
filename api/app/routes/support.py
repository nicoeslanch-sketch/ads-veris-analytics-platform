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
from ..commercial_rpc import commercial_rpc
from ..request_budget import consume_budget

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


class SupportMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=80)
    page: str = Field(default="", max_length=120)


def _insert_sync(user_id: str, body: SupportRequestBody, settings: Settings) -> None:
    consume_budget(f'support:request:{user_id}', settings, limit=5, window=600)
    result = commercial_rpc('create_support_request_guarded', {
        'p_user_id': user_id, 'p_message': body.mensaje.strip(), 'p_page': body.pagina.strip(),
    }, settings)
    if isinstance(result, dict) and result.get('created') is True:
        return
    reason = result.get('reason') if isinstance(result, dict) else None
    if reason == 'duplicate':
        raise HTTPException(409, 'Ya registraste esa misma solicitud y sigue pendiente.')
    if reason == 'pending_limit':
        raise HTTPException(429, 'Ya tienes 3 solicitudes pendientes. El equipo las esta revisando.')
    raise HTTPException(503, 'No se pudo confirmar tu solicitud. Revisa su estado antes de reintentar.')


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


# ── Chat humano (migracion support_chat_coins_google_sheets) ────────────────


def _purge_stale_sync(settings: Settings) -> None:
    """Poda oportunista; pg_cron garantiza la misma regla sin trafico."""
    try:
        httpx.post(
            _rest(settings, "rpc/purge_stale_support_conversations"),
            json={},
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        ).raise_for_status()
    except httpx.HTTPError:
        pass


def _chat_payload_sync(user_id: str, settings: Settings) -> dict:
    _purge_stale_sync(settings)
    response = httpx.get(
        _rest(settings, "support_conversations"),
        params={
            "user_id": f"eq.{user_id}",
            "select": "id,status,source_page,created_at,last_message_at,closed_at",
            "order": "last_message_at.desc",
            "limit": "1",
        },
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    conversations = response.json()
    if not conversations:
        return {"available": True, "conversation": None, "expires_after_hours": 24}
    conversation = conversations[0]
    messages_response = httpx.get(
        _rest(settings, "support_messages"),
        params={
            "conversation_id": f"eq.{conversation['id']}",
            "select": "id,sender_role,body,created_at",
            "order": "created_at.asc",
            "limit": "500",
        },
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    messages_response.raise_for_status()
    conversation["messages"] = messages_response.json()
    return {"available": True, "conversation": conversation, "expires_after_hours": 24}


def _insert_conversation_sync(user_id: str, page: str, settings: Settings) -> str:
    response = httpx.post(
        _rest(settings, "support_conversations"),
        json={"user_id": user_id, "source_page": page or None},
        headers={**_headers(settings), "Prefer": "return=representation"},
        timeout=_TIMEOUT,
    )
    if response.status_code == 409:
        # Dos pestanas iniciaron a la vez: reutilizar la unica conversacion abierta.
        existing = httpx.get(
            _rest(settings, "support_conversations"),
            params={
                "user_id": f"eq.{user_id}",
                "status": "eq.open",
                "select": "id",
                "limit": "1",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        existing.raise_for_status()
        rows = existing.json()
        if rows:
            return str(rows[0]["id"])
    response.raise_for_status()
    return str(response.json()[0]["id"])


def _send_chat_message_sync(user_id: str, body: SupportMessageBody, settings: Settings) -> dict:
    consume_budget(f'support:chat:{user_id}', settings, limit=12, window=60)
    _purge_stale_sync(settings)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Escribe un mensaje para soporte.")
    conversation_id = body.conversation_id
    if conversation_id:
        response = httpx.get(
            _rest(settings, "support_conversations"),
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "select": "id,status",
                "limit": "1",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise HTTPException(status_code=404, detail="La conversación ya no existe.")
        if rows[0]["status"] != "open":
            raise HTTPException(
                status_code=409,
                detail="La conversación está cerrada. Inicia una conversación nueva.",
            )
    else:
        existing = httpx.get(
            _rest(settings, "support_conversations"),
            params={
                "user_id": f"eq.{user_id}",
                "status": "eq.open",
                "select": "id",
                "limit": "1",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        existing.raise_for_status()
        rows = existing.json()
        conversation_id = str(rows[0]["id"]) if rows else _insert_conversation_sync(
            user_id, body.page.strip(), settings
        )
    posted = httpx.post(
        _rest(settings, "support_messages"),
        json={
            "conversation_id": conversation_id,
            "sender_id": user_id,
            "sender_role": "customer",
            "body": message,
        },
        headers={**_headers(settings), "Prefer": "return=minimal"},
        timeout=_TIMEOUT,
    )
    posted.raise_for_status()
    return _chat_payload_sync(user_id, settings)


@router.get("/conversation")
async def current_support_conversation(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not _configured(settings):
        return {"available": False, "conversation": None, "expires_after_hours": 24}
    try:
        return await run_in_threadpool(_chat_payload_sync, user.id, settings)
    except httpx.HTTPError:
        return {"available": False, "conversation": None, "expires_after_hours": 24}


@router.post("/messages")
async def send_support_message(
    body: SupportMessageBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El chat de soporte no está configurado en este momento.",
        )
    try:
        return await run_in_threadpool(_send_chat_message_sync, user.id, body, settings)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El chat de soporte se está habilitando. Intenta nuevamente en unos minutos.",
        ) from exc
