"""Motor de datos de ADS Veris — FastAPI + pandas.

Fase 0: esqueleto con health check y autenticación JWT.
Fase 1: pipeline /standardize, /clean y /metrics (SPEC §6), protegido con JWT.
"""

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthenticatedUser, get_current_user
from .config import Settings, get_settings
from .version import ENGINE_VERSION, LATEST_MIGRATION, commit_sha
from .routes.admin import router as admin_router
from .routes.ai import router as ai_router
from .routes.connectors import router as connectors_router
from .routes.datasets import router as datasets_router
from .routes.me import router as me_router
from .routes.pipeline import router as pipeline_router
from .routes.plans import router as plans_router
from .routes.retention import router as retention_router
from .routes.support import router as support_router

settings = get_settings()
logger = logging.getLogger(__name__)


def validate_production_config(cfg: Settings) -> list[str]:
    """Fase 15: en producción, la configuración insegura IMPIDE arrancar.

    Devuelve la lista de violaciones (vacía = seguro). Con APP_ENV=production
    la API no puede quedar "funcionando" con las puertas comerciales apagadas,
    el bypass de desarrollo activo o sin Supabase — un despliegue así parece
    sano y regala la plataforma completa.
    """
    if cfg.app_env.strip().lower() != "production":
        return []
    violations: list[str] = []
    if not cfg.supabase_url:
        violations.append("SUPABASE_URL está vacío")
    if not cfg.supabase_service_role_key:
        violations.append("SUPABASE_SERVICE_ROLE_KEY está vacío")
    if not cfg.plan_enforcement:
        violations.append("PLAN_ENFORCEMENT=false (puertas comerciales apagadas)")
    if cfg.dev_auth_bypass:
        violations.append("DEV_AUTH_BYPASS=true (autenticación desactivada)")
    non_local = [
        o for o in cfg.cors_origins if "localhost" not in o and "127.0.0.1" not in o
    ]
    if not non_local and not cfg.allowed_origin_regex:
        violations.append("ALLOWED_ORIGINS solo contiene orígenes locales")
    return violations


_violations = validate_production_config(settings)
if _violations:
    raise RuntimeError(
        "Startup failed: insecure production configuration — " + "; ".join(_violations)
    )

app = FastAPI(
    title="ADS Veris — Motor de datos",
    description="Estandarización, limpieza y métricas para la plataforma de análisis.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _warn_denied_origin(request, call_next):
    """Log seguro para diagnosticar CORS en producción: solo Origin + ruta, jamás tokens."""
    origin = request.headers.get("origin")
    if origin and not settings.is_cors_origin_allowed(origin):
        logger.warning(
            "[CORS] Origen NO permitido: %s -> %s %s "
            "(ALLOWED_ORIGINS tiene %d orígenes)",
            origin,
            request.method,
            request.url.path,
            len(settings.cors_origins),
        )
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    """Único endpoint público: verificación de vida para Render/Railway."""
    return {"status": "ok", "service": "ads-veris-data-engine"}


@app.get("/version")
def version() -> dict:
    """Identidad del despliegue (Fase 15): qué commit, motor y migración
    esperada corren AQUÍ — el smoke test posterior al deploy compara este SHA
    con el que se quiso publicar. Público: no revela secretos."""
    return {
        "status": "ok",
        "commit_sha": commit_sha(),
        "engine_version": ENGINE_VERSION,
        "database_migration": LATEST_MIGRATION,
        "environment": settings.app_env,
    }


@app.get("/me")
def me(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Endpoint de prueba de autenticación: devuelve la identidad del JWT."""
    return {"id": user.id, "email": user.email}


app.include_router(pipeline_router)
app.include_router(me_router)
app.include_router(ai_router)
app.include_router(connectors_router)
app.include_router(datasets_router)
app.include_router(plans_router)
app.include_router(admin_router)
app.include_router(support_router)
app.include_router(retention_router)
