"""Structured HTTP error schema for predictable enterprise integrations."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Single structured error payload returned to API clients.

    Attributes:
        code: Stable machine-readable error category.
        message: human-readable error summary.
        request_id: Correlation ID for tracing the error.
        details: Optional technical details for diagnostics.
    """

    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable error summary.")
    request_id: str = Field(..., description="Correlation id for support and tracing.")
    details: str | None = Field(
        default=None,
        description="Optional technical detail for diagnostics and integration support.",
    )


class ErrorResponse(BaseModel):
    """Envelope for all application-level HTTP error responses.

    Attributes:
        error: The structured error detail.
    """

    error: ErrorDetail
