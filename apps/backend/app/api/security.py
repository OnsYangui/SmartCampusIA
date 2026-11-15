"""Authorization boundary of the API.

`get_principal` is the single integration point for SA-28 authentication (JWT cookies, SA-5).
Until it is implemented, every protected request is rejected: there is no default account.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.security import Principal


def get_principal() -> Principal:
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_catalog_manager(principal: PrincipalDep) -> Principal:
    if not principal.manages_catalog:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé aux responsables académiques et administrateurs"
        )
    return principal


CatalogManagerDep = Annotated[Principal, Depends(require_catalog_manager)]

__all__ = ["CatalogManagerDep", "Principal", "get_principal", "require_catalog_manager"]
