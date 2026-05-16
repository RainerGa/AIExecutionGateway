"""Central registration of structured exception handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import ApplicationError
from app.schemas.errors import ErrorDetail, ErrorResponse

LOGGER = logging.getLogger(__name__)


def _request_id_from_request(request: Request) -> str:
    """Return the correlation id from request state or a safe fallback."""
    return getattr(request.state, "request_id", "-")


async def handle_application_error(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    """Convert controlled application exceptions into stable JSON responses."""
    payload = ErrorResponse(
        error=ErrorDetail(
            code=exc.error_code,
            message=exc.message,
            request_id=_request_id_from_request(request),
            details=exc.details,
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
        headers=exc.headers,
    )


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return structured validation errors without leaking framework internals."""
    payload = ErrorResponse(
        error=ErrorDetail(
            code="request_validation_error",
            message="The request payload is invalid.",
            request_id=_request_id_from_request(request),
            details=str(exc),
        )
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


async def handle_unexpected_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Log and mask unhandled exceptions behind a stable 500 response."""
    LOGGER.exception("Unhandled application exception: %s", exc)
    payload = ErrorResponse(
        error=ErrorDetail(
            code="internal_server_error",
            message="An unexpected internal server error occurred.",
            request_id=_request_id_from_request(request),
        )
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all shared exception handlers to the FastAPI application."""
    app.add_exception_handler(ApplicationError, handle_application_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_unexpected_error)
