"""SA-28 — authentication of accounts (the users table of SA-13)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.passwords import burn_time, hash_password, needs_rehash, verify_password
from app.core.security import INSTITUTION_ROLES, ROLES, Principal
from app.models import User


def find_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(func.lower(User.email) == email.lower()))


def authenticate(session: Session, email: str, password: str) -> User | None:
    """The account when e-mail and password match and the account is active, otherwise None.

    The same time is spent whatever the reason of the failure, and the caller gives one single
    message for all of them.
    """
    user = find_by_email(session, email)
    if user is None:
        burn_time()
        return None

    password_ok = verify_password(password, user.password_hash)
    if not (password_ok and user.is_active):
        return None

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        session.flush()
    return user


def get_active_user(session: Session, user_id: uuid.UUID) -> User | None:
    user = session.get(User, user_id)
    return user if user is not None and user.is_active else None


def principal_of(user: User) -> Principal:
    return Principal(user_id=user.id, role=user.role, institution_id=user.institution_id)


def validate_account(role: str, institution_id: uuid.UUID | None) -> None:
    """Same rule as the `institution_scope` constraint, with a readable message."""
    if role not in ROLES:
        raise ValueError(f"Rôle inconnu : {role}")
    if (role in INSTITUTION_ROLES) != (institution_id is not None):
        raise ValueError(
            "Un responsable académique ou entretien doit être rattaché à un établissement ; "
            "les autres rôles ne le sont pas."
        )


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
    role: str,
    institution_id: uuid.UUID | None = None,
) -> User:
    validate_account(role, institution_id)
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role,
        institution_id=institution_id,
    )
    session.add(user)
    session.flush()
    return user
