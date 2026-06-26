"""Consistent JSON error shape and exception handlers.

Every error response is: { "error": { "code", "message" } } with the correlation
id echoed in the X-Correlation-ID header. Domain code raises AppError subclasses;
the registered handlers translate them. No stack traces or engine details leak.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .correlation import CORRELATION_HEADER, get_correlation_id
from .logging import get_logger

logger = get_logger("orchestrator.errors")


class AppError(Exception):
    """Base for domain errors with a stable machine code and HTTP status."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class EngineError(AppError):
    """An internal engine failed; surfaced to the client without engine details."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "engine_unavailable"


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    headers = {}
    cid = get_correlation_id()
    if cid:
        headers[CORRELATION_HEADER] = cid
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
        }.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else code
        return _error_response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "Request validation failed.",
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Log full context server-side; return an opaque message to the client.
        logger.exception("unhandled_exception", extra={"error_type": type(exc).__name__})
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred.",
        )
