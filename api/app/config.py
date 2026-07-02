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

    # SOLO desarrollo local sin Supabase: acepta requests sin JWT.
    # Jamás activar en producción.
    dev_auth_bypass: bool = False

    allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
