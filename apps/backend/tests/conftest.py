import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.engine import make_url

from app.core.config import MigrationSettings, Settings, get_migration_settings, get_settings


def _test_url(url: str) -> str:
    parsed = make_url(url)
    return parsed.set(database=f"{parsed.database}_test").render_as_string(hide_password=False)


# Point the app (smartcampus_app) and the migrations (smartcampus_owner) at the test database
# before anything creates an engine.
_runtime = Settings()
_migration = MigrationSettings()
os.environ["DATABASE_URL"] = _test_url(_runtime.database_url)
os.environ["MIGRATION_DATABASE_URL"] = _test_url(_migration.migration_database_url)
get_settings.cache_clear()
get_migration_settings.cache_clear()

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture(scope="session", autouse=True)
def migrated_database(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")


@pytest.fixture
def conn() -> Iterator[Connection]:
    """Connection as smartcampus_app, rolled back after each test."""
    from app.core.db import engine

    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
