import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import MigrationSettings, Settings, get_migration_settings, get_settings
from tests.factories import insert, new_program


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


@pytest.fixture
def api(conn: Connection) -> Iterator[TestClient]:
    """API client whose requests run inside the test's rolled-back transaction."""
    from app.core.db import get_session
    from app.main import app

    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session)
        session.close()


@pytest.fixture
def catalog(conn: Connection) -> dict[str, uuid.UUID]:
    """Two institutions, four active programs, one inactive program and one pathway."""
    iit = insert(conn, "institutions", code="IIT", name="Institut International de Technologie")
    isb = insert(conn, "institutions", code="ISB", name="ISB", website="https://isb.example")
    ids = {"iit": iit, "isb": isb}
    ids["prepa"] = new_program(
        conn, iit, "IIT-PREPA", name="Cycle préparatoire intégré", type="prepa", duration_years=2
    )
    ids["info"] = new_program(
        conn,
        iit,
        "IIT-LIC-INFO",
        name="Licence en informatique",
        field="Informatique",
        admission_bac_sections=["Mathématiques", "Informatique"],
        min_bac_average=12,
        prerequisites="Admission sur dossier",
    )
    ids["genie"] = new_program(
        conn, iit, "IIT-ING-GL", name="Ingénieur en génie logiciel", type="ingenieur"
    )
    ids["gestion"] = new_program(conn, isb, "ISB-LIC-GEST", name="Licence en gestion")
    ids["closed"] = new_program(conn, isb, "ISB-OLD", name="Ancienne formation", is_active=False)
    conn.execute(
        text(
            "INSERT INTO program_pathways (from_program_id, to_program_id, conditions) "
            "VALUES (:prepa, :genie, 'Validation des deux années')"
        ),
        ids,
    )
    return ids
