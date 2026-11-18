"""SA-25 — Sessions temporaires des visiteurs (conversation sans compte).

Le navigateur garde un jeton secret dans un cookie. La base ne stocke que son empreinte
SHA-256 (candidates.session_id_hash) : une fuite de la base ne permet pas de se connecter.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Candidate, Conversation


def hash_token(token: str) -> str:
    """Empreinte SHA-256 du jeton : 64 caractères, comme la colonne CHAR(64)."""
    return hashlib.sha256(token.encode()).hexdigest()


def open_session(db: Session) -> tuple[str, Candidate, Conversation]:
    """Crée un visiteur anonyme et sa conversation ; renvoie aussi le jeton brut."""
    token = secrets.token_urlsafe(32)  # identifiant unique et impossible à deviner
    visitor = Candidate(session_id_hash=hash_token(token))  # statut VISITEUR par défaut
    db.add(visitor)
    db.flush()  # génère visitor.id pour pouvoir créer la conversation
    conversation = Conversation(candidate_id=visitor.id)
    db.add(conversation)
    db.commit()
    db.refresh(visitor)
    db.refresh(conversation)
    return token, visitor, conversation


def expires_at(visitor: Candidate, settings: Settings) -> datetime:
    """Date d'expiration : la plus proche entre l'inactivité et la durée de vie maximale."""
    idle = visitor.last_activity_at + timedelta(minutes=settings.session_idle_ttl_minutes)
    hard = visitor.created_at + timedelta(days=settings.session_max_lifetime_days)
    return min(idle, hard)


def find_active_visitor(db: Session, token: str | None, settings: Settings) -> Candidate | None:
    """Renvoie le visiteur si le jeton est valide, anonyme et non expiré, sinon None."""
    if not token:
        return None
    visitor = db.scalar(
        select(Candidate).where(
            Candidate.session_id_hash == hash_token(token),
            Candidate.user_id.is_(None),  # un candidat avec compte n'est pas un visiteur
        )
    )
    if visitor is None or expires_at(visitor, settings) <= datetime.now(UTC):
        return None
    return visitor