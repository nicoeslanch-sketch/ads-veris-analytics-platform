"""MFA enforcement shared by the API and the first-factor setup endpoint."""

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


def require_account_mfa(user_id: str, claims: dict, settings: Settings) -> None:
    if not mfa_enforced(settings) or claims.get("aal") == "aal2":
        return
    # Never cache a negative: enrollment/revocation must take effect immediately.
    context = security_context(user_id, settings)
    if context["is_admin"] or context["has_mfa"]:
        raise HTTPException(403, "Verifica tu segundo factor para acceder a la plataforma.",
                            headers={"X-Auth-Action": "mfa_required"})
