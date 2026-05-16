"""In-memory runtime monitoring state for live admin observability."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock

from app.core.config import MonitoringSettings
from app.schemas.monitoring import (
    MonitoringEvent,
    MonitoringSnapshot,
    SessionRuntimeRecord,
    TaskRuntimeRecord,
)
from app.security.models import UserPrincipal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _preview_task(text: str, *, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


@dataclass(slots=True)
class _SessionState:
    session_id: str
    username: str
    email: str | None
    workspace_path: str | None
    created_at: datetime
    last_activity_at: datetime
    active_task_count: int
    last_request_id: str | None
    status: str


class MonitoringService:
    """Tracks live request, task, and session state for admin-facing observability.

    This service maintains an in-memory record of all active and recent
    operations. It is designed to be thread-safe using a reentrant lock.

    Attributes:
        enabled (bool): Whether the monitoring subsystem is active.
        stream_enabled (bool): Whether event streaming is enabled.
        refresh_interval_ms (int): UI refresh interval in milliseconds.
    """

    def __init__(self, settings: MonitoringSettings) -> None:
        """Initializes the monitoring service.

        Args:
            settings: The monitoring configuration settings.
        """
        self._settings = settings
        self._lock = RLock()
        self._active_tasks: dict[str, TaskRuntimeRecord] = {}
        self._recent_tasks: deque[TaskRuntimeRecord] = deque(
            maxlen=settings.history_size
        )
        self._sessions: dict[str, _SessionState] = {}
        self._session_retention_limit = max(settings.history_size, 100)
        self._events: deque[MonitoringEvent] = deque(
            maxlen=max(settings.history_size * 8, 100)
        )
        self._next_event_id = 1

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @property
    def stream_enabled(self) -> bool:
        return self._settings.stream_enabled

    @property
    def refresh_interval_ms(self) -> int:
        return self._settings.refresh_interval_ms

    def record_request_started(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        client_host: str | None,
    ) -> None:
        """Emits an event indicating that a new HTTP request has started.

        Args:
            request_id: Unique correlation ID for the request.
            method: HTTP method (e.g., GET, POST).
            path: The request URI path.
            client_host: The IP or hostname of the calling client.
        """
        self._emit(
            "request_started",
            message=f"{method} {path}",
            request_id=request_id,
            details={"method": method, "path": path, "client_host": client_host},
        )

    def record_principal_resolved(
        self,
        *,
        request_id: str,
        principal: UserPrincipal,
    ) -> None:
        """Emits an event indicating that a user principal has been authenticated.

        Args:
            request_id: Unique correlation ID for the request.
            principal: The resolved user principal.
        """
        self._emit(
            "principal_resolved",
            message=f"Principal resolved for {principal.display_name}",
            request_id=request_id,
            username=principal.username,
            details={
                "auth_mode": principal.auth_mode,
                "roles": ",".join(principal.roles),
                "email": principal.email,
            },
        )

    def record_task_started(
        self,
        *,
        request_id: str,
        session_id: str,
        principal: UserPrincipal,
        task_description: str,
        model: str,
    ) -> None:
        """Records the start of a Codex task and updates the session state.

        Args:
            request_id: Unique correlation ID for the request.
            session_id: The ID of the session the task belongs to.
            principal: The user principal performing the task.
            task_description: A description of the task being executed.
            model: The name of the model being used.
        """
        if not self.enabled:
            return
        now = _utcnow()
        record = TaskRuntimeRecord(
            request_id=request_id,
            session_id=session_id,
            username=principal.username,
            email=principal.email,
            auth_mode=principal.auth_mode,
            roles=principal.roles,
            status="running",
            started_at=now,
            last_updated_at=now,
            task_length=len(task_description),
            task_preview=_preview_task(task_description),
            model=model,
        )
        with self._lock:
            self._active_tasks[request_id] = record
            session = self._sessions.get(session_id)
            if session is None:
                session = _SessionState(
                    session_id=session_id,
                    username=principal.username,
                    email=principal.email,
                    workspace_path=None,
                    created_at=now,
                    last_activity_at=now,
                    active_task_count=0,
                    last_request_id=request_id,
                    status="active",
                )
                self._sessions[session_id] = session
            session.username = principal.username
            session.email = principal.email
            session.last_activity_at = now
            session.active_task_count += 1
            session.last_request_id = request_id
            session.status = "active"
            self._prune_idle_sessions_locked(protected_session_id=session_id)
        self._emit(
            "task_started",
            message=f"Task started for session {session_id}",
            request_id=request_id,
            session_id=session_id,
            username=principal.username,
            status="running",
            details={"task_length": len(task_description), "model": model},
        )

    def record_workspace_event(
        self,
        *,
        request_id: str,
        session_id: str,
        workspace_path: str,
        created: bool,
    ) -> None:
        """Records a workspace allocation event (creation or reuse).

        Args:
            request_id: Unique correlation ID for the request.
            session_id: The ID of the session.
            workspace_path: The absolute path to the workspace directory.
            created: True if the workspace was created, False if reused.
        """
        if not self.enabled:
            return
        now = _utcnow()
        with self._lock:
            task = self._active_tasks.get(request_id)
            if task is not None:
                task.workspace_path = workspace_path
                task.workspace_state = "created" if created else "reused"
                task.last_updated_at = now
            session = self._sessions.get(session_id)
            if session is not None:
                session.workspace_path = workspace_path
                session.last_activity_at = now
        self._emit(
            "workspace_created" if created else "workspace_reused",
            message=f"Workspace {'created' if created else 'reused'} for session {session_id}",
            request_id=request_id,
            session_id=session_id,
            status="running",
            details={"workspace_path": workspace_path},
        )

    def record_task_completed(
        self,
        *,
        request_id: str,
        duration_ms: int,
        result_length: int,
    ) -> None:
        """Records the successful completion of a task.

        Args:
            request_id: Unique correlation ID for the request.
            duration_ms: Time taken to complete the task in milliseconds.
            result_length: Length of the generated result in characters.
        """
        if not self.enabled:
            return
        self._finish_task(
            request_id=request_id,
            final_status="completed",
            duration_ms=duration_ms,
            result_length=result_length,
        )

    def record_task_failed(
        self,
        *,
        request_id: str,
        error_type: str,
        error_message: str,
        duration_ms: int | None = None,
    ) -> None:
        """Records a task failure.

        Args:
            request_id: Unique correlation ID for the request.
            error_type: A stable string identifier for the error type.
            error_message: A human-readable error message.
            duration_ms: Optional time taken before the failure occurred.
        """
        if not self.enabled:
            return
        self._finish_task(
            request_id=request_id,
            final_status="failed",
            error_type=error_type,
            error_message=error_message,
            duration_ms=duration_ms,
        )

    def snapshot(self) -> MonitoringSnapshot:
        """Creates a deep-copy snapshot of the current monitoring state.

        Returns:
            A `MonitoringSnapshot` object containing all active/recent data.
        """
        with self._lock:
            active_tasks = sorted(
                (
                    record.model_copy(deep=True)
                    for record in self._active_tasks.values()
                ),
                key=lambda item: item.started_at,
            )
            recent_tasks = list(
                reversed(
                    [record.model_copy(deep=True) for record in self._recent_tasks]
                )
            )
            sessions = sorted(
                [
                    SessionRuntimeRecord(
                        session_id=session.session_id,
                        username=session.username,
                        email=session.email,
                        workspace_path=session.workspace_path,
                        created_at=session.created_at,
                        last_activity_at=session.last_activity_at,
                        active_task_count=session.active_task_count,
                        last_request_id=session.last_request_id,
                        status=session.status,
                    )
                    for session in self._sessions.values()
                ],
                key=lambda item: item.last_activity_at,
                reverse=True,
            )
            recent_events = list(
                reversed([event.model_copy(deep=True) for event in self._events][-20:])
            )

        return MonitoringSnapshot(
            status="up" if self.enabled else "disabled",
            active_task_count=len(active_tasks),
            session_count=len(sessions),
            history_size=self._settings.history_size,
            active_tasks=active_tasks,
            recent_tasks=recent_tasks,
            sessions=sessions,
            recent_events=recent_events,
        )

    def events_after(self, event_id: int, *, limit: int = 50) -> list[MonitoringEvent]:
        """Returns a list of events that occurred after the specified ID.

        Args:
            event_id: The ID to start from (exclusive).
            limit: Maximum number of events to return.

        Returns:
            A list of matching `MonitoringEvent` objects.
        """
        with self._lock:
            return [
                event.model_copy(deep=True)
                for event in self._events
                if event.event_id > event_id
            ][:limit]

    def latest_event_id(self) -> int:
        """Returns the ID of the most recent event.

        Returns:
            The event ID, or 0 if no events exist.
        """
        with self._lock:
            return self._events[-1].event_id if self._events else 0

    def _finish_task(
        self,
        *,
        request_id: str,
        final_status: str,
        duration_ms: int | None = None,
        result_length: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Internal helper to transition a task from active to recent history.

        Args:
            request_id: Unique correlation ID for the request.
            final_status: The final status of the task ("completed" or "failed").
            duration_ms: Optional total duration of the task.
            result_length: Optional length of the result.
            error_type: Optional error type for failures.
            error_message: Optional human-readable error message.
        """
        now = _utcnow()
        with self._lock:
            task = self._active_tasks.pop(request_id, None)
            if task is None:
                return
            task.status = final_status
            task.last_updated_at = now
            task.completed_at = now
            task.duration_ms = duration_ms
            task.result_length = result_length
            task.error_type = error_type
            task.error_message = error_message
            self._recent_tasks.append(task.model_copy(deep=True))
            session = self._sessions.get(task.session_id)
            if session is not None:
                session.active_task_count = max(0, session.active_task_count - 1)
                session.last_activity_at = now
                session.last_request_id = request_id
                session.status = "active" if session.active_task_count else "idle"
            self._prune_idle_sessions_locked(protected_session_id=task.session_id)

        self._emit(
            "task_completed" if final_status == "completed" else "task_failed",
            message=f"Task {final_status} for session {task.session_id}",
            request_id=request_id,
            session_id=task.session_id,
            username=task.username,
            status=final_status,
            details={
                "duration_ms": duration_ms,
                "result_length": result_length,
                "error_type": error_type,
                "error_message": error_message,
            },
        )

    def _emit(
        self,
        event_type: str,
        *,
        message: str,
        request_id: str | None = None,
        session_id: str | None = None,
        username: str | None = None,
        status: str | None = None,
        details: dict[str, str | int | bool | None] | None = None,
    ) -> None:
        """Appends a new event to the internal event log.

        Args:
            event_type: The category of the event.
            message: A human-readable description of the event.
            request_id: Optional correlation ID.
            session_id: Optional session ID.
            username: Optional username.
            status: Optional task/request status.
            details: Optional structured details.
        """
        if not self.enabled:
            return
        with self._lock:
            event = MonitoringEvent(
                event_id=self._next_event_id,
                event_type=event_type,
                request_id=request_id,
                session_id=session_id,
                username=username,
                status=status,
                message=message,
                details=details or {},
            )
            self._next_event_id += 1
            self._events.append(event)

    def _prune_idle_sessions_locked(
        self, *, protected_session_id: str | None = None
    ) -> None:
        """Keeps the monitoring session map bounded without evicting active sessions.

        This method must be called while holding `self._lock`.

        Args:
            protected_session_id: An optional session ID that should not be
                pruned even if it is idle (e.g., the session currently being updated).
        """
        overflow = len(self._sessions) - self._session_retention_limit
        if overflow <= 0:
            return

        idle_session_ids = [
            session_id
            for session_id, session in sorted(
                self._sessions.items(),
                key=lambda item: item[1].last_activity_at,
            )
            if session.active_task_count == 0 and session_id != protected_session_id
        ]
        for session_id in idle_session_ids[:overflow]:
            self._sessions.pop(session_id, None)
