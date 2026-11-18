"""SA-28 — account creation rules shared by the command line and future user management."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.passwords import verify_password
from app.services import auth


def test_create_user_hashes_the_password_and_normalises_the_email(conn, catalog) -> None:
    with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
        user = auth.create_user(
            session, email="  Admin@Example.com ", password="Un-mot-de-passe-42", role="admin"
        )

        assert user.email == "admin@example.com"
        assert user.password_hash != "Un-mot-de-passe-42"
        assert verify_password("Un-mot-de-passe-42", user.password_hash)


@pytest.mark.parametrize(
    ("role", "with_institution"),
    [
        ("academic_manager", False),
        ("interview_manager", False),
        ("admin", True),
        ("management", True),
        ("candidate", True),
        ("root", False),
    ],
)
def test_create_user_refuses_inconsistent_accounts(conn, catalog, role, with_institution) -> None:
    institution = catalog["iit"] if with_institution else None

    with (
        Session(bind=conn, join_transaction_mode="create_savepoint") as session,
        pytest.raises(ValueError),
    ):
        auth.create_user(
            session,
            email="x@example.com",
            password="Un-mot-de-passe-42",
            role=role,
            institution_id=institution,
        )


def test_a_manager_is_created_with_an_institution(conn, catalog) -> None:
    with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
        user = auth.create_user(
            session,
            email="resp@example.com",
            password="Un-mot-de-passe-42",
            role="academic_manager",
            institution_id=catalog["iit"],
        )

        assert isinstance(user.id, uuid.UUID)
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
