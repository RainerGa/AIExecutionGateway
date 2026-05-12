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


def test_task_request_rejects_long_session_id():
    """Request should reject session identifiers exceeding the length limit."""
    long_id = "s" * 129
    with pytest.raises(ValidationError):
        TaskExecutionRequest(task_description="task", session_id=long_id)
