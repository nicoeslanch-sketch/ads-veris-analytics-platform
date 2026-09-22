"""Panel de administración (Fase 8) — solo cuentas con profiles.is_admin.

La cuenta administradora (servicios@adsveris.com, migración 0010) ve y
gestiona todas las cuentas de la plataforma:

GET  /admin/accounts                  — todas las cuentas con plan, uso y
                                        solicitudes pendientes (semáforo).
POST /admin/accounts/{id}/plan        — activa un plan a mano (Básico/Analista/
                                        Gold), con auditoría transaccional.
GET  /admin/support                   — bandeja unificada: solicitudes de ayuda
                                        (support_requests) + tokens/upgrades
                                        (addon_requests).
POST /admin/support/{id}/attend       — marca una solicitud de ayuda atendida
                                        (con respuesta opcional para el usuario).
POST /admin/addon-requests/{id}/attend — marca una solicitud de tokens atendida.

Toda acción manual queda en admin_audit (quién, a quién, qué y cuándo).
Los datos sensibles jamás salen: solo campos visibles del perfil (nunca
contraseñas — Supabase Auth ni siquiera las expone).
"""

from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import PLAN_ORDER, get_is_admin, normalize_plan
from ..config import Settings, get_settings
from ..commercial_rpc import commercial_rpc
from ..commercial_readiness import commercial_readiness

router = APIRouter(prefix="/admin")

_TIMEOUT = 15


@router.get('/readiness')
async def readiness(user: AuthenticatedUser = Depends(get_current_user),
                    settings: Settings = Depends(get_settings)) -> dict:
    await run_in_threadpool(_require_admin_sync, user.id, settings)
    return await run_in_threadpool(commercial_readiness, user.id, settings)


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _require_admin_sync(user_id: str, settings: Settings, email: str | None = None) -> None:
    """503 sin Supabase, 403 sin rol protegido en la base de datos."""
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El panel de administración requiere Supabase configurado "
            "(y la migración 0010 ejecutada).",
        )
    try:
        is_admin = get_is_admin(user_id, settings)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo verificar el rol de administrador: {exc.__class__.__name__}",
        ) from exc
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta sección es solo para la cuenta administradora de ADS Veris.",
        )


# ── Listado de cuentas ────────────────────────────────────────────────────────


def _fetch_json(settings: Settings, url: str, params: dict) -> list | dict:
    response = httpx.get(url, params=params, headers=_headers(settings), timeout=_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _accounts_sync(caller_id: str, settings: Settings, caller_email: str | None = None) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    try:
        # Emails y último acceso viven en Supabase Auth (service_role).
        auth_payload = _fetch_json(
            settings,
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
            {"page": 1, "per_page": 200},
        )
        auth_users = auth_payload.get("users", []) if isinstance(auth_payload, dict) else auth_payload

        profiles = _fetch_json(
            settings,
            _rest(settings, "profiles"),
            {"select": "id,full_name,company,plan,is_admin,country,phone"},
        )
        datasets = _fetch_json(
            settings,
            _rest(settings, "datasets"),
            {"select": "user_id", "limit": "10000"},
        )
        support = _fetch_json(
            settings,
            _rest(settings, "support_requests"),
            {"select": "user_id,status", "status": "eq.pendiente", "limit": "1000"},
        )
        addons = _fetch_json(
            settings,
            _rest(settings, "addon_requests"),
            {"select": "user_id,status", "status": "eq.pendiente", "limit": "1000"},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo leer las cuentas desde Supabase: {exc.__class__.__name__}",
        ) from exc

    try:
        chat_conversations = _fetch_json(
            settings,
            _rest(settings, "support_conversations"),
            {"select": "user_id,status", "status": "eq.open", "limit": "1000"},
        )
    except httpx.HTTPError:
        chat_conversations = []

    by_id = {p["id"]: p for p in profiles}
    dataset_count: dict[str, int] = {}
    for row in datasets:
        dataset_count[row["user_id"]] = dataset_count.get(row["user_id"], 0) + 1
    support_count: dict[str, int] = {}
    for row in support:
        support_count[row["user_id"]] = support_count.get(row["user_id"], 0) + 1
    for row in chat_conversations:
        support_count[row["user_id"]] = support_count.get(row["user_id"], 0) + 1
    addon_count: dict[str, int] = {}
    for row in addons:
        addon_count[row["user_id"]] = addon_count.get(row["user_id"], 0) + 1

    cuentas = []
    for user in auth_users:
        uid = user.get("id", "")
        profile = by_id.get(uid, {})
        pendientes = support_count.get(uid, 0) + addon_count.get(uid, 0)
        cuentas.append(
            {
                "id": uid,
                "email": user.get("email"),
                "nombre": profile.get("full_name"),
                "empresa": profile.get("company"),
                "pais": profile.get("country"),
                "telefono": profile.get("phone"),
                "plan": normalize_plan(profile.get("plan")),
                "is_admin": bool(profile.get("is_admin")),
                "creado": user.get("created_at"),
                "ultimo_acceso": user.get("last_sign_in_at"),
                "datasets": dataset_count.get(uid, 0),
                "solicitudes_pendientes": pendientes,
            }
        )

    # Semáforo: primero quienes tienen solicitudes pendientes (rojo), luego el
    # resto por fecha de registro (sort estable: el segundo orden manda).
    cuentas.sort(key=lambda c: c["creado"] or "", reverse=True)
    cuentas.sort(key=lambda c: c["solicitudes_pendientes"], reverse=True)

    return {
        "cuentas": cuentas,
        "totales": {
            "cuentas": len(cuentas),
            "solicitudes_pendientes": sum(c["solicitudes_pendientes"] for c in cuentas),
        },
    }


@router.get("/accounts")
async def admin_accounts(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Todas las cuentas de la plataforma con plan, uso y semáforo de solicitudes."""
    return await run_in_threadpool(_accounts_sync, user.id, settings, user.email)


# ── Activación manual de planes ──────────────────────────────────────────────


class SetPlanBody(BaseModel):
    plan: str = Field(min_length=3, max_length=20)
    operation_id: UUID = Field(default_factory=uuid4)


def set_user_plan(
    admin_id: str,
    target_user_id: str,
    plan: str,
    settings: Settings,
    source: str = "admin_manual",
    operation_id: UUID | None = None,
) -> dict:
    """Manual admin activation only; payments need a verified payment receipt."""
    if source != "admin_manual":
        raise HTTPException(422, "Los pagos requieren una confirmacion de la pasarela.")
    normalized = normalize_plan(plan)
    if plan.strip().lower() not in PLAN_ORDER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan desconocido: '{plan}'. Usa uno de {', '.join(PLAN_ORDER)}.",
        )
    return commercial_rpc("admin_commercial_operation", {
        "p_admin_id": admin_id, "p_operation_id": str(operation_id or uuid4()),
        "p_target_user_id": target_user_id, "p_action": "set_plan",
        "p_payload": {"plan": normalized, "source": source},
    }, settings)


def _set_plan_sync(
    caller_id: str, target: str, body: SetPlanBody, settings: Settings, caller_email: str | None = None
) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    return set_user_plan(caller_id, target, body.plan, settings, operation_id=body.operation_id)


@router.post("/accounts/{target_user_id}/plan")
async def admin_set_plan(
    target_user_id: str,
    body: SetPlanBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Activa un plan a mano para una cuenta (control manual hasta tener pasarela)."""
    return await run_in_threadpool(
        _set_plan_sync, user.id, target_user_id, body, settings, user.email
    )


# ── Bandeja de soporte ────────────────────────────────────────────────────────


def _support_inbox_sync(caller_id: str, settings: Settings, caller_email: str | None = None) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    try:
        ayuda = _fetch_json(
            settings,
            _rest(settings, "support_requests"),
            {
                "select": "id,user_id,mensaje,pagina,status,respuesta,created_at",
                "order": "created_at.desc",
                "limit": "200",
            },
        )
        addons = _fetch_json(
            settings,
            _rest(settings, "addon_requests"),
            {
                "select": "id,user_id,tipo,mensaje,status,created_at,billing_identity_id",
                "order": "created_at.desc",
                "limit": "200",
            },
        )
        identity_ids = sorted(
            {
                str(row["billing_identity_id"])
                for row in addons
                if row.get("billing_identity_id")
            }
        )
        identities = (
            _fetch_json(
                settings,
                _rest(settings, "billing_identities"),
                {
                    "select": "id,rut_type,rut_masked",
                    "id": f"in.({','.join(identity_ids)})",
                    "limit": "200",
                },
            )
            if identity_ids
            else []
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo leer la bandeja de soporte: {exc.__class__.__name__}",
        ) from exc

    identities_by_id = {str(row["id"]): row for row in identities}
    solicitudes = [{"origen": "ayuda", **row} for row in ayuda] + [
        {
            "origen": "addon",
            **row,
            "billing_identity": identities_by_id.get(str(row.get("billing_identity_id"))),
        }
        for row in addons
    ]
    solicitudes.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    pendientes = sum(1 for s in solicitudes if s.get("status") == "pendiente")
    return {"solicitudes": solicitudes, "pendientes": pendientes}


@router.get("/support")
async def admin_support_inbox(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Bandeja unificada: solicitudes de ayuda + solicitudes de tokens/upgrade."""
    return await run_in_threadpool(_support_inbox_sync, user.id, settings, user.email)


# ── Conversaciones de soporte en tiempo casi real ───────────────────────────


class AdminChatMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    operation_id: UUID = Field(default_factory=uuid4)


def _admin_conversations_sync(
    caller_id: str,
    settings: Settings,
    caller_email: str | None = None,
) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    from .support import _purge_stale_sync

    _purge_stale_sync(settings)
    conversations = _fetch_json(
        settings,
        _rest(settings, "support_conversations"),
        {
            "select": "id,user_id,status,source_page,created_at,last_message_at,closed_at",
            "order": "last_message_at.desc",
            "limit": "200",
        },
    )
    ids = [str(row["id"]) for row in conversations]
    messages = (
        _fetch_json(
            settings,
            _rest(settings, "support_messages"),
            {
                "conversation_id": f"in.({','.join(ids)})",
                "select": "id,conversation_id,sender_role,body,created_at",
                "order": "created_at.asc",
                "limit": "5000",
            },
        )
        if ids
        else []
    )
    by_conversation: dict[str, list] = {}
    for message in messages:
        by_conversation.setdefault(str(message["conversation_id"]), []).append(message)
    for conversation in conversations:
        thread = by_conversation.get(str(conversation["id"]), [])
        conversation["message_count"] = len(thread)
        conversation["last_message"] = thread[-1] if thread else None
    return {
        "conversations": conversations,
        "open": sum(1 for row in conversations if row.get("status") == "open"),
    }


def _admin_conversation_detail_sync(
    caller_id: str,
    conversation_id: str,
    settings: Settings,
    caller_email: str | None = None,
) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    conversations = _fetch_json(
        settings,
        _rest(settings, "support_conversations"),
        {
            "id": f"eq.{conversation_id}",
            "select": "id,user_id,status,source_page,created_at,last_message_at,closed_at",
            "limit": "1",
        },
    )
    if not conversations:
        raise HTTPException(status_code=404, detail="La conversación ya no existe.")
    messages = _fetch_json(
        settings,
        _rest(settings, "support_messages"),
        {
            "conversation_id": f"eq.{conversation_id}",
            "select": "id,sender_role,body,created_at",
            "order": "created_at.asc",
            "limit": "500",
        },
    )
    return {"conversation": {**conversations[0], "messages": messages}}


def _admin_send_message_sync(
    caller_id: str,
    conversation_id: str,
    body: AdminChatMessageBody,
    settings: Settings,
    caller_email: str | None = None,
) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    commercial_rpc("admin_support_operation", {
        "p_admin_id": caller_id, "p_operation_id": str(body.operation_id),
        "p_resource_id": conversation_id, "p_action": "support_chat_reply",
        "p_message": body.message.strip(),
    }, settings)
    return _admin_conversation_detail_sync(
        caller_id, conversation_id, settings, caller_email
    )


def _admin_close_conversation_sync(
    caller_id: str,
    conversation_id: str,
    settings: Settings,
    caller_email: str | None = None,
) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    return commercial_rpc("admin_support_operation", {
        "p_admin_id": caller_id, "p_operation_id": str(uuid4()),
        "p_resource_id": conversation_id, "p_action": "support_chat_closed",
    }, settings)


@router.get("/support/conversations")
async def admin_support_conversations(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return await run_in_threadpool(
            _admin_conversations_sync, user.id, settings, user.email
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="El chat de soporte se está habilitando en la base de datos.",
        ) from exc


@router.get("/support/conversations/{conversation_id}")
async def admin_support_conversation_detail(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await run_in_threadpool(
        _admin_conversation_detail_sync,
        user.id,
        conversation_id,
        settings,
        user.email,
    )


@router.post("/support/conversations/{conversation_id}/messages")
async def admin_send_support_message(
    conversation_id: str,
    body: AdminChatMessageBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await run_in_threadpool(
        _admin_send_message_sync,
        user.id,
        conversation_id,
        body,
        settings,
        user.email,
    )


@router.post("/support/conversations/{conversation_id}/close")
async def admin_close_support_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await run_in_threadpool(
        _admin_close_conversation_sync,
        user.id,
        conversation_id,
        settings,
        user.email,
    )


class GrantAdsCoinsBody(BaseModel):
    user_id: str = Field(min_length=10, max_length=80)
    amount: int = Field(gt=0, le=1_000_000)
    note: str = Field(default="Otorgado por soporte", max_length=300)
    operation_id: UUID = Field(default_factory=uuid4)


def _grant_ads_coins_sync(
    caller_id: str,
    body: GrantAdsCoinsBody,
    settings: Settings,
    caller_email: str | None = None,
) -> dict:
    _require_admin_sync(caller_id, settings, caller_email)
    return commercial_rpc("admin_commercial_operation", {
        "p_admin_id": caller_id, "p_operation_id": str(body.operation_id),
        "p_target_user_id": body.user_id, "p_action": "grant_ads_coins",
        "p_payload": {"amount": body.amount, "note": body.note},
    }, settings)


@router.post("/grant-coins")
async def admin_grant_ads_coins(
    body: GrantAdsCoinsBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return await run_in_threadpool(
            _grant_ads_coins_sync, user.id, body, settings, user.email
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="La billetera ADS Coins todavía no está disponible en la base de datos.",
        ) from exc


class AttendBody(BaseModel):
    respuesta: str = Field(default="", max_length=2000)
    operation_id: UUID = Field(default_factory=uuid4)


def _attend_sync(
    caller_id: str,
    request_id: str,
    table: str,
    body: AttendBody | None,
    settings: Settings,
) -> dict:
    _require_admin_sync(caller_id, settings)
    if table not in {"support_requests", "addon_requests"}:
        raise ValueError("Unsupported request table")
    action = "support_attended" if table == "support_requests" else "addon_attended"
    return commercial_rpc("admin_support_operation", {
        "p_admin_id": caller_id, "p_operation_id": str(body.operation_id if body else uuid4()),
        "p_resource_id": request_id, "p_action": action,
        "p_message": body.respuesta.strip() if body else "",
    }, settings)


@router.post("/support/{request_id}/attend")
async def admin_attend_support(
    request_id: str,
    body: AttendBody | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Marca una solicitud de ayuda como atendida (con respuesta opcional)."""
    return await run_in_threadpool(
        _attend_sync, user.id, request_id, "support_requests", body, settings
    )


@router.post("/addon-requests/{request_id}/attend")
async def admin_attend_addon(
    request_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Marca una solicitud de tokens/upgrade como atendida."""
    return await run_in_threadpool(
        _attend_sync, user.id, request_id, "addon_requests", None, settings
    )
