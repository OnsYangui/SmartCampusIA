from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """FastAPI runtime settings."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SmartCampus AI API"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"
    database_url: str

    # SA-25 / SA-26 : sessions visiteurs et mémoire temporaire de la conversation
    session_cookie_name: str = "sc_session"
    session_idle_ttl_minutes: int = 60 * 24  # expire après 24 h d'inactivité
    session_max_lifetime_days: int = 7  # durée de vie maximale, même si le visiteur reste actif
    session_max_messages: int = 30  # nombre maximal de messages d'un visiteur par session
    message_max_chars: int = 2000  # taille maximale d'un message
    memory_window_messages: int = 12  # nombre de messages récents donnés à l'agent

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


class MigrationSettings(BaseSettings):
    """Alembic-only settings, never loaded by the running API."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / "migrations" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    migration_database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_migration_settings() -> MigrationSettings:
    return MigrationSettings()
