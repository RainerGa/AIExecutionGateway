"""Tests for admin monitoring endpoints and terminal helper parsing."""

from __future__ import annotations

import asyncio

from app.api.v1.endpoints.monitoring import (
    read_monitoring_snapshot,
    stream_monitoring_events,
)
from app.core.exceptions import AuthorizationDeniedError
from app.security.authentication import AuthenticationService
from app.services.monitoring_service import MonitoringService
from monitor_live import build_headers, parse_sse_block
from tests.support import build_test_principal, build_test_settings


def test_monitoring_snapshot_endpoint_returns_live_data():
    settings = build_test_settings(auth_mode="disabled")
    monitoring = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice")
    monitoring.record_task_started(
        request_id="req-1",
        session_id="monitor-session",
        principal=principal,
        task_description="Generate report",
        model="gpt-5.4",
    )
    monitoring.record_task_completed(
        request_id="req-1", duration_ms=10, result_length=2
    )

    snapshot = asyncio.run(
        read_monitoring_snapshot(_=principal, monitoring_service=monitoring)
    )
    assert snapshot.active_task_count == 0
    assert snapshot.recent_tasks[0].session_id == "monitor-session"
    assert snapshot.recent_events[0].event_type == "task_completed"


def test_monitoring_snapshot_endpoint_denies_non_admin():
    settings = build_test_settings(
        auth_mode="trusted_header",
        authorization_enabled=True,
        user_groups=("Codex-Users",),
    )
    service = AuthenticationService(settings)
    principal = build_test_principal(
        username="bob",
        auth_mode="trusted_header",
        roles=("user",),
    )
    try:
        service.require_admin_access(principal)
    except AuthorizationDeniedError:
        pass
    else:
        raise AssertionError("Expected admin access check to deny non-admin user.")


def test_monitoring_events_stream_emits_live_events():
    settings = build_test_settings()
    monitoring = MonitoringService(settings.monitoring)
    principal = build_test_principal(username="alice")
    monitoring.record_task_started(
        request_id="req-stream",
        session_id="stream-session",
        principal=principal,
        task_description="Trigger stream",
        model="gpt-5.4",
    )

    response = asyncio.run(
        stream_monitoring_events(
            monitoring_service=monitoring,
            _=principal,
            last_event_id=0,
        )
    )
    first_chunk = asyncio.run(response.body_iterator.__anext__())

    assert "event: task_started" in first_chunk
    assert "stream-session" in first_chunk


def test_parse_sse_block_and_header_builder():
    event_id, event_type, payload = parse_sse_block(
        'id: 7\nevent: task_completed\ndata: {"status":"completed"}\n\n'
    )

    assert event_id == 7
    assert event_type == "task_completed"
    assert payload == '{"status":"completed"}'

    headers = build_headers("secret", ["X-Authenticated-User=alice"])
    assert headers["Authorization"] == "Bearer secret"
    assert headers["X-Authenticated-User"] == "alice"
