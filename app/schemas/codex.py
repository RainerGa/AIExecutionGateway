"""Request and response schemas for Codex task execution operations."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

# Only alphanumeric characters, hyphens, and underscores are safe as path components.
# This prevents path traversal attacks (e.g. '../', '/', null bytes).
_SAFE_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


class TaskExecutionRequest(BaseModel):
    """Validated API contract for a single Codex task execution request."""

    task_description: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Natural-language instruction that Codex should execute.",
    )
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description=(
            "Optional identifier to isolate this execution within a user session workspace. "
            "Must consist only of letters, digits, hyphens, and underscores."
        ),
    )

    @field_validator("task_description")
    @classmethod
    def normalize_task_description(cls, value: str) -> str:
        """Reject empty or whitespace-only tasks after trimming input noise."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("task_description must not be blank.")
        return normalized

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        """Enforce a strict whitelist to prevent path traversal and injection attacks.

        Only alphanumeric characters, hyphens, and underscores are permitted.
        This blocks sequences such as '../', '/', null bytes, and encoded variants.
        """
        if value is None:
            return None
        if not _SAFE_SESSION_ID_RE.match(value):
            raise ValueError(
                "session_id must contain only letters, digits, hyphens, and underscores."
            )
        return value

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_description": (
                        "Write a Python function to calculate the factorial of a number."
                    )
                },
                {
                    "task_description": (
                        "Create a simple HTML page with a blue background and a centered heading."
                    )
                },
                {
                    "task_description": (
                        "Explain the concept of recursion in computer science in two sentences."
                    )
                },
            ]
        }
    }


class TaskExecutionMetadata(BaseModel):
    """Operational metadata returned with each completed task execution."""

    request_id: str = Field(..., description="Correlation id for tracing the request.")
    model: str = Field(
        ...,
        description="Effective model used for the run or the inherited Codex default.",
    )
    duration_ms: int = Field(..., ge=0, description="Execution time in milliseconds.")
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the completed execution.",
    )


class TaskExecutionResponse(BaseModel):
    """API response containing Codex output and operational metadata."""

    result: str = Field(..., description="Final textual response returned by Codex.")
    logs: list[str] = Field(
        default_factory=list,
        description="Reserved extension point for future execution log messages.",
    )
    metadata: TaskExecutionMetadata

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "result": (
                        "Here is a Python function to calculate the factorial of a number."
                    ),
                    "logs": [],
                    "metadata": {
                        "request_id": "c5f3e239-0c72-4e4d-baa4-e601f7df62b8",
                        "model": "gpt-5.4",
                        "duration_ms": 1840,
                        "completed_at": "2026-05-08T15:00:00Z",
                    },
                }
            ]
        }
    }
