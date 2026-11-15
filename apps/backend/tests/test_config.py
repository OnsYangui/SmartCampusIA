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
