import pytest
from pydantic import ValidationError

import app.core.config as config

DATABASE_URL = "postgresql+psycopg://app:secret@localhost/smartcampus"
MIGRATION_DATABASE_URL = "postgresql+psycopg://owner:secret@localhost/smartcampus"


def test_runtime_settings_do_not_require_migration_credentials() -> None:
    settings = config.Settings(_env_file=None, database_url=DATABASE_URL)

    assert "migration_database_url" not in type(settings).model_fields


def test_migration_settings_are_isolated_from_runtime_settings() -> None:
    migration_settings_type = getattr(config, "MigrationSettings", None)
    assert migration_settings_type is not None

    settings = migration_settings_type(
        _env_file=None,
        migration_database_url=MIGRATION_DATABASE_URL,
    )

    assert settings.migration_database_url == MIGRATION_DATABASE_URL
    assert "database_url" not in type(settings).model_fields


# SA-28 — authentication settings
def test_development_without_a_jwt_secret_gets_a_random_one() -> None:
    first = config.Settings(_env_file=None, database_url=DATABASE_URL)
    second = config.Settings(_env_file=None, database_url=DATABASE_URL)

    assert len(first.jwt_secret) >= config.MIN_JWT_SECRET_LENGTH
    assert first.jwt_secret != second.jwt_secret


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_other_environments_require_a_jwt_secret(environment: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY is required"):
        config.Settings(_env_file=None, database_url=DATABASE_URL, environment=environment)


def test_a_short_jwt_secret_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least"):
        config.Settings(_env_file=None, database_url=DATABASE_URL, jwt_secret_key="short")


def test_the_example_placeholder_is_refused() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        config.Settings(
            _env_file=None, database_url=DATABASE_URL, jwt_secret_key="change_me_" + "x" * 30
        )


def test_cookies_are_secure_except_in_development() -> None:
    secret = "s" * 40
    dev = config.Settings(_env_file=None, database_url=DATABASE_URL, jwt_secret_key=secret)
    prod = config.Settings(
        _env_file=None, database_url=DATABASE_URL, jwt_secret_key=secret, environment="production"
    )
    forced = config.Settings(
        _env_file=None, database_url=DATABASE_URL, jwt_secret_key=secret, cookie_secure=True
    )

    assert not dev.secure_cookies
    assert prod.secure_cookies
    assert forced.secure_cookies
