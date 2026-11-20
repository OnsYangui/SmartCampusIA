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
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 90

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
