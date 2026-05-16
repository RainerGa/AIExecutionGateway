"""Tests for global exception mapping and standardized error responses."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.api.error_handlers import (
    handle_application_error,
    handle_unexpected_error,
    handle_validation_error,
)
from app.core.exceptions import InvalidTaskRequestError


def test_application_error_mapping_produces_standard_json():
    """Application errors should be mapped to the documented JSON error format."""
    # app = MagicMock(spec=FastAPI)
    request = MagicMock(spec=Request)
    request.state.request_id = "error-req-1"

    exc = InvalidTaskRequestError("Detailed message", details="some detail")

    # Execute the handler
    response = asyncio.run(handle_application_error(request, exc))

    assert response.status_code == 400

    import json

    data = json.loads(response.body)

    assert "error" in data
    assert data["error"]["code"] == "invalid_task_request"
    assert data["error"]["message"] == "Detailed message"
    assert data["error"]["request_id"] == "error-req-1"
    assert data["error"]["details"] == "some detail"


def test_validation_error_mapping_includes_request_id():
    """Validation errors should also follow the standard format with correlation id."""
    request = MagicMock(spec=Request)
    request.state.request_id = "val-req-1"

    # Mocking a Pydantic validation error is complex, we just check the handler logic
    exc = MagicMock(spec=RequestValidationError)
    exc.errors.return_value = [
        {"loc": ["body", "task_description"], "msg": "field required"}
    ]

    response = asyncio.run(handle_validation_error(request, exc))

    import json

    data = json.loads(response.body)

    assert response.status_code == 422
    assert data["error"]["code"] == "request_validation_error"
    assert data["error"]["request_id"] == "val-req-1"


def test_unexpected_error_mapping_hides_details_by_default():
    """Internal server errors should use a generic message to avoid leaking internals."""
    request = MagicMock(spec=Request)
    request.state.request_id = "internal-req-1"
    exc = RuntimeError("Secret database error")

    response = asyncio.run(handle_unexpected_error(request, exc))

    import json

    data = json.loads(response.body)

    assert response.status_code == 500
    assert data["error"]["code"] == "internal_server_error"
    assert "Secret database error" not in data["error"]["message"]
    assert data["error"]["request_id"] == "internal-req-1"
