"""JWT access and refresh tokens, and the CSRF token derived from the session (SA-28, SA-5).

The access token carries the role and the institution: the backend takes them from the token,
never from the request. Both tokens share a session id (`sid`) that stays the same across
refreshes; the CSRF token is an HMAC of that id, so it cannot be forged without the server secret.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from app.core.config import Settings
from app.core.security import ROLES, Principal

ALGORITHM = "HS256"
TokenKind = Literal["access", "refresh"]


class InvalidTokenError(Exception):
    """Missing claim, bad signature, wrong kind or expired token."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    kind: TokenKind
    session_id: str
    role: str | None
    institution_id: uuid.UUID | None

    @property
    def principal(self) -> Principal:
        assert self.role is not None
        return Principal(user_id=self.user_id, role=self.role, institution_id=self.institution_id)


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


def _encode(settings: Settings, claims: dict, lifetime: timedelta, now: datetime | None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {"iat": issued_at, "exp": issued_at + lifetime, "jti": secrets.token_urlsafe(12)}
    return jwt.encode(payload | claims, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(
    settings: Settings, principal: Principal, session_id: str, *, now: datetime | None = None
) -> str:
    claims = {
        "sub": str(principal.user_id),
        "typ": "access",
        "sid": session_id,
        "role": principal.role,
        "inst": str(principal.institution_id) if principal.institution_id else None,
    }
    return _encode(settings, claims, timedelta(minutes=settings.access_token_minutes), now)


def create_refresh_token(
    settings: Settings, user_id: uuid.UUID, session_id: str, *, now: datetime | None = None
) -> str:
    claims = {"sub": str(user_id), "typ": "refresh", "sid": session_id}
    return _encode(settings, claims, timedelta(days=settings.refresh_token_days), now)


def decode_token(settings: Settings, token: str, kind: TokenKind) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],  # pinned: never trust the algorithm named by the token
            options={"require": ["exp", "iat", "sub", "typ", "sid"]},
        )
        if payload["typ"] != kind:
            raise InvalidTokenError("wrong token kind")
        user_id = uuid.UUID(payload["sub"])
        role = payload.get("role")
        institution = payload.get("inst")
        if kind == "access" and role not in ROLES:
            raise InvalidTokenError("unknown role")
        return TokenClaims(
            user_id=user_id,
            kind=kind,
            session_id=str(payload["sid"]),
            role=role,
            institution_id=uuid.UUID(institution) if institution else None,
        )
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise InvalidTokenError(str(error)) from error


def csrf_token_for(settings: Settings, session_id: str) -> str:
    digest = hmac.new(
        settings.jwt_secret.encode(), f"csrf:{session_id}".encode(), hashlib.sha256
    ).hexdigest()
    return digest


def csrf_matches(settings: Settings, session_id: str, supplied: str | None) -> bool:
    if not supplied:
        return False
    return hmac.compare_digest(csrf_token_for(settings, session_id), supplied)
