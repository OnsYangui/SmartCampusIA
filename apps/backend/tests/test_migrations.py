from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_migration_settings


def test_migrations_go_down_and_up_again(alembic_config: Config) -> None:
    engine = create_engine(get_migration_settings().migration_database_url)
    try:
        command.downgrade(alembic_config, "0001")
        assert inspect(engine).get_table_names() == ["alembic_version"]

        command.upgrade(alembic_config, "head")
        assert len(inspect(engine).get_table_names()) == 25  # 24 tables + alembic_version
    finally:
        engine.dispose()
