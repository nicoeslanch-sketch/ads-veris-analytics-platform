"""Prueba gratuita de 15 días (Fase 14).

Estado del trial desde ``account_trials`` (migración 0016). La activación es
una RPC atómica en Postgres (``activate_account_trial``) ejecutable SOLO por
la service_role — así el rate limiting de la API es insoslayable y ningún
cliente puede pasarle un user_id arbitrario (la RPC prioriza auth.uid() y el
parámetro solo se honra en el camino service_role, tras validar el JWT aquí).

Las fechas son del SERVIDOR: ``ends_at`` se calcula en la RPC con
``now() + interval '15 days'`` y la vigencia se evalúa contra ``now()`` — no
existe cron ni campo "activo" mantenido a mano, y el frontend recibe
``days_remaining`` calculado acá, nunca del reloj del navegador.

Privacidad de errores: los códigos sobre el PROPIO solicitante son específicos
(USER_ALREADY_USED_TRIAL); los que involucran a terceros (RUT ya usado)
colapsan a un mensaje genérico para no revelar qué empresas usan la plataforma.
"""

from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status

from .config import Settings

_TIMEOUT = 10

TRIAL_DAYS = 15

EMPTY_TRIAL: dict = {
    "used": False,
    "active": False,
    "started_at": None,
    "ends_at": None,
    "days_remaining": 0,
}


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, path: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{path}"


def _configured(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def trial_state_from_row(row: dict | None, now: datetime | None = None) -> dict:
    """Estado del trial a partir de una fila de account_trials (o None).

    Regla de vigencia (idéntica a can_process_data() en SQL):
    started_at <= now < ends_at AND revoked_at IS NULL.
    """
    if not row:
        return dict(EMPTY_TRIAL)
    now = now or datetime.now(timezone.utc)
    started = _parse_ts(row.get("started_at"))
    ends = _parse_ts(row.get("ends_at"))
    revoked = _parse_ts(row.get("revoked_at"))
    active = bool(
        revoked is None and started and ends and started <= now < ends
    )
    remaining = 0
    if active and ends:
        remaining = max(0, (ends - now).days + (1 if (ends - now).seconds else 0))
    return {
        "used": True,
        "active": active,
        "started_at": started.isoformat() if started else None,
        "ends_at": ends.isoformat() if ends else None,
        "days_remaining": remaining,
    }


def get_trial_state(user_id: str, settings: Settings) -> dict:
    """Trial del usuario vía PostgREST (service_role). Sin Supabase o sin la
    migración 0016 ejecutada → 'sin trial' (fail-safe: no rompe la API)."""
    if not _configured(settings):
        return dict(EMPTY_TRIAL)
    try:
        response = httpx.get(
            _rest(settings, "account_trials"),
            params={
                "user_id": f"eq.{user_id}",
                "select": "started_at,ends_at,revoked_at",
                "limit": "1",
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        print(f"[trial] No se pudo consultar account_trials ({exc.__class__.__name__}).")
        return dict(EMPTY_TRIAL)
    if response.status_code == 404:
        # Migración 0016 sin ejecutar: la plataforma sigue operando sin trials.
        return dict(EMPTY_TRIAL)
    if response.status_code >= 400:
        print(f"[trial] account_trials respondió {response.status_code} (¿migración 0016?).")
        return dict(EMPTY_TRIAL)
    rows = response.json()
    return trial_state_from_row(rows[0] if rows else None)


# ── Activación (RPC atómica) ──────────────────────────────────────────────────

_GENERIC_RUT_MESSAGE = (
    "Este RUT no es elegible para una nueva prueba gratuita. Revisa los datos "
    "o contacta a soporte si consideras que se trata de un error."
)

_ERROR_RESPONSES: dict[str, tuple[int, str]] = {
    # Error del PROPIO solicitante → específico (no revela nada de terceros).
    "USER_ALREADY_USED_TRIAL": (
        status.HTTP_409_CONFLICT,
        "Tu cuenta ya utilizó la prueba gratuita de 15 días. "
        "Puedes contratar un plan en la página Planes.",
    ),
    # Involucra a terceros → genérico (anti-enumeración de clientes por RUT).
    "RUT_ALREADY_USED_TRIAL": (status.HTTP_409_CONFLICT, _GENERIC_RUT_MESSAGE),
    "TRIAL_NOT_ELIGIBLE": (status.HTTP_409_CONFLICT, _GENERIC_RUT_MESSAGE),
    "INVALID_RUT": (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "El RUT ingresado no es válido. Revisa el número y el dígito verificador.",
    ),
}


def activate_trial(user_id: str, rut_type: str, rut_normalized: str, settings: Settings) -> dict:
    """Llama a la RPC activate_account_trial (SECURITY DEFINER, migración 0016).

    Devuelve el estado del trial recién creado. Lanza HTTPException con el
    mensaje es-CL que corresponda (específico para errores propios, genérico
    para los que involucran a terceros). El RUT completo JAMÁS se loguea.
    """
    if not _configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La activación de la prueba no está disponible en este entorno.",
        )
    try:
        response = httpx.post(
            _rest(settings, "rpc/activate_account_trial"),
            json={
                "p_user_id": user_id,
                "p_rut_type": rut_type,
                "p_rut": rut_normalized,
            },
            headers=_headers(settings),
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        print(f"[trial] RPC de activación inalcanzable ({exc.__class__.__name__}).")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo activar la prueba. Intenta nuevamente en unos minutos.",
        ) from exc
    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "La prueba gratuita aún no está habilitada en este entorno "
                "(falta ejecutar la migración 0016)."
            ),
        )
    if response.status_code >= 400:
        print(f"[trial] RPC de activación respondió {response.status_code}.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo activar la prueba. Intenta nuevamente en unos minutos.",
        )
    result = response.json()
    if not isinstance(result, dict):
        result = {}
    if not result.get("ok"):
        code = str(result.get("error") or "TRIAL_NOT_ELIGIBLE")
        http_status, message = _ERROR_RESPONSES.get(
            code, _ERROR_RESPONSES["TRIAL_NOT_ELIGIBLE"]
        )
        # El código exacto queda en logs internos SIN el RUT; auditoría en la tabla.
        print(f"[trial] Activación rechazada user={user_id} code={code}")
        raise HTTPException(status_code=http_status, detail=message)
    return trial_state_from_row(result.get("trial"))
