"""Validación del JWT de Supabase (SPEC §2 — seguridad de la API Python).

Soporta dos modos de firma detectados automáticamente desde el header del token:

- HS256 (legacy): valida con SUPABASE_JWT_SECRET.
- ES256 / RS256 (nuevo estándar Supabase con ECC/P-256): valida via JWKS en
  {SUPABASE_URL}/auth/v1/.well-known/jwks.json.

El cliente JWKS (PyJWKClient) se cachea por URL y renueva claves cada 5 minutos.
"""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt.exceptions import PyJWKClientError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None
    claims: dict


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    """Instancia de PyJWKClient cacheada por URL; renueva claves cada 5 min."""
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _decode(token: str, settings: Settings) -> dict:
    """Decodifica y valida el JWT según el algoritmo declarado en el header."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise jwt.InvalidTokenError("Token malformado.") from exc

    alg = header.get("alg", "HS256")

    # ── HS256 — legacy JWT Secret ──────────────────────────────────────────
    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidTokenError(
                "Token HS256 recibido pero SUPABASE_JWT_SECRET no está configurado."
            )
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )

    # ── ES256 / RS256 — JWKS (Supabase ECC/P-256 signing keys) ───────────
    if alg in ("ES256", "RS256"):
        if not settings.supabase_url:
            raise jwt.InvalidTokenError(
                "Token asimétrico recibido pero SUPABASE_URL no está configurado."
            )
        jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        try:
            client = _jwks_client(jwks_url)
            signing_key = client.get_signing_key_from_jwt(token)
        except PyJWKClientError as exc:
            raise jwt.InvalidTokenError(
                f"No se pudo validar la clave pública JWKS: {exc}"
            ) from exc
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )

    raise jwt.InvalidTokenError(f"Algoritmo de firma no soportado: {alg}.")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    # Modo desarrollo local: DEV_AUTH_BYPASS=true y sin credenciales configuradas.
    # Jamás activar en producción (Render siempre tiene SUPABASE_URL).
    no_creds = not settings.supabase_jwt_secret and not settings.supabase_url
    if settings.dev_auth_bypass and no_creds:
        return AuthenticatedUser(id="dev-user", email="dev@localhost", claims={})

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = _decode(credentials.credentials, settings)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión expiró. Inicia sesión nuevamente.",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc) or "Token inválido.",
        )

    return AuthenticatedUser(
        id=claims.get("sub", ""),
        email=claims.get("email"),
        claims=claims,
    )
