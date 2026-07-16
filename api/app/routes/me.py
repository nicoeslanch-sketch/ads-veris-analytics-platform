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


def _build_access_sync(user_id: str, settings: Settings) -> dict:
    configured = bool(settings.supabase_url and settings.supabase_service_role_key)
    enforcement = bool(settings.plan_enforcement and configured)
    if not configured:
        # Desarrollo local sin Supabase: fail-open coherente con las puertas.
        plan, is_admin = "basico", False
        trial = dict(trials.EMPTY_TRIAL)
    else:
        plan, is_admin = get_profile_flags(user_id, settings)
        # El estado del trial solo importa para cuentas sin plan pagado: las
        # demás no pagan la consulta extra.
        trial = (
            trials.get_trial_state(user_id, settings)
            if plan == "sin_plan" and not is_admin
            else dict(trials.EMPTY_TRIAL)
        )
    caps = effective_capabilities(plan, is_admin, bool(trial.get("active")), enforcement)
    return {
        "paid_plan": plan,
        "plan_display": display_plan(plan),
        "is_admin": is_admin,
        "enforcement": enforcement,
        "trial": trial,
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
