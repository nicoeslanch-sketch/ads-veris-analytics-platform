"""Motor de datos de ADS Veris — FastAPI + pandas.

Fase 0: esqueleto con health check y autenticación JWT.
Fase 1: pipeline /standardize, /clean y /metrics (SPEC §6), protegido con JWT.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthenticatedUser, get_current_user
from .config import get_settings
from .routes.ai import router as ai_router
from .routes.pipeline import router as pipeline_router

settings = get_settings()

app = FastAPI(
    title="ADS Veris — Motor de datos",
    description="Estandarización, limpieza y métricas para la plataforma de análisis.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _warn_denied_origin(request, call_next):
    """Log seguro para diagnosticar CORS en producción: solo Origin + ruta, jamás tokens."""
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_origins:
        print(f"[CORS] Origen NO permitido: {origin} → {request.method} {request.url.path} "
              f"(ALLOWED_ORIGINS tiene {len(settings.cors_origins)} orígenes)")
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    """Único endpoint público: verificación de vida para Render/Railway."""
    return {"status": "ok", "service": "ads-veris-data-engine"}


@app.get("/me")
def me(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Endpoint de prueba de autenticación: devuelve la identidad del JWT."""
    return {"id": user.id, "email": user.email}


app.include_router(pipeline_router)
app.include_router(ai_router)
