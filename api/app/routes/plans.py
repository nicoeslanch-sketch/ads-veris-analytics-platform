"""Endpoints de planes, addons y administración (Fase 7 §3).

GET  /plans/usage         — cupo de insights + cupo de limpieza dirigida +
                            créditos addon (para Planes y Configuración).
POST /addons/request      — el usuario solicita tokens o un upgrade; queda en
                            `addon_requests` (migración 0009) y ADS Veris se
                            pone en contacto.
POST /admin/grant-credits — solo `profiles.is_admin`: otorga créditos de
                            limpieza dirigida a mano (ledger `plan_addons`).
                            Alternativa mínima documentada en el README:
                            insertar la fila por SQL en Supabase.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .. import quota
from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import get_is_admin, get_plan
from ..config import Settings, get_settings

router = APIRouter()

_TIMEOUT = 10

REQUEST_TYPES = {"tokens_limpieza", "upgrade_analista", "upgrade_gold", "otro"}


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _require_supabase(settings: Settings) -> None:
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Esta función requiere Supabase configurado en el servidor "
            "(y las migraciones 0008 y 0009 ejecutadas).",
        )


# ── Estado de cupos ───────────────────────────────────────────────────────────


def _usage_sync(user_id: str, settings: Settings) -> dict:
    insights = quota.usage_info(user_id, settings)
    limpieza = quota.cleaning_usage_info(user_id, settings)
    return {
        "disponible": bool(insights.get("disponible") or limpieza.get("disponible")),
        "plan": insights.get("plan", "basico"),
        "enforcement": settings.plan_enforcement,
        "insights": {
            "usadas": insights.get("usadas", 0),
            "limite": insights.get("limite", 0),
        },
        "limpieza": {
            "usadas_mes": limpieza.get("usadas_mes", 0),
            "base": limpieza.get("base", settings.ai_cleaning_monthly_limit),
            "addons": limpieza.get("addons", 0),
        },
    }


@router.get("/plans/usage")
async def plans_usage(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Cupos del mes (insights + limpieza dirigida + addons) para Planes/Configuración."""
    return await run_in_threadpool(_usage_sync, user.id, settings)


# ── Solicitudes de addons / upgrades ──────────────────────────────────────────


class AddonRequestBody(BaseModel):
    tipo: str = Field(default="tokens_limpieza", max_length=60)
    mensaje: str = Field(default="", max_length=1000)
    # Fase 14b: la contratación viaja vinculada a la identidad de facturación
    # (billing_identities, migración 0016) — jamás el RUT en texto libre.
    billing_identity_id: str | None = Field(default=None, max_length=64)


def _verify_identity_ownership(user_id: str, identity_id: str, settings: Settings) -> bool:
    """La solicitud solo puede vincular una identidad DEL PROPIO usuario."""
    try:
        response = httpx.get(
            _rest(settings, "billing_identities"),
            params={
                "id": f"eq.{identity_id}",
                "user_id": f"eq.{user_id}",
                "select": "id",
                "limit": "1",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        return False
    return response.status_code < 400 and bool(response.json())


def _insert_request_sync(user_id: str, body: AddonRequestBody, settings: Settings) -> None:
    tipo = body.tipo if body.tipo in REQUEST_TYPES else "otro"
    identity_id: str | None = None
    if body.billing_identity_id:
        if not _verify_identity_ownership(user_id, body.billing_identity_id, settings):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="La identidad de facturación no es válida para tu cuenta.",
            )
        identity_id = body.billing_identity_id
    # Fase 10 §12.2: sin duplicar una solicitud idéntica que sigue pendiente.
    try:
        pending = httpx.get(
            _rest(settings, "addon_requests"),
            params={
                "user_id": f"eq.{user_id}",
                "status": "eq.pendiente",
                "tipo": f"eq.{tipo}",
                "select": "id",
                "limit": "1",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        if pending.status_code < 400 and pending.json():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya tienes una solicitud pendiente de este tipo: te contactaremos pronto.",
            )
    except httpx.HTTPError:
        pass  # fail-open
    payload: dict = {"user_id": user_id, "tipo": tipo, "mensaje": body.mensaje.strip()}
    if identity_id:
        payload["billing_identity_id"] = identity_id
    try:
        response = httpx.post(
            _rest(settings, "addon_requests"),
            json=payload,
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo registrar la solicitud: {exc.__class__.__name__}",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase respondió {response.status_code} al guardar la solicitud "
            "(¿está ejecutada la migración 0009?).",
        )


@router.post("/addons/request")
async def addons_request(
    body: AddonRequestBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Registra una solicitud de tokens/upgrade. ADS Veris contacta al usuario."""
    _require_supabase(settings)
    await run_in_threadpool(_insert_request_sync, user.id, body, settings)
    return {
        "registrado": True,
        "mensaje": "Recibimos tu solicitud. Nos pondremos en contacto contigo para coordinar.",
    }


# ── Otorgamiento manual de créditos (admin) ──────────────────────────────────


class GrantCreditsBody(BaseModel):
    user_id: str = Field(min_length=8, max_length=64)
    credits: int = Field(gt=0, le=1000)
    note: str = Field(default="", max_length=300)


def _grant_sync(caller_id: str, body: GrantCreditsBody, settings: Settings) -> dict:
    try:
        if not get_is_admin(caller_id, settings):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo un administrador puede otorgar créditos.",
            )
        # El destinatario debe existir en profiles.
        check = httpx.get(
            _rest(settings, "profiles"),
            params={"id": f"eq.{body.user_id}", "select": "id"},
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
        check.raise_for_status()
        if not check.json():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No existe un usuario con ese ID en profiles.",
            )
        insert = httpx.post(
            _rest(settings, "plan_addons"),
            json={
                "user_id": body.user_id,
                "credits": body.credits,
                "granted_by": caller_id,
                "note": body.note.strip() or "Otorgado por administrador",
            },
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        )
        if insert.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Supabase respondió {insert.status_code} al otorgar créditos "
                "(¿está ejecutada la migración 0009?).",
            )
        # Fase 10 §11.2: TODO otorgamiento manual queda en la misma auditoría
        # que los cambios de plan (admin_audit, migración 0010).
        from .admin import _audit

        _audit(
            settings,
            caller_id,
            "grant_credits",
            body.user_id,
            {"credits": body.credits, "note": body.note.strip()},
        )
        saldo = quota.addons_balance(body.user_id, settings)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar a Supabase: {exc.__class__.__name__}",
        ) from exc
    return {"otorgado": True, "user_id": body.user_id, "credits": body.credits, "saldo": saldo}


@router.post("/admin/grant-credits")
async def admin_grant_credits(
    body: GrantCreditsBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Otorga créditos de limpieza dirigida (solo profiles.is_admin)."""
    _require_supabase(settings)
    return await run_in_threadpool(_grant_sync, user.id, body, settings)


# `get_plan` queda importado para uso futuro de la página Planes (checkout).
_ = get_plan
