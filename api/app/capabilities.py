"""Plan capabilities for commercial gating.

The database still stores the legacy value ``gold``. Product copy calls that
same tier "Analista"; keeping the mapping here avoids scattering ``plan ==
"gold"`` checks across the codebase.
"""

from enum import StrEnum

import httpx
from fastapi import HTTPException, status

from .config import Settings

_TIMEOUT = 10


class Capability(StrEnum):
    STANDARDIZE = "standardize"
    CLEAN = "clean"
    VIEW_DASHBOARD = "view_dashboard"
    ASK_DATA_AI = "ask_data_ai"
    DOWNLOAD_CLEAN_DATASET = "download_clean_dataset"
    ADVANCED_CLEANING_CHAT = "advanced_cleaning_chat"
    CUSTOM_CLEANING_VARIABLES = "custom_cleaning_variables"
    ADVANCED_REPORTS = "advanced_reports"


_BASICO_CAPABILITIES = {
    Capability.STANDARDIZE,
    Capability.CLEAN,
    Capability.VIEW_DASHBOARD,
    Capability.ASK_DATA_AI,
}

_ANALISTA_CAPABILITIES = {
    *_BASICO_CAPABILITIES,
    Capability.DOWNLOAD_CLEAN_DATASET,
    Capability.ADVANCED_CLEANING_CHAT,
    Capability.CUSTOM_CLEANING_VARIABLES,
    Capability.ADVANCED_REPORTS,
}


def normalize_plan(plan: str | None) -> str:
    value = (plan or "basico").strip().lower()
    if value in {"gold", "analista", "analyst"}:
        return "analista"
    return "basico"


def storage_plan_value(plan: str | None) -> str:
    """Plan value currently stored in public.profiles."""
    return "gold" if normalize_plan(plan) == "analista" else "basico"


def display_plan(plan: str | None) -> str:
    return "Analista" if normalize_plan(plan) == "analista" else "Basico"


def plan_allows(plan: str | None, capability: Capability | str) -> bool:
    cap = Capability(capability)
    allowed = (
        _ANALISTA_CAPABILITIES
        if normalize_plan(plan) == "analista"
        else _BASICO_CAPABILITIES
    )
    return cap in allowed


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def get_plan(user_id: str, settings: Settings) -> str:
    """Fetch the user's plan from profiles.

    Returns the storage value (``basico`` or ``gold``) for backward
    compatibility with existing API responses.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return "basico"
    response = httpx.get(
        _rest(settings, "profiles"),
        params={"id": f"eq.{user_id}", "select": "plan"},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    rows = response.json()
    plan = rows[0].get("plan") if rows else None
    return storage_plan_value(plan)


def require_capability_for_user(
    user_id: str,
    capability: Capability,
    settings: Settings,
) -> str:
    try:
        plan = get_plan(user_id, settings)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo verificar tu plan. Intenta nuevamente en unos minutos.",
        ) from exc
    if plan_allows(plan, capability):
        return plan
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Esta funcion requiere Plan {display_plan('analista')}.",
    )
