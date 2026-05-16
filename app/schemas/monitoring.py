"""Schemas for live runtime monitoring and admin observability views."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class MonitoringEvent(BaseModel):
    """One structured runtime event emitted by the monitoring subsystem."""

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
    """Current or recently completed task execution state."""

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
    """Aggregated monitoring data for one logical session workspace."""

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
    """Current runtime snapshot for the admin monitoring UI."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str
    active_task_count: int
    session_count: int
    history_size: int
    active_tasks: list[TaskRuntimeRecord] = Field(default_factory=list)
    recent_tasks: list[TaskRuntimeRecord] = Field(default_factory=list)
    sessions: list[SessionRuntimeRecord] = Field(default_factory=list)
    recent_events: list[MonitoringEvent] = Field(default_factory=list)
