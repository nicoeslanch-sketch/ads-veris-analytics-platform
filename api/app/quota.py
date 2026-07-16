"""Cuotas de IA por plan (SPEC §9 + Fase 7).

Dos cupos independientes, ambos registrados en ``ai_usage`` (migraciones 0006
y 0009) vía PostgREST con la service_role key (solo backend):

- **Insights** (`kind` in summary|chat|recommendation): cupo mensual por plan.
- **Limpieza dirigida** (`kind` = cleaning): base mensual (2, configurable con
  AI_CLEANING_MONTHLY_LIMIT) **+ créditos addon** de ``plan_addons`` — un
  ledger: filas positivas = tokens otorgados a mano, filas negativas =
  consumos. El saldo es la suma. Los intentos base se reinician cada mes; los
  addons son saldo aparte que no expira (decisión Fase 7 §7.2).

Comportamiento compartido:
- Supabase sin configurar (desarrollo local) → sin gating, devuelve None.
- Cupo agotado → HTTP 429 con mensaje claro y CTA.
- Error de red contra Supabase → fail-open documentado: se permite la consulta
  y se registra el problema (la disponibilidad pesa más que una consulta sin
  contar). Todo el módulo es síncrono: llamarlo con `run_in_threadpool`.

Deuda conocida (PHASE_STATUS → Pendiente): el control es check-then-record,
una ráfaga simultánea justo en el límite puede excederlo por pocas consultas.
"""

from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status

from .capabilities import display_plan, get_profile_flags, normalize_plan
from .config import Settings

_TIMEOUT = 10

INSIGHT_KINDS = ("summary", "chat", "recommendation")


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


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def count_month_usage(
    user_id: str,
    settings: Settings,
    kinds: tuple[str, ...] = INSIGHT_KINDS,
) -> int:
    """Consultas del usuario en el mes calendario en curso (UTC), por tipo."""
    params = {
        "user_id": f"eq.{user_id}",
        "created_at": f"gte.{_month_start_iso()}",
        "select": "id",
    }
    if kinds:
        params["kind"] = f"in.({','.join(kinds)})"
    response = httpx.get(
        _rest(settings, "ai_usage"),
        params=params,
        headers={**_headers(settings), "Prefer": "count=exact", "Range": "0-0"},
        timeout=_TIMEOUT,
    )
    if response.status_code not in (200, 206):
        response.raise_for_status()
    content_range = response.headers.get("content-range", "")
    total = content_range.split("/")[-1]
    return int(total) if total.isdigit() else 0


def limit_for(plan: str, settings: Settings) -> int:
    limits = {
        # Fase 14: sin plan (y prueba gratuita, que mantiene plan sin_plan) no
        # incluye IA — límite 0 explícito. Antes esto era un KeyError → 500 en
        # /ai/usage para cualquier cuenta nueva.
        "sin_plan": 0,
        "basico": settings.ai_monthly_limit_basico,
        "analista": settings.ai_monthly_limit_analista,
        "gold": settings.ai_monthly_limit_gold,
    }
    return limits[normalize_plan(plan)]


def check_quota(user_id: str, settings: Settings) -> dict | None:
    """Valida el cupo de INSIGHTS antes de llamar a Anthropic.

    Devuelve {"plan", "usadas", "limite"} o None si no hay Supabase (dev).
    Lanza 429 si el cupo mensual está agotado.
    """
    if not _configured(settings):
        return None
    try:
        plan, is_admin = get_profile_flags(user_id, settings)
        usadas = count_month_usage(user_id, settings, kinds=INSIGHT_KINDS)
    except httpx.HTTPError as exc:
        # Fail-open: no castigar al usuario por un problema de red interno.
        print(f"[quota] No se pudo verificar el cupo de IA ({exc.__class__.__name__}); se permite la consulta.")
        return None
    if is_admin:
        return {
            "plan": plan,
            "usadas": usadas,
            "limite": 0,
            "ilimitado": True,
        }
    limite = limit_for(plan, settings)
    if limite <= 0:
        # Fase 14: sin plan / prueba gratuita — la IA no está incluida. Es una
        # restricción de plan (403 con CTA), no un cupo agotado (429).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El asistente con IA está disponible desde el Plan Básico. "
            "Contrata un plan en la página Planes para activarlo.",
        )
    if usadas >= limite:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Alcanzaste el límite mensual de consultas IA de tu plan "
                f"{display_plan(plan)} ({limite}). "
                + (
                    "Mejora a Analista para ampliar tu cupo."
                    if normalize_plan(plan) == "basico"
                    else "El cupo se renueva el próximo mes."
                )
            ),
        )
    return {
        "plan": plan,
        "usadas": usadas,
        "limite": limite,
        "ilimitado": False,
    }


def record_usage(user_id: str, kind: str, settings: Settings) -> None:
    """Registra una consulta consumida (tras una llamada exitosa). Best-effort."""
    if not _configured(settings):
        return
    try:
        response = httpx.post(
            _rest(settings, "ai_usage"),
            json={"user_id": user_id, "kind": kind},
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        )
        if response.status_code >= 400:
            # Típico: migración 0006/0009 sin ejecutar → PostgREST responde 404/400
            print(
                f"[quota] ai_usage respondió {response.status_code} al registrar consumo "
                "(¿están ejecutadas las migraciones 0006 y 0009?)."
            )
    except httpx.HTTPError as exc:
        print(f"[quota] No se pudo registrar el consumo de IA ({exc.__class__.__name__}).")


def usage_info(user_id: str, settings: Settings) -> dict:
    """Estado del cupo de insights para la página Configuración."""
    if not _configured(settings):
        return {
            "disponible": False,
            "plan": "basico",
            "usadas": 0,
            "limite": 0,
            "ilimitado": False,
        }
    try:
        plan, is_admin = get_profile_flags(user_id, settings)
        usadas = count_month_usage(user_id, settings, kinds=INSIGHT_KINDS)
    except httpx.HTTPError:
        return {
            "disponible": False,
            "plan": "basico",
            "usadas": 0,
            "limite": 0,
            "ilimitado": False,
        }
    return {
        "disponible": True,
        "plan": plan,
        "usadas": usadas,
        "limite": 0 if is_admin else limit_for(plan, settings),
        "ilimitado": is_admin,
        "periodo": datetime.now(timezone.utc).strftime("%Y-%m"),
    }


# ── Fase 7: cuota de limpieza dirigida (base mensual + addons) ───────────────


def addons_balance(user_id: str, settings: Settings) -> int:
    """Saldo de créditos addon = suma del ledger plan_addons (migración 0009)."""
    response = httpx.get(
        _rest(settings, "plan_addons"),
        params={"user_id": f"eq.{user_id}", "select": "credits"},
        headers=_headers(settings),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return sum(int(row.get("credits") or 0) for row in response.json())


def cleaning_limit_for(plan: str, settings: Settings) -> int:
    """Intentos base de limpieza dirigida al mes según el plan (Fase 8)."""
    if normalize_plan(plan) == "gold":
        return settings.ai_cleaning_monthly_limit_gold
    return settings.ai_cleaning_monthly_limit


def check_cleaning_quota(user_id: str, settings: Settings) -> dict | None:
    """Valida el cupo de limpieza dirigida ANTES de correr el motor.

    Devuelve {"plan", "usadas_mes", "base", "addons", "consume_addon"} o None
    si no hay Supabase (dev). Lanza 429 con CTA a Planes si no quedan intentos
    base ni créditos addon. El administrador nunca agota cupo (Fase 8).
    """
    if not _configured(settings):
        return None
    try:
        plan, is_admin = get_profile_flags(user_id, settings)
        usadas = count_month_usage(user_id, settings, kinds=("cleaning",))
        addons = addons_balance(user_id, settings)
    except httpx.HTTPError as exc:
        print(
            f"[quota] No se pudo verificar el cupo de limpieza dirigida "
            f"({exc.__class__.__name__}); se permite el intento."
        )
        return None
    base = cleaning_limit_for(plan, settings)
    if is_admin:
        return {
            "plan": plan,
            "usadas_mes": usadas,
            "base": base,
            "addons": addons,
            "consume_addon": False,
            "ilimitado": True,
        }
    consume_addon = usadas >= base
    if consume_addon and addons <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Usaste tus {base} intentos de limpieza dirigida de este mes y no "
                "tienes tokens adicionales. Solicita más tokens en la página Planes "
                "(addons) y nos pondremos en contacto contigo."
            ),
        )
    return {
        "plan": plan,
        "usadas_mes": usadas,
        "base": base,
        "addons": addons,
        "consume_addon": consume_addon,
        "ilimitado": False,
    }


def record_cleaning_usage(user_id: str, settings: Settings, consume_addon: bool) -> None:
    """Registra un intento de limpieza dirigida consumido. Best-effort.

    Si el intento excede la base mensual, descuenta 1 crédito addon insertando
    una fila negativa en el ledger plan_addons (auditable: quién/cuándo).
    """
    if not _configured(settings):
        return
    record_usage(user_id, "cleaning", settings)
    if not consume_addon:
        return
    try:
        response = httpx.post(
            _rest(settings, "plan_addons"),
            json={
                "user_id": user_id,
                "credits": -1,
                "granted_by": "sistema",
                "note": "Consumo de limpieza dirigida IA",
            },
            headers={**_headers(settings), "Prefer": "return=minimal"},
            timeout=_TIMEOUT,
        )
        if response.status_code >= 400:
            print(
                f"[quota] plan_addons respondió {response.status_code} al descontar "
                "un crédito (¿está ejecutada la migración 0009?)."
            )
    except httpx.HTTPError as exc:
        print(f"[quota] No se pudo descontar el crédito addon ({exc.__class__.__name__}).")


def cleaning_usage_info(user_id: str, settings: Settings) -> dict:
    """Estado del cupo de limpieza dirigida para Planes y Configuración.
    La base depende del plan del usuario (Fase 8: 10 Analista / 25 Gold)."""
    if not _configured(settings):
        return {
            "disponible": False,
            "usadas_mes": 0,
            "base": settings.ai_cleaning_monthly_limit,
            "addons": 0,
            "ilimitado": False,
        }
    try:
        plan, is_admin = get_profile_flags(user_id, settings)
        usadas = count_month_usage(user_id, settings, kinds=("cleaning",))
        addons = addons_balance(user_id, settings)
    except httpx.HTTPError:
        return {
            "disponible": False,
            "usadas_mes": 0,
            "base": settings.ai_cleaning_monthly_limit,
            "addons": 0,
            "ilimitado": False,
        }
    return {
        "disponible": True,
        "usadas_mes": usadas,
        "base": cleaning_limit_for(plan, settings),
        "addons": addons,
        "ilimitado": is_admin,
    }
