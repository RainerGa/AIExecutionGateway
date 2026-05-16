"""Unit tests for the Codex service layer and its error translation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from codex_app_server.errors import JsonRpcError, ServerBusyError

from app.core.exceptions import (
    CodexExecutionError,
    CodexRuntimeBusyError,
    InvalidTaskRequestError,
    ConfigurationError,
)
from app.schemas.codex import TaskExecutionRequest
from app.services.codex_service import CodexExecutionService, INHERITED_MODEL_NAME
from app.services.monitoring_service import MonitoringService
from tests.support import build_test_principal, build_test_settings

TEST_PRINCIPAL = build_test_principal()


def test_execute_task_success_returns_metadata():
    """The service should return the Codex result plus execution metadata."""
    settings = build_test_settings(codex_model="gpt-5.4")
    service = CodexExecutionService(
        settings=settings,
        monitoring_service=MonitoringService(settings.monitoring),
    )

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_result = MagicMock(final_response="Hello, enterprise!")
        mock_thread.run.return_value = mock_result

        response = service.execute_task(
            TaskExecutionRequest(task_description="Answer politely."),
            request_id="req-123",
            principal=TEST_PRINCIPAL,
        )

    assert response.result == "Hello, enterprise!"
    assert response.logs == []
    assert response.metadata.request_id == "req-123"
    assert response.metadata.model == "gpt-5.4"
    assert response.metadata.duration_ms >= 0
    mock_codex_instance.thread_start.assert_called_once_with(model="gpt-5.4")


def test_execute_task_without_model_override_uses_inherited_model_name():
    """The metadata should show the inherited default when no override is set."""
    settings = build_test_settings()
    service = CodexExecutionService(
        settings=settings,
        monitoring_service=MonitoringService(settings.monitoring),
    )

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="Done")

        response = service.execute_task(
            TaskExecutionRequest(task_description="Do the thing."),
            request_id="req-124",
            principal=TEST_PRINCIPAL,
        )

    assert response.metadata.model == INHERITED_MODEL_NAME
    mock_codex_instance.thread_start.assert_called_once_with()


def test_execute_task_maps_jsonrpc_errors():
    """JSON-RPC failures should be translated into a stable 400 domain error."""
    settings = build_test_settings()
    monitoring = MonitoringService(settings.monitoring)
    service = CodexExecutionService(settings=settings, monitoring_service=monitoring)

    with patch(
        "app.services.codex_service.Codex",
        side_effect=JsonRpcError(code=-32600, message="invalid request"),
    ):
        with pytest.raises(InvalidTaskRequestError) as exc_info:
            service.execute_task(
                TaskExecutionRequest(task_description="Bad task"),
                request_id="req-125",
                principal=TEST_PRINCIPAL,
            )

    assert "Codex rejected" in exc_info.value.message
    assert monitoring.snapshot().recent_tasks[0].status == "failed"


def test_execute_task_maps_server_busy_errors():
    """Busy upstream conditions should surface as service-unavailable errors."""
    settings = build_test_settings()
    service = CodexExecutionService(
        settings=settings,
        monitoring_service=MonitoringService(settings.monitoring),
    )

    with patch(
        "app.services.codex_service.Codex",
        side_effect=ServerBusyError(code=-32000, message="busy"),
    ):
        with pytest.raises(CodexRuntimeBusyError):
            service.execute_task(
                TaskExecutionRequest(task_description="Busy task"),
                request_id="req-126",
                principal=TEST_PRINCIPAL,
            )


def test_execute_task_maps_unexpected_errors():
    """Unexpected runtime failures should be wrapped in a generic execution error."""
    settings = build_test_settings()
    service = CodexExecutionService(
        settings=settings,
        monitoring_service=MonitoringService(settings.monitoring),
    )

    with patch("app.services.codex_service.Codex", side_effect=RuntimeError("boom")):
        with pytest.raises(CodexExecutionError):
            service.execute_task(
                TaskExecutionRequest(task_description="Crash task"),
                request_id="req-127",
                principal=TEST_PRINCIPAL,
            )


def test_execute_task_audit_logging():
    settings = build_test_settings()
    object.__setattr__(settings.audit, "enabled", True)
    service = CodexExecutionService(
        settings=settings,
        monitoring_service=MonitoringService(settings.monitoring),
    )
    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="Audit test")

        response = service.execute_task(
            TaskExecutionRequest(task_description="Test audit"),
            request_id="req-123",
            principal=TEST_PRINCIPAL,
        )
    assert response.result == "Audit test"


def test_execute_task_workspace_missing_source():
    settings = build_test_settings(
        codex_sessions_base_path="/tmp/sessions", codex_project_source="/does/not/exist"
    )
    monitoring = MonitoringService(settings.monitoring)
    service = CodexExecutionService(settings=settings, monitoring_service=monitoring)
    with patch("pathlib.Path.exists", side_effect=[False, False]):
        with pytest.raises(ConfigurationError) as exc_info:
            service.execute_task(
                TaskExecutionRequest(task_description="Test"),
                request_id="req-123",
                principal=TEST_PRINCIPAL,
            )
        assert "Configured project source not found" in str(exc_info.value)
        assert monitoring.snapshot().recent_tasks[0].status == "failed"


def test_execute_task_workspace_copytree_error():
    settings = build_test_settings(
        codex_sessions_base_path="/tmp/sessions", codex_project_source="/tmp/src"
    )
    monitoring = MonitoringService(settings.monitoring)
    service = CodexExecutionService(settings=settings, monitoring_service=monitoring)
    with (
        patch("pathlib.Path.exists", side_effect=[False, True]),
        patch("shutil.copytree", side_effect=PermissionError("denied")),
    ):
        with pytest.raises(
            CodexExecutionError, match="Failed to provision session workspace"
        ):
            service.execute_task(
                TaskExecutionRequest(task_description="Test"),
                request_id="req-123",
                principal=TEST_PRINCIPAL,
            )
    assert monitoring.snapshot().recent_tasks[0].status == "failed"


def test_execute_task_workspace_mkdir_error():
    settings = build_test_settings(codex_sessions_base_path="/tmp/sessions")
    monitoring = MonitoringService(settings.monitoring)
    service = CodexExecutionService(settings=settings, monitoring_service=monitoring)
    with (
        patch("pathlib.Path.exists", return_value=False),
        patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")),
    ):
        with pytest.raises(
            CodexExecutionError, match="Failed to create session workspace"
        ):
            service.execute_task(
                TaskExecutionRequest(task_description="Test"),
                request_id="req-123",
                principal=TEST_PRINCIPAL,
            )
    assert monitoring.snapshot().recent_tasks[0].status == "failed"


def test_execute_task_file_not_found_error():
    settings = build_test_settings()
    monitoring = MonitoringService(settings.monitoring)
    service = CodexExecutionService(settings=settings, monitoring_service=monitoring)
    with patch(
        "app.services.codex_service.Codex",
        side_effect=FileNotFoundError("codex missing"),
    ):
        with pytest.raises(
            ConfigurationError, match="configured Codex runtime could not be found"
        ):
            service.execute_task(
                TaskExecutionRequest(task_description="Test"),
                request_id="req-123",
                principal=TEST_PRINCIPAL,
            )
    assert monitoring.snapshot().recent_tasks[0].status == "failed"


def test_readiness_components_with_codex_bin():
    settings = build_test_settings(codex_bin="/bin/codex")
    service = CodexExecutionService(
        settings=settings,
        monitoring_service=MonitoringService(settings.monitoring),
    )

    with patch("app.services.codex_service.access", return_value=True):
        components = service.readiness_components()
        assert components[1].status == "up"

    with patch("app.services.codex_service.access", return_value=False):
        components = service.readiness_components()
        assert components[1].status == "down"


def test_build_app_server_config_none():
    settings = build_test_settings()
    service = CodexExecutionService(
        settings=settings,
        monitoring_service=MonitoringService(settings.monitoring),
    )
    assert service._build_app_server_config() is None
    config = service._build_app_server_config(cwd="/tmp")
    assert config is not None
    assert config.cwd == "/tmp"


def test_execute_task_monitoring_captures_workspace_reuse(tmp_path):
    sessions_dir = tmp_path / "sessions"
    workspace_dir = sessions_dir / "session-A"
    workspace_dir.mkdir(parents=True)
    settings = build_test_settings(codex_sessions_base_path=str(sessions_dir))
    monitoring = MonitoringService(settings.monitoring)
    service = CodexExecutionService(settings=settings, monitoring_service=monitoring)

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="ok")

        service.execute_task(
            TaskExecutionRequest(task_description="Inspect", session_id="session-A"),
            request_id="req-reuse",
            principal=TEST_PRINCIPAL,
        )

    snapshot = monitoring.snapshot()
    assert snapshot.recent_tasks[0].workspace_state == "reused"


def test_execute_task_derives_safe_workspace_session_from_identity(tmp_path):
    sessions_dir = tmp_path / "sessions"
    settings = build_test_settings(codex_sessions_base_path=str(sessions_dir))
    service = CodexExecutionService(settings=settings)
    principal = build_test_principal(
        subject="oidc-user-123",
        username="alice@example.org",
        auth_mode="oidc_jwt",
        email="alice@example.org",
    )

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="ok")

        service.execute_task(
            TaskExecutionRequest(task_description="Inspect"),
            request_id="req-derived",
            principal=principal,
        )

    workspace_name = Path(mock_codex_class.call_args[1]["config"].cwd).name
    assert workspace_name.startswith("alice-example-org-")
    assert "@" not in workspace_name


def test_execute_task_rejects_explicit_invalid_session_id_even_if_model_validation_is_bypassed():
    settings = build_test_settings()
    service = CodexExecutionService(settings=settings)
    request = TaskExecutionRequest.model_construct(
        task_description="Inspect",
        session_id="alice@example.org",
    )

    with pytest.raises(InvalidTaskRequestError, match="Invalid session_id"):
        service.execute_task(
            request,
            request_id="req-invalid-session",
            principal=TEST_PRINCIPAL,
        )
