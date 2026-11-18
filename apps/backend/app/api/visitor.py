"""SA-25 — Identification du visiteur à partir du cookie de session."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.db import SessionDep
from app.models import Candidate
from app.services.sessions import find_active_visitor


def get_visitor(
    request: Request, db: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> Candidate:
    token = request.cookies.get(settings.session_cookie_name)
    visitor = find_active_visitor(db, token, settings)
    if visitor is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session absente ou expirée")
    return visitor


VisitorDep = Annotated[Candidate, Depends(get_visitor)]