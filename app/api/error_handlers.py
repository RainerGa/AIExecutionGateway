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
    """Returns the correlation ID from the request state or a safe fallback.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The request ID string or "-" if not found.
    """
    return getattr(request.state, "request_id", "-")


async def handle_application_error(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    """Converts controlled application exceptions into stable JSON responses.

    This handler processes all exceptions that inherit from `ApplicationError`,
    ensuring they are returned with the correct status code and a structured
    error payload.

    Args:
        request: The incoming FastAPI request.
        exc: The caught application-specific exception.

    Returns:
        A JSONResponse containing the structured error detail.
    """
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
    """Returns structured validation errors without leaking framework internals.

    This handler overrides the default FastAPI validation error response to
    match the application's global error format.

    Args:
        request: The incoming FastAPI request.
        exc: The validation error raised by FastAPI/Pydantic.

    Returns:
        A JSONResponse with status 422 and a structured error payload.
    """
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
    """Logs and masks unhandled exceptions behind a stable 500 response.

    This is the final safety net for any exception not explicitly handled.
    It logs the full stack trace but returns a generic error message to
    the client to prevent information leakage.

    Args:
        request: The incoming FastAPI request.
        exc: The unhandled exception.

    Returns:
        A JSONResponse with status 500 and a generic error payload.
    """
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
    """Attaches all shared exception handlers to the FastAPI application.

    Args:
        app: The FastAPI application instance to configure.
    """
    app.add_exception_handler(ApplicationError, handle_application_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_unexpected_error)
