"""SA-25 — POST /sessions ouvre une session anonyme (SA-5, BF-01)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.visitor import VisitorDep
from app.core.config import Settings, get_settings
from app.core.db import SessionDep
from app.models import Conversation
from app.services.sessions import expires_at, open_session

router = APIRouter(prefix="/sessions", tags=["sessions"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class SessionOut(BaseModel):
    id: uuid.UUID
    expires_at: datetime


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
