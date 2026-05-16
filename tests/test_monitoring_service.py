"""Unit tests for live monitoring runtime state management."""

from __future__ import annotations

from app.services.monitoring_service import MonitoringService
from tests.support import build_test_principal, build_test_settings


def test_monitoring_service_tracks_task_lifecycle_and_sessions():
    settings = build_test_settings()
    service = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice", email="alice@example.org")

    service.record_request_started(
        request_id="req-1",
        method="POST",
        path="/api/v1/execute_task",
        client_host="127.0.0.1",
    )
    service.record_principal_resolved(request_id="req-1", principal=principal)
    service.record_task_started(
        request_id="req-1",
        session_id="session-A",
        principal=principal,
        task_description="Summarize the project and write a short report.",
        model="gpt-5.4",
    )
    service.record_workspace_event(
        request_id="req-1",
        session_id="session-A",
        workspace_path="/tmp/sessions/session-A",
        created=True,
    )

    running_snapshot = service.snapshot()
    assert running_snapshot.active_task_count == 1
    assert running_snapshot.active_tasks[0].session_id == "session-A"
    assert running_snapshot.active_tasks[0].workspace_state == "created"
    assert running_snapshot.sessions[0].active_task_count == 1

    service.record_task_completed(request_id="req-1", duration_ms=42, result_length=123)

    completed_snapshot = service.snapshot()
    assert completed_snapshot.active_task_count == 0
    assert completed_snapshot.recent_tasks[0].status == "completed"
    assert completed_snapshot.recent_tasks[0].duration_ms == 42
    assert completed_snapshot.sessions[0].status == "idle"
    assert completed_snapshot.recent_events[0].event_type == "task_completed"


def test_monitoring_service_rotates_recent_history():
    settings = build_test_settings(monitoring_history_size=10)
    service = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice")

    for index in range(12):
        request_id = f"req-{index}"
        service.record_task_started(
            request_id=request_id,
            session_id=f"session-{index}",
            principal=principal,
            task_description="Task",
            model="gpt-5.4",
        )
        service.record_task_failed(
            request_id=request_id,
            error_type="RuntimeError",
            error_message="boom",
            duration_ms=index,
        )

    snapshot = service.snapshot()
    assert len(snapshot.recent_tasks) == 10
    assert snapshot.recent_tasks[0].request_id == "req-11"
    assert snapshot.recent_tasks[-1].request_id == "req-2"


def test_monitoring_service_records_failures_with_error_details():
    settings = build_test_settings()
    service = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice")

    service.record_task_started(
        request_id="req-fail",
        session_id="session-fail",
        principal=principal,
        task_description="Do something risky",
        model="gpt-5.4",
    )
    service.record_task_failed(
        request_id="req-fail",
        error_type="RuntimeError",
        error_message="boom",
        duration_ms=9,
    )

    snapshot = service.snapshot()
    assert snapshot.recent_tasks[0].status == "failed"
    assert snapshot.recent_tasks[0].error_type == "RuntimeError"
    assert snapshot.recent_tasks[0].error_message == "boom"
    assert snapshot.recent_events[0].event_type == "task_failed"


def test_monitoring_service_disabled_mode_suppresses_runtime_state():
    settings = build_test_settings(monitoring_enabled=False)
    service = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice")

    service.record_request_started(
        request_id="req-disabled",
        method="POST",
        path="/api/v1/execute_task",
        client_host="127.0.0.1",
    )
    service.record_task_started(
        request_id="req-disabled",
        session_id="session-disabled",
        principal=principal,
        task_description="Ignored task",
        model="gpt-5.4",
    )

    snapshot = service.snapshot()
    assert snapshot.status == "disabled"
    assert snapshot.active_task_count == 0
    assert snapshot.recent_tasks == []
    assert service.latest_event_id() == 0


def test_monitoring_service_events_after_and_latest_event_id():
    settings = build_test_settings()
    service = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice")

    service.record_request_started(
        request_id="req-1",
        method="GET",
        path="/api/v1/health/live",
        client_host="127.0.0.1",
    )
    service.record_task_started(
        request_id="req-2",
        session_id="session-2",
        principal=principal,
        task_description="Task",
        model="gpt-5.4",
    )

    latest = service.latest_event_id()
    events = service.events_after(1)

    assert latest >= 2
    assert [event.event_type for event in events] == ["task_started"]


def test_monitoring_service_prunes_old_idle_sessions():
    settings = build_test_settings(monitoring_history_size=10)
    service = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice")

    for index in range(105):
        request_id = f"req-{index}"
        session_id = f"session-{index}"
        service.record_task_started(
            request_id=request_id,
            session_id=session_id,
            principal=principal,
            task_description="Task",
            model="gpt-5.4",
        )
        service.record_task_completed(
            request_id=request_id, duration_ms=index, result_length=2
        )

    snapshot = service.snapshot()
    session_ids = {session.session_id for session in snapshot.sessions}

    assert snapshot.session_count == 100
    assert "session-0" not in session_ids
    assert "session-104" in session_ids
