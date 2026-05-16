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
        codex_project_source=str(template_dir),
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
            principal=TEST_PRINCIPAL,
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
            principal=TEST_PRINCIPAL,
        )
        cwd_A = mock_codex_class.call_args[1]["config"].cwd

        # Session 2: Bob (different session_id)
        service.execute_task(
            TaskExecutionRequest(task_description="test", session_id="session-B"),
            request_id="req-B",
            principal=TEST_PRINCIPAL,
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
        codex_project_source="/non/existent/path",
    )

    service = CodexExecutionService(settings=settings)

    with pytest.raises(ConfigurationError) as exc_info:
        service.execute_task(
            TaskExecutionRequest(task_description="test"),
            request_id="req-fail",
            principal=TEST_PRINCIPAL,
        )
    assert "project source not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ADVERSARIAL TESTS – Path Traversal & Injection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unsafe_username",
    [
        "../../../etc",
        "alice/../../etc",
        "..",
        "/absolute/path",
        "../../root",
        "alice@example.org",
    ],
)
def test_identity_fallback_session_id_is_safely_derived(
    tmp_path: Path, unsafe_username: str
):
    """
    ADVERSARIAL TEST: Even if the authenticated identity contains path separators
    or other unsafe characters, the derived workspace session id must stay inside
    sessions_base_path and resolve to one safe path segment.
    """
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    settings = build_test_settings()
    settings = replace(settings, codex_sessions_base_path=str(sessions_dir))

    service = CodexExecutionService(settings=settings)
    principal = build_test_principal(
        subject="principal-123",
        username=unsafe_username,
        auth_mode="oidc_jwt",
    )

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_codex_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_codex_instance
        mock_thread = MagicMock()
        mock_codex_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="OK")

        service.execute_task(
            TaskExecutionRequest(task_description="test"),
            request_id="req-derived-session",
            principal=principal,
        )

    derived_workspace = Path(mock_codex_class.call_args[1]["config"].cwd)
    assert derived_workspace.parent == sessions_dir
    assert "/" not in derived_workspace.name
    assert "\\" not in derived_workspace.name
    assert derived_workspace.name not in {".", ".."}


@pytest.mark.parametrize(
    "bad_session_id",
    [
        "../../../etc",
        "alice/../../etc",
        "..",
        "alice/../bob",
        "/absolute/path",
        "alice evil",
        "alice;evil",
        "alice\x00evil",
        "",
    ],
)
def test_schema_rejects_dangerous_session_ids(bad_session_id: str):
    """
    ADVERSARIAL TEST: Verifies that the Pydantic schema rejects all session_id
    values containing path traversal sequences, special characters, or null bytes.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TaskExecutionRequest(task_description="test", session_id=bad_session_id)


@pytest.mark.parametrize(
    "safe_session_id",
    [
        "alice",
        "session-123",
        "user_abc",
        "MySession-42",
        "a" * 128,
    ],
)
def test_schema_accepts_safe_session_ids(safe_session_id: str):
    """
    Verifies that valid session_ids (letters, digits, hyphens, underscores)
    pass the schema validator unchanged.
    """
    req = TaskExecutionRequest(task_description="test", session_id=safe_session_id)
    assert req.session_id == safe_session_id


def test_disabled_auth_with_sessions_emits_security_warning(tmp_path: Path, caplog):
    """
    ADVERSARIAL TEST: Verifies that the service emits a SECURITY WARNING when
    auth_mode=disabled is combined with an active sessions_base_path, because
    all requests would share the 'local-development' workspace directory.
    """
    import logging

    sessions_dir = tmp_path / "sessions"
    settings = build_test_settings(auth_mode="disabled")
    settings = replace(settings, codex_sessions_base_path=str(sessions_dir))

    with caplog.at_level(logging.WARNING, logger="app.services.codex_service"):
        CodexExecutionService(settings=settings)

    warning_messages = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any("SECURITY WARNING" in msg for msg in warning_messages), (
        "Expected a SECURITY WARNING when auth=disabled + sessions_base_path is set."
    )


def test_template_copytree_preserves_symlinks(tmp_path: Path):
    """
    SECURITY TEST: Verifies that template provisioning uses symlinks=True so that
    symlinks inside the template are copied as symlinks (not followed), preventing
    symlink-based escape attacks from within the template directory.
    """
    import os

    sessions_dir = tmp_path / "sessions"
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "real_file.txt").write_text("real content")

    outside_file = tmp_path / "outside_secret.txt"
    outside_file.write_text("sensitive data")
    os.symlink(outside_file, template_dir / "symlink_to_outside.txt")

    settings = build_test_settings()
    settings = replace(
        settings,
        codex_sessions_base_path=str(sessions_dir),
        codex_project_source=str(template_dir),
    )

    service = CodexExecutionService(settings=settings)

    with patch("app.services.codex_service.Codex") as mock_codex_class:
        mock_instance = MagicMock()
        mock_codex_class.return_value.__enter__.return_value = mock_instance
        mock_thread = MagicMock()
        mock_instance.thread_start.return_value = mock_thread
        mock_thread.run.return_value = MagicMock(final_response="OK")

        service.execute_task(
            TaskExecutionRequest(task_description="test"),
            request_id="req-symlink",
            principal=TEST_PRINCIPAL,
        )

    alice_dir = sessions_dir / "alice"
    symlink_in_session = alice_dir / "symlink_to_outside.txt"
    assert symlink_in_session.exists()
    assert symlink_in_session.is_symlink(), (
        "Symlinks in the template must be preserved as symlinks (symlinks=True), "
        "not followed – this prevents unintended data exposure."
    )
