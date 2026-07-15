"""Planes y capacidades comerciales — fuente única de verdad (Fase 7).

Tres planes: ``basico`` → ``analista`` → ``gold`` (en construcción).
La matriz PLAN_CAPABILITIES se replica en el frontend
(``frontend/src/lib/plans.ts``); si cambias algo aquí, cámbialo allá.

Interruptor global ``PLAN_ENFORCEMENT`` (Settings.plan_enforcement, default
False en Fase 7): con enforcement apagado TODO queda accesible para probar,
pero cada puerta ya tiene su cerradura instalada. Encenderlo en el futuro no
requiere tocar componentes: solo el flag (backend) y VITE_PLAN_ENFORCEMENT
(frontend).

Historia: hasta la migración 0008, la base guardaba ``gold`` para el plan que
la UI mostraba como "Analista". La 0008 migra esas filas a ``analista`` y
``gold`` pasa a ser el tercer plan (SQL + comunidad). Si el backend nuevo corre
contra una base sin migrar, los ``gold`` legacy reciben el set Gold — que es un
superconjunto de Analista, así que nadie pierde capacidades.
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
    # Fase 8: el reporte PDF del negocio es para TODOS los planes; lo que se
    # reserva para Analista es la descarga de la base LIMPIA (Excel/CSV).
    DOWNLOAD_REPORTS = "download_reports"
    # ── Analista ──
    DOWNLOAD_CLEAN_DATASET = "download_clean_dataset"
    AI_CLEANING = "ai_cleaning"  # chat de limpieza dirigida por variables (cupo mensual + addons)
    # ── Gold (en construcción) ──
    CONNECT_SQL = "connect_sql"
    COMMUNITY_ACCESS = "community_access"


_BASICO = {
    Capability.STANDARDIZE,
    Capability.CLEAN,
    Capability.VIEW_DASHBOARD,
    Capability.ASK_DATA_AI,
    Capability.DOWNLOAD_REPORTS,
}

_ANALISTA = {
    *_BASICO,
    Capability.DOWNLOAD_CLEAN_DATASET,
    Capability.AI_CLEANING,
}

_GOLD = {
    *_ANALISTA,
    Capability.CONNECT_SQL,
    Capability.COMMUNITY_ACCESS,
}

PLAN_CAPABILITIES: dict[str, set[Capability]] = {
    # Fase 13: las cuentas NUEVAS nacen sin plan (migración 0015) — pueden
    # navegar la plataforma pero no procesar archivos. Las cuentas existentes
    # conservan 'basico' y no notan el cambio.
    "sin_plan": set(),
    "basico": _BASICO,
    "analista": _ANALISTA,
    "gold": _GOLD,
}

PLAN_ORDER = ("basico", "analista", "gold")


def normalize_plan(plan: str | None) -> str:
    # Sin fila en profiles (cuentas antiguas / entorno local) → 'basico':
    # las cuentas existentes quedan protegidas por diseño.
    value = (plan or "basico").strip().lower()
    if value in {"sin_plan", "ninguno", "none", "free"}:
        return "sin_plan"
    if value in {"analista", "analyst"}:
        return "analista"
    if value == "gold":
        return "gold"
    return "basico"


def display_plan(plan: str | None) -> str:
    return {
        "sin_plan": "Sin plan",
        "basico": "Básico",
        "analista": "Analista",
        "gold": "Gold",
    }[normalize_plan(plan)]


def plan_allows(plan: str | None, capability: Capability | str) -> bool:
    cap = Capability(capability)
    return cap in PLAN_CAPABILITIES[normalize_plan(plan)]


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def get_plan(user_id: str, settings: Settings) -> str:
    """Plan normalizado del usuario desde profiles (basico|analista|gold)."""
    return get_profile_flags(user_id, settings)[0]


def get_profile_flags(user_id: str, settings: Settings) -> tuple[str, bool]:
    """(plan, is_admin) en UNA consulta a profiles. Sin Supabase → ('basico', False)."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return "basico", False
    response = httpx.get(
        _rest(settings, "profiles"),
        params={"id": f"eq.{user_id}", "select": "plan,is_admin"},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return "basico", False
    return normalize_plan(rows[0].get("plan")), bool(rows[0].get("is_admin"))


def get_is_admin(user_id: str, settings: Settings) -> bool:
    """profiles.is_admin (migración 0008). Sin Supabase → False."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return False
    response = httpx.get(
        _rest(settings, "profiles"),
        params={"id": f"eq.{user_id}", "select": "is_admin"},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    rows = response.json()
    return bool(rows and rows[0].get("is_admin"))


def min_plan_for(capability: Capability) -> str:
    for plan in PLAN_ORDER:
        if capability in PLAN_CAPABILITIES[plan]:
            return plan
    return "gold"


def require_capability_for_user(
    user_id: str,
    capability: Capability,
    settings: Settings,
) -> str:
    """Puerta de capacidad. Con PLAN_ENFORCEMENT apagado deja pasar todo sin
    consultar la red. El administrador (profiles.is_admin) pasa siempre.
    Sin Supabase configurado (desarrollo local) no hay dónde mirar el plan:
    fail-open, igual que las cuotas."""
    if not settings.plan_enforcement:
        return "sin_enforcement"
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return "sin_supabase"
    try:
        plan, is_admin = get_profile_flags(user_id, settings)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo verificar tu plan. Intenta nuevamente en unos minutos.",
        ) from exc
    if is_admin or plan_allows(plan, capability):
        return plan
    if plan == "sin_plan":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Necesitas un plan activo para usar esta función. "
            "Contrata un plan en la página Planes para comenzar.",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Esta función requiere el Plan {display_plan(min_plan_for(capability))}. "
        "Puedes contratarlo en la página Planes.",
    )
