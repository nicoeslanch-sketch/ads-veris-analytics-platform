"""Cuotas de IA por plan (SPEC §9 — planes y feature gating).

Cada consulta a /ai/* descuenta del cupo mensual del usuario según su plan
(`profiles.plan`: basico|gold). El consumo vive en `ai_usage` (migración 0006)
y se consulta/escribe vía PostgREST con la service_role key (solo backend).

Comportamiento:
- Supabase sin configurar (desarrollo local) → sin gating, devuelve None.
- Cupo agotado → HTTP 429 con mensaje claro y el detalle del plan.
- Error de red contra Supabase → se permite la consulta (fail-open) y se
  registra el problema: la disponibilidad del asistente pesa más que una
  consulta sin contar. Todo el módulo es síncrono: llamarlo con
  `run_in_threadpool` desde los endpoints async.
"""

from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status

from .config import Settings

_TIMEOUT = 10


def _headers(settings: Settings) -> dict:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def get_plan(user_id: str, settings: Settings) -> str:
    """Plan del usuario desde profiles; 'basico' si no hay fila."""
    response = httpx.get(
        _rest(settings, "profiles"),
        params={"id": f"eq.{user_id}", "select": "plan"},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    rows = response.json()
    plan = rows[0].get("plan") if rows else None
    return plan if plan in ("basico", "gold") else "basico"


def count_month_usage(user_id: str, settings: Settings) -> int:
    """Consultas IA del usuario en el mes calendario en curso (UTC)."""
    response = httpx.get(
        _rest(settings, "ai_usage"),
        params={
            "user_id": f"eq.{user_id}",
            "created_at": f"gte.{_month_start_iso()}",
            "select": "id",
        },
        headers={**_headers(settings), "Prefer": "count=exact", "Range": "0-0"},
        timeout=_TIMEOUT,
    )
    if response.status_code not in (200, 206):
        response.raise_for_status()
    content_range = response.headers.get("content-range", "")
    total = content_range.split("/")[-1]
    return int(total) if total.isdigit() else 0


def limit_for(plan: str, settings: Settings) -> int:
    return (
        settings.ai_monthly_limit_gold
        if plan == "gold"
        else settings.ai_monthly_limit_basico
    )


def check_quota(user_id: str, settings: Settings) -> dict | None:
    """Valida el cupo ANTES de llamar a Anthropic.

    Devuelve {"plan", "usadas", "limite"} o None si no hay Supabase (dev).
    Lanza 429 si el cupo mensual está agotado.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    try:
        plan = get_plan(user_id, settings)
        usadas = count_month_usage(user_id, settings)
    except httpx.HTTPError as exc:
        # Fail-open: no castigar al usuario por un problema de red interno.
        print(f"[quota] No se pudo verificar el cupo de IA ({exc.__class__.__name__}); se permite la consulta.")
        return None
    limite = limit_for(plan, settings)
    if usadas >= limite:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Alcanzaste el límite mensual de consultas IA de tu plan "
                f"{plan} ({limite}). "
                + (
                    "Mejora a Gold para ampliar tu cupo."
                    if plan == "basico"
                    else "El cupo se renueva el próximo mes."
                )
            ),
        )
    return {"plan": plan, "usadas": usadas, "limite": limite}


def record_usage(user_id: str, kind: str, settings: Settings) -> None:
    """Registra una consulta consumida (tras una llamada exitosa). Best-effort."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    try:
        response = httpx.post(
            _rest(settings, "ai_usage"),
            json={"user_id": user_id, "kind": kind},
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        )
        if response.status_code >= 400:
            # Típico: migración 0006 sin ejecutar → PostgREST responde 404
            print(
                f"[quota] ai_usage respondió {response.status_code} al registrar consumo "
                "(¿está ejecutada la migración 0006?)."
            )
    except httpx.HTTPError as exc:
        print(f"[quota] No se pudo registrar el consumo de IA ({exc.__class__.__name__}).")


def usage_info(user_id: str, settings: Settings) -> dict:
    """Estado del cupo para la página Configuración."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {"disponible": False, "plan": "basico", "usadas": 0, "limite": 0}
    try:
        plan = get_plan(user_id, settings)
        usadas = count_month_usage(user_id, settings)
    except httpx.HTTPError:
        return {"disponible": False, "plan": "basico", "usadas": 0, "limite": 0}
    return {
        "disponible": True,
        "plan": plan,
        "usadas": usadas,
        "limite": limit_for(plan, settings),
        "periodo": datetime.now(timezone.utc).strftime("%Y-%m"),
    }
