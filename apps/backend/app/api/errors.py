"""Error bodies in the SA-5 format: {"code", "message"}, plus field details for 422."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.core.errors import ConflictError, ForbiddenError

ERROR_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
}


CONFLICT_STATES = {"23505", "23P01"}  # unique and exclusion violations


def _error(status_code: int, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": ERROR_CODES.get(status_code, "error"), "message": message},
        headers=headers,
    )


async def _http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    return _error(exc.status_code, str(exc.detail), exc.headers)


async def _conflict(_request: Request, exc: ConflictError) -> JSONResponse:
    return _error(409, str(exc))


async def _forbidden(_request: Request, exc: ForbiddenError) -> JSONResponse:
    return _error(403, str(exc))


async def _integrity_error(_request: Request, exc: IntegrityError) -> JSONResponse:
    if getattr(exc.orig, "sqlstate", None) in CONFLICT_STATES:
        return _error(409, "Conflit avec une ressource existante")
    return _error(422, "Données incohérentes avec le catalogue")


async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"code": "validation_error", "message": "Paramètres invalides", "details": details},
    )


async def _unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "message": "Erreur interne du serveur"},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(ConflictError, _conflict)
    app.add_exception_handler(ForbiddenError, _forbidden)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.add_exception_handler(Exception, _unexpected_error)
