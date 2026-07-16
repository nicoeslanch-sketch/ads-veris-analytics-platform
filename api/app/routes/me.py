"""Contexto de acceso del usuario + activación de la prueba gratuita (Fase 14).

GET  /me/access — LA fuente de verdad que consume el frontend: plan pagado,
                  admin, estado del trial y capacidades EFECTIVAS calculadas
                  en el servidor. El cliente no reconstruye capacidades desde
                  el plan (evita que las matrices Python/TS diverjan).

POST /me/trial  — activa la prueba gratuita de 15 días. Valida el RUT en
                  Python (feedback temprano), aplica rate limiting (el RUT no
                  puede volverse un mecanismo de consulta masiva de
                  elegibilidad) y delega la escritura a la RPC atómica
                  ``activate_account_trial`` (migración 0016) — la unicidad
                  por usuario y por RUT vive en constraints de Postgres, no
                  en un check-then-insert de Python.

Privacidad: el RUT viaja SOLO en el body (jamás en URLs), no se loguea y las
respuestas nunca revelan qué otra cuenta usó un RUT.
"""

import threading
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import httpx

from .. import trials
from ..auth import AuthenticatedUser, get_current_user
from ..capabilities import (
    display_plan,
    effective_capabilities,
    get_profile_flags,
)
from ..config import Settings, get_settings
from ..rut import is_valid_rut, mask_rut, normalize_rut

router = APIRouter(prefix="/me", dependencies=[Depends(get_current_user)])

# ── Rate limiting de activación (en memoria, por usuario) ────────────────────
# Ventana deslizante simple: N intentos por ventana. Vive en memoria (una
# instancia); si la API escala horizontal, moverlo a la base. Se aplica ANTES
# de tocar la RPC — y como la RPC solo es ejecutable por la service_role, el
# límite no se puede esquivar hablándole directo a PostgREST.
_TRIAL_ATTEMPT_WINDOW_S = 600
_TRIAL_ATTEMPT_MAX = 5
_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def _guard_activation_rate(user_id: str) -> None:
    now = time.monotonic()
    with _attempts_lock:
        recent = [t for t in _attempts.get(user_id, []) if now - t < _TRIAL_ATTEMPT_WINDOW_S]
        if len(recent) >= _TRIAL_ATTEMPT_MAX:
            _attempts[user_id] = recent
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos de activación. Espera unos minutos "
                "y vuelve a intentarlo.",
            )
        recent.append(now)
        _attempts[user_id] = recent


# ── Contexto de acceso ────────────────────────────────────────────────────────


def _rest_headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _billing_identity_sync(user_id: str, settings: Settings) -> dict | None:
    """Identidad de facturación más reciente del usuario (enmascarada) — la
    consume Planes para no volver a pedir el RUT al contratar. El RUT completo
    JAMÁS sale por esta vía."""
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/billing_identities",
            params={
                "user_id": f"eq.{user_id}",
                "select": "id,rut_type,rut_masked",
                "order": "updated_at.desc",
                "limit": "1",
            },
            headers=_rest_headers(settings),
            timeout=10,
        )
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    rows = response.json()
    return rows[0] if rows else None


def _build_access_sync(user_id: str, settings: Settings) -> dict:
    configured = bool(settings.supabase_url and settings.supabase_service_role_key)
    enforcement = bool(settings.plan_enforcement and configured)
    if not configured:
        # Desarrollo local sin Supabase: fail-open coherente con las puertas.
        plan, is_admin = "basico", False
        trial = dict(trials.EMPTY_TRIAL)
        identity = None
    else:
        plan, is_admin = get_profile_flags(user_id, settings)
        # El estado del trial solo importa para cuentas sin plan pagado: las
        # demás no pagan la consulta extra.
        trial = (
            trials.get_trial_state(user_id, settings)
            if plan == "sin_plan" and not is_admin
            else dict(trials.EMPTY_TRIAL)
        )
        identity = _billing_identity_sync(user_id, settings)
    caps = effective_capabilities(plan, is_admin, bool(trial.get("active")), enforcement)
    return {
        "paid_plan": plan,
        "plan_display": display_plan(plan),
        "is_admin": is_admin,
        "enforcement": enforcement,
        "trial": trial,
        "billing_identity": identity,
        "capabilities": sorted(str(c) for c in caps),
    }


@router.get("/access")
async def me_access(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Contexto de acceso efectivo del usuario (plan + admin + trial + caps)."""
    try:
        return await run_in_threadpool(_build_access_sync, user.id, settings)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[access] No se pudo construir el contexto ({exc.__class__.__name__}).")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo verificar tu acceso. Intenta nuevamente en unos minutos.",
        ) from exc


# ── Activación de la prueba gratuita ─────────────────────────────────────────


class TrialActivationBody(BaseModel):
    rut_type: Literal["empresa", "responsable"]
    rut: str = Field(min_length=2, max_length=20)


def _guard_trial_eligibility_sync(user: AuthenticatedUser, settings: Settings) -> None:
    """Elegibilidad COMERCIAL antes de tocar la RPC (que la re-verifica como
    autoridad final): la prueba es SOLO para cuentas sin plan. Un usuario
    Básico/Analista/Gold o un administrador no gana nada activándola, pero
    podía RESERVAR el RUT de otra empresa e impedir que su titular legítimo
    probara la plataforma."""
    plan, is_admin = get_profile_flags(user.id, settings)
    if is_admin or plan != "sin_plan":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La prueba gratuita es para cuentas nuevas sin plan. "
            "Tu cuenta ya tiene acceso con su plan actual.",
        )
    # Correo confirmado (antiabuso): solo bloquea si el claim dice
    # explícitamente que NO está verificado — proyectos sin confirmación de
    # correo habilitada no se rompen.
    metadata = user.claims.get("user_metadata") or {}
    if metadata.get("email_verified") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Confirma tu correo electrónico antes de activar la prueba "
            "gratuita (revisa tu bandeja de entrada).",
        )


@router.post("/trial")
async def activate_trial(
    body: TrialActivationBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Activa la prueba gratuita de 15 días (una por usuario Y por RUT)."""
    _guard_activation_rate(user.id)
    normalized = normalize_rut(body.rut)
    if not normalized or not is_valid_rut(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El RUT ingresado no es válido. Revisa el número y el "
            "dígito verificador.",
        )
    # El mismo RUT no debe poder sondearse sin límite alternando usuarios:
    # también hay ventana por RUT normalizado (jamás se loguea el RUT).
    _guard_activation_rate(f"rut:{normalized}")
    if settings.supabase_url and settings.supabase_service_role_key:
        await run_in_threadpool(_guard_trial_eligibility_sync, user, settings)
    trial = await run_in_threadpool(
        trials.activate_trial, user.id, body.rut_type, normalized, settings
    )
    access = await run_in_threadpool(_build_access_sync, user.id, settings)
    # El estado recién creado manda: si PostgREST tarda en ver la fila, el
    # contexto igual vuelve con el trial activo (una sola vuelta, sin recargar).
    if trial.get("active") and not access["trial"].get("active"):
        access["trial"] = trial
        access["capabilities"] = sorted(
            str(c)
            for c in effective_capabilities(
                access["paid_plan"], access["is_admin"], True, access["enforcement"]
            )
        )
    return {
        "activada": True,
        "rut_confirmado": mask_rut(normalized),
        "access": access,
    }


# ── Identidad de facturación (contratación de planes) ────────────────────────


class BillingIdentityBody(BaseModel):
    rut_type: Literal["empresa", "responsable"]
    rut: str = Field(min_length=2, max_length=20)


def _upsert_identity_sync(user_id: str, rut_type: str, normalized: str, settings: Settings) -> dict:
    """Crea o actualiza la identidad de facturación del usuario (una fila por
    usuario+RUT — el mismo esquema que usa la RPC del trial). Se usa al
    CONTRATAR un plan: la solicitud queda vinculada a `billing_identity_id`,
    nunca al RUT en texto libre."""
    payload = {
        "user_id": user_id,
        "rut_type": rut_type,
        "rut_normalized": normalized,
        "rut_masked": mask_rut(normalized),
    }
    try:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/billing_identities",
            params={"on_conflict": "user_id,rut_normalized"},
            json=payload,
            headers={
                **_rest_headers(settings),
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar la identidad de facturación. Intenta nuevamente.",
        ) from exc
    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falta ejecutar la migración 0016 en Supabase.",
        )
    if response.status_code >= 400:
        print(f"[billing] billing_identities respondió {response.status_code}.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar la identidad de facturación. Intenta nuevamente.",
        )
    rows = response.json()
    row = rows[0] if isinstance(rows, list) and rows else {}
    return {
        "id": row.get("id"),
        "rut_type": row.get("rut_type", rut_type),
        "rut_masked": row.get("rut_masked", mask_rut(normalized)),
    }


@router.post("/billing-identity")
async def save_billing_identity(
    body: BillingIdentityBody,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Registra el RUT de facturación (empresa o responsable) para contratar."""
    _guard_activation_rate(user.id)
    normalized = normalize_rut(body.rut)
    if not normalized or not is_valid_rut(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El RUT ingresado no es válido. Revisa el número y el "
            "dígito verificador.",
        )
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Esta función requiere Supabase configurado en el servidor.",
        )
    identity = await run_in_threadpool(
        _upsert_identity_sync, user.id, body.rut_type, normalized, settings
    )
    return {"guardada": True, "identity": identity}
