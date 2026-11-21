"""SA-25 — POST /sessions ouvre une session anonyme (SA-5, BF-01).
SA-29 — POST /sessions/{id}/link rattache la session à un compte candidat.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select, update

from app.api.security import PrincipalDep
from app.api.visitor import VisitorDep
from app.core.config import Settings, get_settings
from app.core.db import SessionDep
from app.models import Candidate, Consent, Conversation
from app.services.sessions import expires_at, open_session

router = APIRouter(prefix="/sessions", tags=["sessions"])

SettingsDep = Annotated[Settings, Depends(get_settings)]

CONSENT_TEXT_VERSION = "v1"  # version du texte de consentement affiché au candidat


class SessionOut(BaseModel):
    id: uuid.UUID
    expires_at: datetime


class LinkIn(BaseModel):
    consent: bool


class LinkOut(BaseModel):
    candidate_id: uuid.UUID
    conversation_id: uuid.UUID


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(response: Response, db: SessionDep, settings: SettingsDep) -> SessionOut:
    """Ouvre une session : pose le cookie HttpOnly et renvoie l'identifiant de conversation."""
    token, visitor, conversation = open_session(db)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_lifetime_days * 86400,
        httponly=True,  # illisible par le JavaScript
        samesite="lax",
        secure=settings.environment != "development",  # HTTPS obligatoire hors développement
        path="/",
    )
    return SessionOut(id=conversation.id, expires_at=expires_at(visitor, settings))


@router.get("/{session_id}")
def read_session(
    session_id: uuid.UUID, visitor: VisitorDep, db: SessionDep, settings: SettingsDep
) -> SessionOut:
    """Vérifie qu'une session est encore valide et appartient bien au visiteur."""
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == session_id, Conversation.candidate_id == visitor.id
        )
    )
    if conversation is None:
        # 404 et non 403 : on ne révèle pas qu'une session d'un autre visiteur existe (SA-5).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session introuvable")
    return SessionOut(id=conversation.id, expires_at=expires_at(visitor, settings))


@router.post("/{session_id}/link")
def link_session(
    session_id: uuid.UUID,
    body: LinkIn,
    response: Response,
    visitor: VisitorDep,  # cookie sc_session : le visiteur anonyme
    principal: PrincipalDep,  # cookie access_token + CSRF : le compte connecté
    db: SessionDep,
    settings: SettingsDep,
) -> LinkOut:
    """SA-29 — rattache la conversation d'un visiteur au compte candidat connecté."""
    if principal.role != "candidate":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux comptes candidats")
    if not body.consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Accord explicite requis")

    # La session doit appartenir à ce visiteur (404 : on ne révèle rien sur les autres).
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == session_id, Conversation.candidate_id == visitor.id
        )
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session introuvable")

    existing = db.scalar(select(Candidate).where(Candidate.user_id == principal.user_id))
    if existing is None:
        # Premier rattachement : la fiche anonyme devient la fiche du compte.
        visitor.user_id = principal.user_id
        visitor.status = "EN_PROFILAGE"
        target = visitor
    else:
        # Le compte a déjà une fiche (nouvel appareil) : on déplace les conversations
        # puis on supprime la fiche anonyme (son Profile part avec, CASCADE).
        db.execute(
            update(Conversation)
            .where(Conversation.candidate_id == visitor.id)
            .values(candidate_id=existing.id)
        )
        db.flush()
        db.delete(visitor)
        target = existing

    db.add(
        Consent(
            candidate_id=target.id,
            text_version=CONSENT_TEXT_VERSION,
            accepted_at=datetime.now(UTC),
        )
    )
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return LinkOut(candidate_id=target.id, conversation_id=conversation.id)
