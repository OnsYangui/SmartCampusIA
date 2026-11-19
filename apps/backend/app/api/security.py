"""Authorization boundary of the API (SA-28, SA-5).

`get_principal` reads the access-token cookie and rebuilds who is acting. The role and the
institution come from the signed token, never from the request. Every request that changes data
must also repeat the CSRF token in the X-CSRF-Token header.

Protect a route with `PrincipalDep` (any signed-in account) or with `require_roles(...)`:

    @router.get("/stats/pending", dependencies=[Depends(require_roles(MANAGEMENT))])
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.api.cookies import ACCESS_COOKIE, CSRF_HEADER
from app.core.config import Settings, get_settings
from app.core.security import ROLES, Principal
from app.core.tokens import InvalidTokenError, csrf_matches, decode_token

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_principal(request: Request, settings: SettingsDep) -> Principal:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    try:
        claims = decode_token(settings, token, "access")
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée ou invalide") from None

    if request.method not in SAFE_METHODS and not csrf_matches(
        settings, claims.session_id, request.headers.get(CSRF_HEADER)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Jeton CSRF absent ou invalide")
    return claims.principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Dependency that lets only the given roles through (403 for the others)."""
    allowed = frozenset(roles)
    if not allowed or not allowed <= ROLES:
        raise ValueError(f"Rôles inconnus : {sorted(allowed - ROLES)}")

    def dependency(principal: PrincipalDep) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Rôle non autorisé pour cette action")
        return principal

    return dependency


def require_catalog_manager(principal: PrincipalDep) -> Principal:
    if not principal.manages_catalog:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé aux responsables académiques et administrateurs"
        )
    return principal


CatalogManagerDep = Annotated[Principal, Depends(require_catalog_manager)]

__all__ = [
    "CatalogManagerDep",
    "Principal",
    "PrincipalDep",
    "SettingsDep",
    "get_principal",
    "require_catalog_manager",
    "require_roles",
]
