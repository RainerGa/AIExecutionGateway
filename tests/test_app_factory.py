"""Unit tests for application factory wiring and published routes."""

from __future__ import annotations

from app.core.config import get_settings
from app.main import create_application
from app.services.monitoring_service import MonitoringService
from tests.support import build_test_settings


def test_create_application_registers_monitoring_service_and_route_set():
    settings = build_test_settings(auth_mode="disabled")

    app = create_application(settings=settings)
    route_paths = {route.path for route in app.routes}

    assert isinstance(app.state.monitoring_service, MonitoringService)
    assert app.dependency_overrides[get_settings]() is settings
    assert "/" in route_paths
    assert "/api/v1/execute_task" in route_paths
    assert "/api/v1/health/live" in route_paths
    assert "/api/v1/monitoring/snapshot" in route_paths
    assert "/api/v1/monitoring/events" in route_paths


def test_create_application_respects_disabled_docs_settings():
    settings = build_test_settings(enable_docs=False)

    app = create_application(settings=settings)

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
