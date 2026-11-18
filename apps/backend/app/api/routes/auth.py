"""SA-28 — login, token renewal, logout and current account (SA-5 §2: /auth/*)."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.cookies import (
    CSRF_HEADER,
    REFRESH_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from app.api.security import PrincipalDep, SettingsDep
from app.core.db import SessionDep
from app.core.tokens import InvalidTokenError, csrf_matches, decode_token, new_session_id
from app.models import User
from app.schemas.auth import LoginIn, UserOut
from app.services import auth

router = APIRouter(prefix="/auth", tags=["authentication"])

# One message for every cause (unknown e-mail, wrong password, disabled account).
BAD_CREDENTIALS = "E-mail ou mot de passe incorrect"


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, role=user.role, institution_id=user.institution_id)


@router.post("/login")
def login(
    payload: LoginIn, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut:
    user = auth.authenticate(session, payload.email, payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
    session.commit()  # persists a password re-hash, if any
    set_session_cookies(response, settings, auth.principal_of(user), new_session_id())
    return _user_out(user)


@router.post("/refresh")
def refresh(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut:
    """New access token. The role and institution are read again from the database, so a role
    change or a disabled account takes effect at the next renewal."""
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    try:
        claims = decode_token(settings, token, "refresh")
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée ou invalide") from None
    if not csrf_matches(settings, claims.session_id, request.headers.get(CSRF_HEADER)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Jeton CSRF absent ou invalide")

    user = auth.get_active_user(session, claims.user_id)
    if user is None:
        clear_session_cookies(response, settings)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée ou invalide")
    set_session_cookies(response, settings, auth.principal_of(user), claims.session_id)
    return _user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, settings: SettingsDep) -> None:
    clear_session_cookies(response, settings)


@router.get("/me")
def me(principal: PrincipalDep, session: SessionDep) -> UserOut:
    user = auth.get_active_user(session, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée ou invalide")
    # Role and institution as the token states them: they are what authorisation uses.
    return UserOut(
        id=user.id,
        email=user.email,
        role=principal.role,
        institution_id=principal.institution_id,
    )
