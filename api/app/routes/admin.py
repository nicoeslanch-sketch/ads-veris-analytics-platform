"""Panel de administración (Fase 8) — solo cuentas con profiles.is_admin.

La cuenta administradora (servicios@adsveris.com, migración 0010) ve y
gestiona todas las cuentas de la plataforma:

GET  /admin/accounts                  — todas las cuentas con plan, uso y
                                        solicitudes pendientes (semáforo).
POST /admin/accounts/{id}/plan        — activa un plan a mano (Básico/Analista/
                                        Gold). La pasarela de pago del futuro
                                        llamará la MISMA función set_user_plan.
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

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import PLAN_ORDER, get_is_admin, normalize_plan
from ..config import Settings, get_settings

router = APIRouter(prefix="/admin")

_TIMEOUT = 15


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _require_admin_sync(user_id: str, settings: Settings) -> None:
    """503 sin Supabase, 403 si el caller no es administrador."""
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


def _audit(
    settings: Settings,
    admin_id: str,
    action: str,
    target_user_id: str | None = None,
    detail: dict | None = None,
) -> None:
    """Registro best-effort en admin_audit: un fallo aquí no anula la acción."""
    try:
        response = httpx.post(
            _rest(settings, "admin_audit"),
            json={
                "admin_id": admin_id,
                "target_user_id": target_user_id,
                "action": action,
                "detail": detail or {},
            },
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        )
        if response.status_code >= 400:
            print(f"[admin] admin_audit respondió {response.status_code} (¿migración 0010?).")
    except httpx.HTTPError as exc:
        print(f"[admin] No se pudo escribir en admin_audit ({exc.__class__.__name__}).")


# ── Listado de cuentas ────────────────────────────────────────────────────────


def _fetch_json(settings: Settings, url: str, params: dict) -> list | dict:
    response = httpx.get(url, params=params, headers=_headers(settings), timeout=_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _accounts_sync(caller_id: str, settings: Settings) -> dict:
    _require_admin_sync(caller_id, settings)
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

    by_id = {p["id"]: p for p in profiles}
    dataset_count: dict[str, int] = {}
    for row in datasets:
        dataset_count[row["user_id"]] = dataset_count.get(row["user_id"], 0) + 1
    support_count: dict[str, int] = {}
    for row in support:
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
    return await run_in_threadpool(_accounts_sync, user.id, settings)


# ── Activación manual de planes ──────────────────────────────────────────────


class SetPlanBody(BaseModel):
    plan: str = Field(min_length=3, max_length=20)


def set_user_plan(
    admin_id: str,
    target_user_id: str,
    plan: str,
    settings: Settings,
    source: str = "admin_manual",
) -> dict:
    """Activa un plan para una cuenta. ÚNICA vía para cambiar planes.

    TODO pasarela de pago (Fase 9): cuando exista el checkout, el webhook de
    pago confirmado debe llamar ESTA misma función con source="pasarela" —
    así el flujo manual y el automático comparten validación y auditoría.
    """
    normalized = normalize_plan(plan)
    if plan.strip().lower() not in PLAN_ORDER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan desconocido: '{plan}'. Usa uno de {', '.join(PLAN_ORDER)}.",
        )
    try:
        response = httpx.patch(
            _rest(settings, "profiles"),
            params={"id": f"eq.{target_user_id}"},
            json={"plan": normalized},
            headers={**_headers(settings), "Prefer": "return=representation"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar a Supabase: {exc.__class__.__name__}",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase respondió {response.status_code} al cambiar el plan.",
        )
    if not response.json():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un usuario con ese ID en profiles.",
        )
    _audit(settings, admin_id, "set_plan", target_user_id, {"plan": normalized, "source": source})
    return {"ok": True, "user_id": target_user_id, "plan": normalized}


def _set_plan_sync(caller_id: str, target: str, body: SetPlanBody, settings: Settings) -> dict:
    _require_admin_sync(caller_id, settings)
    return set_user_plan(caller_id, target, body.plan, settings)


@router.post("/accounts/{target_user_id}/plan")
async def admin_set_plan(
    target_user_id: str,
    body: SetPlanBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Activa un plan a mano para una cuenta (control manual hasta tener pasarela)."""
    return await run_in_threadpool(_set_plan_sync, user.id, target_user_id, body, settings)


# ── Bandeja de soporte ────────────────────────────────────────────────────────


def _support_inbox_sync(caller_id: str, settings: Settings) -> dict:
    _require_admin_sync(caller_id, settings)
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
                "select": "id,user_id,tipo,mensaje,status,created_at",
                "order": "created_at.desc",
                "limit": "200",
            },
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo leer la bandeja de soporte: {exc.__class__.__name__}",
        ) from exc

    solicitudes = [{"origen": "ayuda", **row} for row in ayuda] + [
        {"origen": "addon", **row} for row in addons
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
    return await run_in_threadpool(_support_inbox_sync, user.id, settings)


class AttendBody(BaseModel):
    respuesta: str = Field(default="", max_length=2000)


def _attend_sync(
    caller_id: str,
    request_id: str,
    table: str,
    body: AttendBody | None,
    settings: Settings,
) -> dict:
    _require_admin_sync(caller_id, settings)
    payload: dict = {"status": "atendida"}
    if table == "support_requests":
        payload["attended_at"] = datetime.now(timezone.utc).isoformat()
        if body and body.respuesta.strip():
            payload["respuesta"] = body.respuesta.strip()
    try:
        response = httpx.patch(
            _rest(settings, table),
            params={"id": f"eq.{request_id}"},
            json=payload,
            headers={**_headers(settings), "Prefer": "return=representation"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar a Supabase: {exc.__class__.__name__}",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase respondió {response.status_code} al atender la solicitud.",
        )
    rows = response.json()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una solicitud con ese ID.",
        )
    action = "support_attended" if table == "support_requests" else "addon_attended"
    _audit(settings, caller_id, action, rows[0].get("user_id"), {"request_id": request_id})
    return {"ok": True, "id": request_id, "status": "atendida"}


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
