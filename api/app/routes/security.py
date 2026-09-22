"""Minimal first-factor endpoint: no account data, secrets or cross-user IDs."""

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool

from ..auth import AuthenticatedUser, get_verified_user
from ..account_security import mfa_enforced, security_context
from ..config import Settings, get_settings

router = APIRouter(prefix="/security")


@router.get("/session")
async def session_security(
    response: Response,
    user: AuthenticatedUser = Depends(get_verified_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    enforced = mfa_enforced(settings)
    context = await run_in_threadpool(security_context, user.id, settings) if enforced else {
        "has_mfa": False, "is_admin": False,
    }
    verified = user.claims.get("aal") == "aal2"
    return {"enforced": enforced, "has_mfa": context["has_mfa"],
            "admin_required": enforced and context["is_admin"], "verified": verified,
            "needs_verification": enforced and not verified and (context["has_mfa"] or context["is_admin"])}
