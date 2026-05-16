"""Unit tests for FastAPI dependency helpers and monitoring wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.dependencies import (
    get_codex_execution_service,
    get_current_principal,
    get_monitoring_service,
    get_request_id,
    require_admin_principal,
    require_task_execution_principal,
)
from app.services.monitoring_service import MonitoringService
from tests.support import build_test_principal, build_test_settings


def _build_request():
    settings = build_test_settings()
    monitoring = MonitoringService(settings.monitoring)
    request = MagicMock()
    request.state = SimpleNamespace(request_id="req-1")
    request.app.state.monitoring_service = monitoring
    return request, settings, monitoring


def test_get_monitoring_service_returns_process_singleton():
    request, _, monitoring = _build_request()

    assert get_monitoring_service(request) is monitoring


def test_get_request_id_returns_state_value_or_dash():
    request, _, _ = _build_request()

    assert get_request_id(request) == "req-1"
    assert get_request_id(SimpleNamespace(state=SimpleNamespace())) == "-"


def test_get_codex_execution_service_uses_app_monitoring_service():
    request, settings, monitoring = _build_request()

    service = get_codex_execution_service(request=request, settings=settings)

    assert service.settings is settings
    assert service.monitoring_service is monitoring


def test_get_current_principal_caches_and_records_monitoring_event():
    request, _, monitoring = _build_request()
    principal = build_test_principal(username="alice", email="alice@example.org")
    auth_service = MagicMock()
    auth_service.resolve_principal.return_value = principal

    first = get_current_principal(
        request, auth_service=auth_service, monitoring_service=monitoring
    )
    second = get_current_principal(
        request, auth_service=auth_service, monitoring_service=monitoring
    )

    assert first == principal
    assert second == principal
    auth_service.resolve_principal.assert_called_once_with(request)
    assert monitoring.snapshot().recent_events[0].event_type == "principal_resolved"


def test_get_current_principal_does_not_record_event_for_missing_principal():
    request, _, monitoring = _build_request()
    auth_service = MagicMock()
    auth_service.resolve_principal.return_value = None

    principal = get_current_principal(
        request, auth_service=auth_service, monitoring_service=monitoring
    )

    assert principal is None
    assert monitoring.latest_event_id() == 0


def test_require_task_execution_principal_delegates_to_auth_service():
    principal = build_test_principal(username="alice")
    auth_service = MagicMock()
    auth_service.require_execute_task_access.return_value = principal

    result = require_task_execution_principal(
        principal=principal, auth_service=auth_service
    )

    assert result == principal
    auth_service.require_execute_task_access.assert_called_once_with(principal)


def test_require_admin_principal_delegates_to_auth_service():
    principal = build_test_principal(username="alice")
    auth_service = MagicMock()
    auth_service.require_admin_access.return_value = principal

    result = require_admin_principal(principal=principal, auth_service=auth_service)

    assert result == principal
    auth_service.require_admin_access.assert_called_once_with(principal)
