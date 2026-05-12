"""Tests for the liveness and readiness endpoint functions."""

from __future__ import annotations

import asyncio

from app.api.v1.endpoints.health import read_liveness, read_readiness
from tests.support import build_test_settings


class StubHealthService:
    """Simple readiness stub that returns deterministic component states."""

    def __init__(self, component_status: str) -> None:
        self.component_status = component_status

    def readiness_components(self):
        return [
            {
                "name": "api",
                "status": "up",
                "details": "Environment=test",
            },
            {
                "name": "codex_runtime",
                "status": self.component_status,
                "details": "Test component",
            },
        ]


class StubAuthenticationService:
    """Simple auth readiness stub that returns deterministic component states."""

    def __init__(self, component_status: str) -> None:
        self.component_status = component_status

    def readiness_components(self):
        return [
            {
                "name": "authentication",
                "status": self.component_status,
                "details": "Test authentication component",
            }
        ]


def test_read_liveness_reports_up():
    """Liveness should always report the process as available."""
    response = asyncio.run(read_liveness(settings=build_test_settings()))
    assert response.status == "up"
    assert response.environment == "test"


def test_read_readiness_reports_up_when_all_components_are_up():
    """Readiness should report up when every dependency is ready."""
    response = asyncio.run(
        read_readiness(
            settings=build_test_settings(),
            service=StubHealthService(component_status="up"),
            auth_service=StubAuthenticationService(component_status="up"),
        )
    )

    assert response.status == "up"
    assert len(response.components) == 3


def test_read_readiness_reports_degraded_when_dependency_is_down():
    """Readiness should degrade when a required subsystem is unavailable."""
    response = asyncio.run(
        read_readiness(
            settings=build_test_settings(),
            service=StubHealthService(component_status="down"),
            auth_service=StubAuthenticationService(component_status="up"),
        )
    )

    assert response.status == "degraded"
