import re
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno del motor de datos (ver .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_storage_bucket: str = "datasets"

    anthropic_api_key: str = ""
    anthropic_model: str = ""

    # Cuotas mensuales de consultas IA (insights) por plan (SPEC §9)
    ai_monthly_limit_basico: int = 20
    ai_monthly_limit_analista: int = 200
    ai_monthly_limit_gold: int = 200

    # ── Fase 7/8: planes y limpieza dirigida ──
    # Interruptor global de gating por plan. Desde la Fase 8 queda ENCENDIDO:
    # descargar la base limpia y la limpieza dirigida exigen Plan Analista.
    # El administrador (profiles.is_admin) pasa todas las puertas.
    # Apagarlo no requiere tocar código: PLAN_ENFORCEMENT=false
    # (+ VITE_PLAN_ENFORCEMENT en el frontend).
    plan_enforcement: bool = True
    # Intentos base de limpieza dirigida por mes, POR PLAN (se suman los
    # créditos addon de plan_addons, migración 0009). Fase 8: sube de 2 a
    # 10/25 — la interpretación consume pocos tokens por intento, y con 10
    # el Plan Analista se siente útil sin riesgo de costo (ver PHASE_STATUS).
    ai_cleaning_monthly_limit: int = 10        # Plan Analista (y fallback)
    ai_cleaning_monthly_limit_gold: int = 25   # Plan Gold
    # Costura IA del motor (§5.13): refinado final del dataset con IA.
    # Preparado pero APAGADO hasta perfeccionar el motor determinista.
    ai_refine_enabled: bool = False

    # ── Fase 8: retención de archivos en Storage (por usuario) ──
    # Tope de archivos guardados por plan; al subir uno nuevo, el frontend
    # dispara POST /storage/retention y el backend poda: primero el excedente
    # sobre el tope y luego lo no usado hace más de N días. Los últimos
    # `storage_keep_last` archivos JAMÁS se borran.
    storage_max_files_basico: int = 10
    storage_max_files_analista: int = 25
    storage_max_files_gold: int = 50
    storage_retention_days: int = 60
    storage_keep_last: int = 5

    # SOLO desarrollo local sin Supabase: acepta requests sin JWT.
    # Jamás activar en producción.
    dev_auth_bypass: bool = False

    allowed_origins: str = "http://localhost:5173,http://localhost:4173"
    allowed_origin_regex: str = (
        r"https://("
        r"ads-veris-analytics-platform(-[a-z0-9]+|-nicoeslanch-sketchs-projects)?"
        r"|ads-veris-analytics-pla-git-[a-z0-9]+-nicoeslanch-sketchs-projects"
        r")\.vercel\.app"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def is_cors_origin_allowed(self, origin: str) -> bool:
        return origin in self.cors_origins or bool(
            self.allowed_origin_regex
            and re.fullmatch(self.allowed_origin_regex, origin)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
