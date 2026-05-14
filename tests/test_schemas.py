"""Tests for Pydantic schema validation and normalization logic."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.codex import TaskExecutionRequest


def test_task_request_accepts_valid_input():
    """Request should be valid with a standard task description."""
    request = TaskExecutionRequest(task_description="Execute this task.")
    assert request.task_description == "Execute this task."


def test_task_request_trims_whitespace():
    """Request should trim leading and trailing whitespace from the description."""
    request = TaskExecutionRequest(task_description="   padded task   ")
    assert request.task_description == "padded task"


def test_task_request_rejects_empty_string():
    """Request should fail validation for an empty task description."""
    with pytest.raises(ValidationError) as exc_info:
        TaskExecutionRequest(task_description="")
    assert "at least 1 character" in str(exc_info.value)


def test_task_request_rejects_whitespace_only():
    """Request should fail validation if description becomes empty after trimming."""
    with pytest.raises(ValueError) as exc_info:
        TaskExecutionRequest(task_description="   ")
    assert "must not be blank" in str(exc_info.value)


def test_task_request_enforces_max_length():
    """Request should reject descriptions that exceed the 10,000 character limit."""
    long_task = "a" * 10001
    with pytest.raises(ValidationError) as exc_info:
        TaskExecutionRequest(task_description=long_task)
    assert "at most 10000 characters" in str(exc_info.value)


def test_task_request_accepts_valid_session_id():
    """Request should allow a valid session identifier."""
    request = TaskExecutionRequest(
        task_description="task", 
        session_id="session-42"
    )
    assert request.session_id == "session-42"


# ---------------------------------------------------------------------------
# session_id whitelist-validator security tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("invalid_id,description", [
    ("../etc",           "path traversal with leading dots"),
    ("alice/../bob",     "embedded path traversal"),
    ("..",               "bare parent directory reference"),
    ("alice/bob",        "forward slash"),
    ("/absolute",        "leading slash"),
    ("alice evil",       "space character"),
    ("alice;evil",       "semicolon"),
    ("alice\x00evil",    "null byte injection"),
    ("alice%2Fevil",     "URL-encoded slash (not decoded, but still rejected by regex)"),
    ("",                 "empty string (min_length=1)"),
    ("a" * 129,          "exceeds max length of 128"),
])
def test_session_id_rejects_unsafe_characters(invalid_id: str, description: str):
    """
    SECURITY: The session_id validator must reject all values that could
    enable path traversal, injection, or filesystem escape attacks.
    """
    with pytest.raises(ValidationError):
        TaskExecutionRequest(task_description="task", session_id=invalid_id)


@pytest.mark.parametrize("valid_id", [
    "alice",
    "session-123",
    "user_workdir",
    "MySession-42",
    "UPPER-lower_mix-42",
    "a" * 128,
])
def test_session_id_accepts_safe_characters(valid_id: str):
    """
    The session_id validator must accept all values consisting solely of
    letters, digits, hyphens, and underscores.
    """
    req = TaskExecutionRequest(task_description="task", session_id=valid_id)
    assert req.session_id == valid_id


def test_session_id_none_is_always_accepted():
    """session_id is optional; omitting it must not raise a validation error."""
    req = TaskExecutionRequest(task_description="task")
    assert req.session_id is None
