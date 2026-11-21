import pytest
from sqlalchemy import Connection, text

import app.seed as seed
from app.core.config import Settings

CANDIDATES = seed.CANDIDATES
seed_demo = seed.seed_demo
seed_reference = seed.seed_reference

TABLES = [
    "institutions",
    "programs",
    "program_fees",
    "program_pathways",
    "admission_campaigns",
    "users",
    "candidates",
    "profiles",
    "consents",
    "recommendations",
    "applications",
    "state_transitions",
    "quizzes",
    "quiz_questions",
    "interview_slots",
    "appointments",
    "message_templates",
]

DEVELOPMENT_URL = "postgresql+psycopg://app:secret@localhost/smartcampus"
TEST_URL = "postgresql+psycopg://app:secret@localhost/smartcampus_test"


def counts(conn: Connection) -> dict[str, int]:
    return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in TABLES}


def runtime_settings(environment: str, database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        environment=environment,
        database_url=database_url,
        jwt_secret_key="x" * 32,  # mandatory outside development (SA-28)
    )


def seed_guard():
    guard = getattr(seed, "ensure_seed_allowed", None)
    assert guard is not None
    return guard


def test_seed_refuses_non_development_environment() -> None:
    settings = runtime_settings("production", DEVELOPMENT_URL)

    with pytest.raises(RuntimeError, match="development"):
        seed_guard()(settings, allow_test_database=False)


def test_seed_test_override_requires_an_isolated_test_database() -> None:
    settings = runtime_settings("production", DEVELOPMENT_URL)

    with pytest.raises(RuntimeError, match="_test"):
        seed_guard()(settings, allow_test_database=True)


def test_seed_allows_an_explicit_isolated_test_database() -> None:
    settings = runtime_settings("production", TEST_URL)

    seed_guard()(settings, allow_test_database=True)


def test_seed_allows_development_environment() -> None:
    settings = runtime_settings("development", DEVELOPMENT_URL)

    seed_guard()(settings, allow_test_database=False)


def test_seed_is_replayable_and_covers_every_state(conn: Connection) -> None:
    seed_reference(conn)
    seed_demo(conn)
    first = counts(conn)
    seed_reference(conn)
    seed_demo(conn)
    assert counts(conn) == first  # no duplicates on a second run

    reached = set(
        conn.execute(
            text(
                "SELECT c.status::text FROM candidates c"
                " WHERE NOT EXISTS (SELECT 1 FROM applications a WHERE a.candidate_id = c.id)"
                " UNION SELECT status::text FROM applications"
            )
        ).scalars()
    )
    assert {target for _, _, target in CANDIDATES} <= reached

    # Every demo e-mail template is approved, and no document fragment is created.
    unapproved = "SELECT count(*) FROM message_templates WHERE approved_by IS NULL"
    assert conn.execute(text(unapproved)).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM document_fragments")).scalar_one() == 0


def test_reference_seed_labels_fictional_admission_requirements(conn: Connection) -> None:
    seed_reference(conn)

    requirements = conn.execute(
        text("SELECT prerequisites FROM programs WHERE admission_source_url IS NULL")
    ).scalars()

    assert all(value.startswith("DÉMO FICTIVE — ") for value in requirements)


def test_reference_seed_preserves_existing_admission_requirements(conn: Connection) -> None:
    seed_reference(conn)
    conn.execute(
        text("UPDATE programs SET prerequisites = 'Condition confirmée' WHERE code = 'IIT-PREPA'")
    )

    seed_reference(conn)

    requirement = conn.execute(
        text("SELECT prerequisites FROM programs WHERE code = 'IIT-PREPA'")
    ).scalar_one()
    assert requirement == "Condition confirmée"


def test_demo_accounts_cannot_log_in(conn: Connection) -> None:
    seed_reference(conn)
    seed_demo(conn)

    hashes = conn.execute(text("SELECT DISTINCT password_hash FROM users")).scalars().all()

    assert hashes == [seed.DEMO_PASSWORD_HASH]
    assert not seed.DEMO_PASSWORD_HASH.startswith("$")  # never a usable PHC hash


# SA-28 — demonstration accounts can log in once a demo password is configured
def test_demo_accounts_cannot_log_in_until_a_password_is_set(conn: Connection) -> None:
    from app.core.passwords import verify_password

    seed_reference(conn)
    seed_demo(conn)

    hashes = conn.execute(
        text("SELECT password_hash FROM users WHERE email LIKE '%@example.com'")
    ).scalars()

    assert not any(verify_password("n'importe-quoi", h) for h in hashes)


def test_enable_demo_login_sets_one_working_password(conn: Connection) -> None:
    from app.core.passwords import verify_password

    seed_reference(conn)
    seed_demo(conn)

    updated = seed.enable_demo_login(conn, "Demo-Password-2026")

    rows = conn.execute(text("SELECT email, password_hash FROM users")).all()
    assert updated == len(rows) == len(seed.demo_user_ids())
    assert all(verify_password("Demo-Password-2026", row.password_hash) for row in rows)
    # Replaying with another password replaces the previous one.
    seed.enable_demo_login(conn, "Autre-Password-2026")
    rows = conn.execute(text("SELECT password_hash FROM users")).all()
    assert not any(verify_password("Demo-Password-2026", row.password_hash) for row in rows)
