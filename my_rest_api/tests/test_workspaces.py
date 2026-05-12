"""Deep tests for Workspace Isolation and Session Management.

These tests verify that the API correctly isolates user sessions 
into distinct filesystem directories and provisions them from templates.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from app.services.codex_service import CodexExecutionService
from app.schemas.codex import TaskExecutionRequest
from tests.support import build_test_principal, build_test_settings

TEST_PRINCIPAL = build_test_principal(username="alice")


def test_workspace_provisioning_from_template(tmp_path: Path):
    """
    DEEP TEST: Verifies that if a project_source is configured:
    1. A new session directory is created in sessions_base_path.
    2. The contents of project_source are copied into the session directory.
    3. The Codex runtime is started with the correct CWD.
    """
    sessions_dir = tmp_path / "sessions"
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "README.txt").write_text("template content")
    
    settings = build_test_settings()
    # Use dataclasses.replace as AppSettings is a frozen dataclass
    settings = replace(
        settings,
        codex_sessions_base_path=str(sessions_dir),
        codex_project_source=str(template_dir)
    )
    
    service = CodexExecutionService(settings=settings)
    
    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="OK")

        service.execute_task(
            TaskExecutionRequest(task_description="test"),
            request_id="req-ws-1",
            principal=TEST_PRINCIPAL
        )

        # Verify filesystem state
        alice_dir = sessions_dir / "alice"
        assert alice_dir.exists()
        assert (alice_dir / "README.txt").exists()
        assert (alice_dir / "README.txt").read_text() == "template content"

        # Verify Codex config
        args, kwargs = mock_codex_class.call_args
        assert kwargs["config"].cwd == str(alice_dir)


def test_session_isolation_uses_separate_directories(tmp_path: Path):
    """
    DEEP TEST: Verifies that different session_ids lead to different 
    Working Directories, ensuring complete data isolation.
    """
    sessions_dir = tmp_path / "sessions"
    settings = build_test_settings()
    settings = replace(settings, codex_sessions_base_path=str(sessions_dir))
    
    service = CodexExecutionService(settings=settings)
    
    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="OK")

        # Session 1: Alice
        service.execute_task(
            TaskExecutionRequest(task_description="test", session_id="session-A"),
            request_id="req-A",
            principal=TEST_PRINCIPAL
        )
        cwd_A = mock_codex_class.call_args[1]["config"].cwd

        # Session 2: Bob (different session_id)
        service.execute_task(
            TaskExecutionRequest(task_description="test", session_id="session-B"),
            request_id="req-B",
            principal=TEST_PRINCIPAL
        )
        cwd_B = mock_codex_class.call_args[1]["config"].cwd

        assert cwd_A != cwd_B
        assert "session-A" in cwd_A
        assert "session-B" in cwd_B


def test_workspace_creation_fails_gracefully_on_missing_template(tmp_path: Path):
    """
    DEEP TEST: Verifies that if the project_source is missing, 
    the API returns a proper ConfigurationError (500) instead of crashing.
    """
    from app.core.exceptions import ConfigurationError
    
    settings = build_test_settings()
    settings = replace(
        settings,
        codex_sessions_base_path=str(tmp_path / "sessions"),
        codex_project_source="/non/existent/path"
    )
    
    service = CodexExecutionService(settings=settings)
    
    with pytest.raises(ConfigurationError) as exc_info:
        service.execute_task(
            TaskExecutionRequest(task_description="test"),
            request_id="req-fail",
            principal=TEST_PRINCIPAL
        )
    assert "project source not found" in str(exc_info.value)
