"""SA-26 — mémoire temporaire : enregistrement, limites et fenêtre de contexte."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Candidate, Conversation
from app.services.memory import (
    EmptyMessageError,
    MessageLimitReachedError,
    MessageTooLongError,
    add_message,
    get_context,
)
from app.services.sessions import open_session


@pytest.fixture
def db(conn: Connection) -> Iterator[Session]:
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def visit(db: Session) -> tuple[Candidate, Conversation]:
    _token, visitor, conversation = open_session(db)
    return visitor, conversation


def settings_with(**values: int) -> Settings:
    return get_settings().model_copy(update=values)


def test_add_message_strips_and_stores(db: Session, visit) -> None:
    visitor, conversation = visit

    message = add_message(db, conversation, visitor, "candidate", "  Bonjour  ", settings_with())

    assert message.content == "Bonjour"
    assert message.sender == "candidate"
    assert conversation.last_message_at is not None


def test_add_message_extends_the_session(db: Session, visit) -> None:
    visitor, conversation = visit
    before = visitor.last_activity_at

    add_message(db, conversation, visitor, "candidate", "Bonjour", settings_with())

    assert visitor.last_activity_at > before


def test_empty_message_is_rejected(db: Session, visit) -> None:
    visitor, conversation = visit

    with pytest.raises(EmptyMessageError):
        add_message(db, conversation, visitor, "candidate", "   ", settings_with())


def test_too_long_message_is_rejected(db: Session, visit) -> None:
    visitor, conversation = visit

    with pytest.raises(MessageTooLongError):
        add_message(
            db, conversation, visitor, "candidate", "x" * 11, settings_with(message_max_chars=10)
        )


def test_visitor_message_limit_is_enforced(db: Session, visit) -> None:
    visitor, conversation = visit
    settings = settings_with(session_max_messages=3)
    for number in range(3):
        add_message(db, conversation, visitor, "candidate", f"Question {number}", settings)

    with pytest.raises(MessageLimitReachedError):
        add_message(db, conversation, visitor, "candidate", "Une de trop", settings)

    # La réponse de l'assistant n'est pas comptée dans la limite du visiteur.
    add_message(db, conversation, visitor, "assistant", "Réponse", settings)


def test_context_keeps_only_the_recent_window_in_order(db: Session, visit) -> None:
    visitor, conversation = visit
    settings = settings_with(memory_window_messages=2)
    add_message(db, conversation, visitor, "candidate", "un", settings)
    add_message(db, conversation, visitor, "assistant", "deux", settings)
    add_message(db, conversation, visitor, "candidate", "trois", settings)
    add_message(db, conversation, visitor, "assistant", "quatre", settings)

    context = get_context(db, conversation, settings)

    assert context["messages"] == [
        {"role": "user", "content": "trois"},
        {"role": "assistant", "content": "quatre"},
    ]


def test_context_includes_the_summary(db: Session, visit) -> None:
    _visitor, conversation = visit
    conversation.summary = "Intéressé par l'informatique"
    db.commit()

    context = get_context(db, conversation, settings_with())

    assert context["summary"] == "Intéressé par l'informatique"
    assert context["messages"] == []


def test_context_is_isolated_between_visitors(db: Session, visit) -> None:
    visitor, conversation = visit
    _token, _other_visitor, other_conversation = open_session(db)
    add_message(db, conversation, visitor, "candidate", "Privé", settings_with())

    assert get_context(db, other_conversation, settings_with())["messages"] == []