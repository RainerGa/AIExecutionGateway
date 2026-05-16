"""Deep integration tests for the full HTTP request lifecycle.

These tests verify the interaction between FastAPI, Middleware,
Dependency Injection, and Service logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import threading

from fastapi import Request
from fastapi.testclient import TestClient

from app.main import create_application
from app.api.dependencies import get_current_principal
from tests.support import build_test_settings


def test_request_id_propagation_cycle():
    """
    DEEP TEST: Verifies that a Request ID provided by the client:
    1. Is adopted by the middleware.
    2. Is accessible in the service layer (via contextvars/dependency).
    3. Is returned in the final HTTP response headers.
    4. Is present in the JSON response body metadata.
    """
    settings = build_test_settings(auth_mode="disabled")
    app = create_application(settings=settings)
    client = TestClient(app)

    # We mock the Codex SDK to isolate the API logic
    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="Integration success")

        response = client.post(
            "/api/v1/execute_task",
            json={"task_description": "Integration test"},
            headers={"X-Request-ID": "external-correlation-id"},
        )

    assert response.status_code == 200

    # 1. Header propagation
    assert response.headers["X-Request-ID"] == "external-correlation-id"

    # 2. Body propagation (Metadata)
    data = response.json()
    assert data["metadata"]["request_id"] == "external-correlation-id"
    assert data["result"] == "Integration success"


def test_full_auth_flow_trusted_header_integration():
    """
    DEEP TEST: Verifies the entire security chain:
    Request -> Middleware -> Security Dependency -> Role Check -> Service.
    """
    settings = build_test_settings(
        auth_mode="trusted_header",
        authorization_enabled=True,
        execute_task_roles=["admin"],
        admin_groups=["SystemAdmins"],
    )
    app = create_application(settings=settings)
    client = TestClient(app)

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="Authorized")

        # CASE A: Missing Headers -> 401
        resp_401 = client.post("/api/v1/execute_task", json={"task_description": "..."})
        assert resp_401.status_code == 401

        # CASE B: Wrong Role -> 403
        resp_403 = client.post(
            "/api/v1/execute_task",
            json={"task_description": "..."},
            headers={"X-Authenticated-User": "bob", "X-Authenticated-Groups": "Users"},
        )
        assert resp_403.status_code == 403

        # CASE C: Correct Role -> 200
        resp_200 = client.post(
            "/api/v1/execute_task",
            json={"task_description": "..."},
            headers={
                "X-Authenticated-User": "alice",
                "X-Authenticated-Groups": "SystemAdmins",
            },
        )
        assert resp_200.status_code == 200
        assert resp_200.json()["result"] == "Authorized"


def test_health_ready_check_integrates_auth_status():
    """
    DEEP TEST: Readiness probe should reflect the actual state of
    configuration and dependencies.
    """
    settings = build_test_settings(auth_mode="oidc_jwt")
    # OIDC is configured in build_test_settings but let's break it by
    # mocking PyJWT missing
    app = create_application(settings=settings)
    client = TestClient(app)

    with patch(
        "app.security.authentication.importlib.util.find_spec", return_value=None
    ):
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"

    auth_comp = next(c for c in data["components"] if c["name"] == "authentication")
    assert auth_comp["status"] == "down"
    assert "PyJWT is not installed" in auth_comp["details"]


def test_app_lifespan_and_root_endpoint():
    """Test the application startup/shutdown lifespan and the root endpoint."""
    settings = build_test_settings(auth_mode="disabled")
    app = create_application(settings=settings)

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 204


def test_monitoring_snapshot_shows_active_task_during_execution():
    settings = build_test_settings(auth_mode="disabled")
    app = create_application(settings=settings)
    client = TestClient(app)
    task_started = threading.Event()
    release_task = threading.Event()

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread

        def slow_run(_: str):
            task_started.set()
            release_task.wait(timeout=2)
            return MagicMock(final_response="done")

        mock_thread.run.side_effect = slow_run

        response_holder: dict[str, object] = {}

        def execute_request():
            response_holder["response"] = client.post(
                "/api/v1/execute_task",
                json={"task_description": "Long task", "session_id": "live-session"},
            )

        worker = threading.Thread(target=execute_request, daemon=True)
        worker.start()
        assert task_started.wait(timeout=1)

        snapshot = client.get("/api/v1/monitoring/snapshot")
        assert snapshot.status_code == 200
        data = snapshot.json()
        assert data["active_task_count"] == 1
        assert data["active_tasks"][0]["session_id"] == "live-session"

        release_task.set()
        worker.join(timeout=2)

    assert response_holder["response"].status_code == 200


def test_principal_cache_hit():
    """Verify that get_current_principal caches the principal on the request state."""
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    # explicitly clear state
    if hasattr(request.state, "_principal_cache"):
        delattr(request.state, "_principal_cache")

    auth_service = MagicMock()
    auth_service.resolve_principal.return_value = "mock_principal"
    monitoring_service = MagicMock()

    # First call - cache miss
    principal1 = get_current_principal(request, auth_service, monitoring_service)
    assert principal1 == "mock_principal"
    auth_service.resolve_principal.assert_called_once_with(request)

    # Second call - cache hit
    principal2 = get_current_principal(request, auth_service, monitoring_service)
    assert principal2 == "mock_principal"
    # Should not be called again
    assert auth_service.resolve_principal.call_count == 1
