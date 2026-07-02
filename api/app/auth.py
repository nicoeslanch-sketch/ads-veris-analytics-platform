"""Validación del JWT de Supabase (SPEC §2 — seguridad de la API Python).

Todos los endpoints sensibles dependen de `get_current_user`: el frontend envía
el access_token de la sesión Supabase en `Authorization: Bearer <jwt>` y aquí se
verifica firma (HS256 con SUPABASE_JWT_SECRET), expiración y audiencia antes de
procesar cualquier dato. Ningún endpoint sensible queda público.
"""

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None
    claims: dict


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    # Modo desarrollo sin Supabase (DEV_AUTH_BYPASS=true y sin JWT secret):
    # permite probar el pipeline en local. Nunca activar en producción.
    if settings.dev_auth_bypass and not settings.supabase_jwt_secret:
        return AuthenticatedUser(id="dev-user", email="dev@localhost", claims={})
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor no tiene configurado SUPABASE_JWT_SECRET.",
        )
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión expiró. Inicia sesión nuevamente.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )
    return AuthenticatedUser(
        id=claims.get("sub", ""),
        email=claims.get("email"),
        claims=claims,
    )
