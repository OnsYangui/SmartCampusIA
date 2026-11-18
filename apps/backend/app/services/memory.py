"""SA-26 — Mémoire temporaire des conversations des visiteurs.

Les messages d'une session sont enregistrés, bornés (taille et nombre) et relus par l'agent
sous forme de fenêtre glissante. Ils expirent avec la session (voir services/sessions.py).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Candidate, Conversation, Message


class EmptyMessageError(ValueError):
    """Le message est vide."""


class MessageTooLongError(ValueError):
    """Le message dépasse message_max_chars."""


class MessageLimitReachedError(Exception):
    """Le visiteur a atteint session_max_messages."""


def add_message(
    db: Session,
    conversation: Conversation,
    visitor: Candidate,
    sender: str,
    content: str,
    settings: Settings,
    language: str | None = None,
) -> Message:
    """Enregistre un message ('candidate' ou 'assistant') et prolonge la session."""
    clean = content.strip()
    if not clean:
        raise EmptyMessageError("Message vide")
    if len(clean) > settings.message_max_chars:
        raise MessageTooLongError(f"Message trop long (maximum {settings.message_max_chars})")
    if sender == "candidate":
        sent = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation.id, Message.sender == "candidate")
        )
        if sent >= settings.session_max_messages:
            raise MessageLimitReachedError("Limite de messages atteinte pour cette session")

    now = datetime.now(UTC)
    message = Message(
        conversation_id=conversation.id,
        sender=sender,
        content=clean,
        language=language,
        # Horloge réelle de PostgreSQL : now() est figé pendant toute une transaction.
        created_at=func.clock_timestamp(),
    )
    db.add(message)
    conversation.last_message_at = now
    visitor.last_activity_at = now  # un visiteur actif garde sa session
    db.commit()
    db.refresh(message)
    return message


def get_context(db: Session, conversation: Conversation, settings: Settings) -> dict[str, Any]:
    """Résumé et derniers messages, dans l'ordre chronologique, au format de l'agent."""
    recent = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(settings.memory_window_messages)
    ).all()
    return {
        "summary": conversation.summary,
        "messages": [
            {"role": "user" if m.sender == "candidate" else "assistant", "content": m.content}
            for m in reversed(recent)
        ],
    }