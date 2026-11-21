import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

MIN_JWT_SECRET_LENGTH = 32


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
    ollama_timeout_seconds: float = Field(default=90, gt=0)
    ollama_temperature: float = Field(default=0.3, ge=0, le=2)

    # SA-25 / SA-26 : sessions visiteurs et mémoire temporaire de la conversation
    session_cookie_name: str = "sc_session"
    session_idle_ttl_minutes: int = 60 * 24  # expire après 24 h d'inactivité
    session_max_lifetime_days: int = 7  # durée de vie maximale, même si le visiteur reste actif
    session_max_messages: int = 30  # nombre maximal de messages d'un visiteur par session
    message_max_chars: int = 2000  # taille maximale d'un message
    memory_window_messages: int = 12  # nombre de messages récents donnés à l'agent

    # Authentication (SA-28, SA-5): short-lived JWT in an HttpOnly cookie plus a refresh token.
    # Mandatory outside development; in development a random per-process secret is used when
    # the variable is missing (sessions then end whenever the API restarts).
    jwt_secret_key: SecretStr | None = None
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    # None = automatic: Secure cookies everywhere except development (plain http://localhost).
    cookie_secure: bool | None = None
    # Development only: password given to the demonstration accounts by `python -m app.seed`.
    demo_password: SecretStr | None = None

    @model_validator(mode="after")
    def _check_authentication(self) -> Self:
        secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
        if secret.startswith("change_me"):
            raise ValueError("JWT_SECRET_KEY still holds the .env.example placeholder")
        if not secret:
            if self.environment != "development":
                raise ValueError("JWT_SECRET_KEY is required outside development")
            self.jwt_secret_key = SecretStr(secrets.token_urlsafe(48))
        elif len(secret) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must hold at least {MIN_JWT_SECRET_LENGTH} characters"
            )
        return self

    @property
    def jwt_secret(self) -> str:
        assert self.jwt_secret_key is not None  # guaranteed by the validator
        return self.jwt_secret_key.get_secret_value()

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment != "development"

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
