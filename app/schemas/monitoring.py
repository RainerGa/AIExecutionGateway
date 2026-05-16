"""Schemas for live runtime monitoring and admin observability views."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class MonitoringEvent(BaseModel):
    """One structured runtime event emitted by the monitoring subsystem.

    Attributes:
        event_id: Monotonically increasing ID for stream synchronization.
        event_type: Category of the event (e.g., "task_started").
        occurred_at: UTC timestamp of the event.
        request_id: Optional correlation ID.
        session_id: Optional session ID.
        username: Optional username of the actor.
        status: Optional status related to the event.
        message: Human-readable event description.
        details: Structured technical details.
    """

    event_id: int
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str | None = None
    session_id: str | None = None
    username: str | None = None
    status: str | None = None
    message: str
    details: dict[str, str | int | bool | None] = Field(default_factory=dict)


class TaskRuntimeRecord(BaseModel):
    """Current or recently completed task execution state.

    Attributes:
        request_id: Unique correlation ID.
        session_id: Session identifier.
        username: Actor username.
        email: Actor email.
        auth_mode: Authentication method used.
        roles: User roles at the time of execution.
        status: Execution status ("running", "completed", "failed").
        started_at: When the task was received.
        last_updated_at: Last heartbeat or state transition.
        completed_at: When the task finished.
        task_length: Length of the task description.
        task_preview: Truncated preview of the task.
        model: Model identifier.
        workspace_path: Absolute path to the session workspace.
        workspace_state: Workspace status ("created" or "reused").
        duration_ms: Total execution time.
        result_length: Length of the generated result.
        error_type: Type of error if failed.
        error_message: Detailed error message if failed.
    """

    request_id: str
    session_id: str
    username: str
    email: str | None = None
    auth_mode: str
    roles: tuple[str, ...] = ()
    status: str
    started_at: datetime
    last_updated_at: datetime
    completed_at: datetime | None = None
    task_length: int
    task_preview: str
    model: str
    workspace_path: str | None = None
    workspace_state: str | None = None
    duration_ms: int | None = None
    result_length: int | None = None
    error_type: str | None = None
    error_message: str | None = None


class SessionRuntimeRecord(BaseModel):
    """Aggregated monitoring data for one logical session workspace.

    Attributes:
        session_id: The session identifier.
        username: The primary user of this session.
        email: User email.
        workspace_path: Path to the workspace on disk.
        created_at: When the session was first seen.
        last_activity_at: When the last task was started or completed.
        active_task_count: Number of currently running tasks in this session.
        last_request_id: ID of the most recent request.
        status: Session status ("active" or "idle").
    """

    session_id: str
    username: str
    email: str | None = None
    workspace_path: str | None = None
    created_at: datetime
    last_activity_at: datetime
    active_task_count: int
    last_request_id: str | None = None
    status: str


class MonitoringSnapshot(BaseModel):
    """Current runtime snapshot for the admin monitoring UI.

    Attributes:
        generated_at: UTC timestamp of the snapshot.
        status: Global monitoring status ("up" or "disabled").
        active_task_count: Total number of running tasks across all sessions.
        session_count: Total number of tracked sessions.
        history_size: Configured memory retention limit.
        active_tasks: List of currently running tasks.
        recent_tasks: List of recently completed tasks.
        sessions: List of tracked sessions.
        recent_events: Tail of the event log.
    """

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str
    active_task_count: int
    session_count: int
    history_size: int
    active_tasks: list[TaskRuntimeRecord] = Field(default_factory=list)
    recent_tasks: list[TaskRuntimeRecord] = Field(default_factory=list)
    sessions: list[SessionRuntimeRecord] = Field(default_factory=list)
    recent_events: list[MonitoringEvent] = Field(default_factory=list)
