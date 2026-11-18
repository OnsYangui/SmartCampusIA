"""Session cookies (SA-5 §1): HttpOnly, SameSite=Lax, Secure outside development.

- access_token  : short-lived JWT, sent to the whole API.
- refresh_token : longer-lived JWT, only sent to /auth/* so that it travels as rarely as possible.
- csrf_token    : the only cookie JavaScript may read; the client copies it into X-CSRF-Token.
"""

from fastapi import Response

from app.core.config import Settings
from app.core.security import Principal
from app.core.tokens import create_access_token, create_refresh_token, csrf_token_for

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def _refresh_path(settings: Settings) -> str:
    return f"{settings.api_v1_prefix}/auth"


def set_session_cookies(
    response: Response, settings: Settings, principal: Principal, session_id: str
) -> None:
    common = {"secure": settings.secure_cookies, "samesite": "lax"}
    response.set_cookie(
        ACCESS_COOKIE,
        create_access_token(settings, principal, session_id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        path="/",
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        create_refresh_token(settings, principal.user_id, session_id),
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        path=_refresh_path(settings),
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token_for(settings, session_id),
        max_age=settings.refresh_token_days * 86400,
        httponly=False,
        path="/",
        **common,
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=_refresh_path(settings))
    response.delete_cookie(CSRF_COOKIE, path="/")
