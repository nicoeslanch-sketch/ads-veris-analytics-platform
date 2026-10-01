"""Live-session and MFA enforcement; no cached authorization decisions."""

from uuid import UUID

from fastapi import HTTPException

from .commercial_rpc import commercial_rpc
from .config import Settings


def mfa_enforced(settings: Settings) -> bool:
    return settings.app_env.strip().lower() == "production" or settings.mfa_enforcement


def security_context(user_id: str, settings: Settings) -> dict:
    result = commercial_rpc("session_security_context", {"p_user_id": user_id}, settings)
    if not isinstance(result, dict) or any(type(result.get(k)) is not bool for k in ("is_admin", "has_mfa")):
        raise HTTPException(503, "No se pudo verificar la seguridad de tu cuenta.")
    return result


def require_live_session(user_id: str, claims: dict, settings: Settings) -> dict | None:
    if not mfa_enforced(settings):
        return None
    try:
        session_id = str(UUID(claims.get("session_id", "")))
        owner_id = str(UUID(user_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(401, "La sesion ya no esta activa. Inicia sesion nuevamente.")
    context = commercial_rpc("verified_session_context", {
        "p_user_id": owner_id, "p_session_id": session_id,
    }, settings)
    if not isinstance(context, dict) or any(type(context.get(k)) is not bool
            for k in ("session_active", "is_admin", "has_mfa")):
        raise HTTPException(503, "No se pudo verificar la seguridad de tu cuenta.")
    if not context["session_active"]:
        raise HTTPException(401, "La sesion ya no esta activa. Inicia sesion nuevamente.")
    return context


def require_account_mfa(user_id: str, claims: dict, settings: Settings,
                        context: dict | None = None) -> None:
    if not mfa_enforced(settings):
        return
    # get_verified_user supplies this request's live result, never a JWT claim.
    context = context if context is not None else require_live_session(user_id, claims, settings)
    if claims.get("aal") != "aal2" and (context["is_admin"] or context["has_mfa"]):
        raise HTTPException(403, "Verifica tu segundo factor para acceder a la plataforma.",
                            headers={"X-Auth-Action": "mfa_required"})
