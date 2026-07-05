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

    # Cuotas mensuales de consultas IA por plan (SPEC §9)
    ai_monthly_limit_basico: int = 20
    ai_monthly_limit_gold: int = 200

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
