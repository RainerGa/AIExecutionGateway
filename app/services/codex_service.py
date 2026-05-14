"""Codex execution service with runtime abstraction and error translation."""

from __future__ import annotations

import logging
import re
import shutil
from os import access, X_OK
from pathlib import Path
from time import perf_counter
import os

from codex_app_server import AppServerConfig, Codex
from codex_app_server.errors import JsonRpcError, ServerBusyError

from app.core.config import AppSettings
from app.core.exceptions import (
    CodexExecutionError,
    CodexRuntimeBusyError,
    ConfigurationError,
    InvalidTaskRequestError,
)

from app.schemas.codex import (
    TaskExecutionMetadata,
    TaskExecutionRequest,
    TaskExecutionResponse,
)
from app.schemas.health import HealthComponent
from app.security.models import UserPrincipal

LOGGER = logging.getLogger(__name__)
INHERITED_MODEL_NAME = "codex-default"
SAFE_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class CodexExecutionService:
    """Application service responsible for executing tasks through Codex."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._warn_if_misconfigured()

    def execute_task(
        self,
        request: TaskExecutionRequest,
        *,
        request_id: str,
        principal: UserPrincipal,
    ) -> TaskExecutionResponse:
        """Execute one validated task request and map it into an API response."""
        start = perf_counter()
        LOGGER.info(
            "Executing Codex task. actor=%s auth_mode=%s roles=%s task_length=%s model_override=%s",
            principal.display_name,
            principal.auth_mode,
            ",".join(principal.roles) if principal.roles else "-",
            len(request.task_description),
            self.settings.codex_model or INHERITED_MODEL_NAME,
        )
        if self.settings.audit.enabled:
            LOGGER.info(
                "Audit event=task_execution_started actor=%s request_id=%s auth_mode=%s",
                principal.display_name,
                request_id,
                principal.auth_mode,
            )

        raw_session_id = request.session_id or principal.username
        session_id = self._sanitize_session_id(raw_session_id)

        cwd = None

        if self.settings.codex_sessions_base_path:
            # CodeQL-friendly path normalization
            base_dir = os.path.realpath(self.settings.codex_sessions_base_path)
            # Explicitly untaint the session_id at the call site
            safe_session_id = os.path.basename(session_id)
            target_path = os.path.realpath(os.path.join(base_dir, safe_session_id))

            # Defense-in-depth: explicit prefix check is a standard CodeQL sanitizer
            if not target_path.startswith(base_dir + os.sep) and target_path != base_dir:
                LOGGER.error(
                    "Path traversal attempt blocked. actor=%s",
                    principal.display_name,
                )
                raise InvalidTaskRequestError(
                    "Invalid session_id: resolved path escapes the allowed workspace area.",
                )

            session_dir = Path(target_path)
            cwd = str(session_dir)

            if not session_dir.exists():
                if self.settings.codex_project_source:
                    # Also normalize source_path to satisfy static analysis
                    source_path = Path(os.path.realpath(self.settings.codex_project_source))
                    if not source_path.exists():
                        raise ConfigurationError(f"Configured project source not found: {source_path}")
                    try:
                        shutil.copytree(source_path, session_dir, symlinks=True)
                    except Exception as exc:
                        raise CodexExecutionError(f"Failed to provision session workspace: {exc}") from exc
                else:
                    try:
                        session_dir.mkdir(parents=True, exist_ok=True)
                    except Exception as exc:
                        raise CodexExecutionError(f"Failed to create session workspace: {exc}") from exc

        try:
            with Codex(config=self._build_app_server_config(cwd=cwd)) as codex:
                thread = codex.thread_start(**self._build_thread_start_kwargs())
                result = thread.run(request.task_description)
        except ServerBusyError as exc:
            raise CodexRuntimeBusyError(
                "Codex is currently busy. Please retry later.",
                details=str(exc),
            ) from exc
        except JsonRpcError as exc:
            raise InvalidTaskRequestError(
                "Codex rejected the submitted task request.",
                details=str(exc),
            ) from exc
        except FileNotFoundError as exc:
            raise ConfigurationError(
                "The configured Codex runtime could not be found.",
                details=str(exc),
            ) from exc
        except Exception as exc:
            raise CodexExecutionError(
                "Task execution failed unexpectedly.",
                details=str(exc),
            ) from exc

        duration_ms = int((perf_counter() - start) * 1000)
        final_response = result.final_response if result.final_response is not None else ""

        LOGGER.info(
            "Codex task completed. actor=%s duration_ms=%s result_length=%s",
            principal.display_name,
            duration_ms,
            len(final_response),
        )
        if self.settings.audit.enabled:
            LOGGER.info(
                "Audit event=task_execution_completed actor=%s request_id=%s duration_ms=%s",
                principal.display_name,
                request_id,
                duration_ms,
            )

        return TaskExecutionResponse(
            result=final_response,
            metadata=TaskExecutionMetadata(
                request_id=request_id,
                model=self.settings.codex_model or INHERITED_MODEL_NAME,
                duration_ms=duration_ms,
            ),
        )

    def _sanitize_session_id(self, raw_session_id: str) -> str:
        """Validate and normalize user-provided session id to one safe path segment."""
        # CodeQL py/path-injection sanitizer: os.path.basename explicitly untaints the string
        session_id = os.path.basename(str(raw_session_id))
        
        if (
            not session_id
            or session_id in {".", ".."}
            or session_id != raw_session_id
            or not SAFE_SESSION_ID_PATTERN.fullmatch(session_id)
        ):
            raise InvalidTaskRequestError(
                "Invalid session_id: must be a single safe path segment (alphanumeric, underscores, or hyphens).",
            )
        return session_id

    def readiness_components(self) -> list[HealthComponent]:
        """Return a lightweight readiness report for infrastructure probing."""
        codex_bin = self.settings.codex_bin or "codex on PATH or packaged default"
        is_ready = True

        if self.settings.codex_bin:
            is_ready = access(self.settings.codex_bin, X_OK)

        codex_detail = (
            f"Configured runtime is executable: {codex_bin}"
            if is_ready
            else f"Configured runtime is not executable: {codex_bin}"
        )

        return [
            HealthComponent(
                name="api",
                status="up",
                details=f"Environment={self.settings.environment}",
            ),
            HealthComponent(
                name="codex_runtime",
                status="up" if is_ready else "down",
                details=codex_detail,
            ),
        ]

    def _build_app_server_config(self, cwd: str | None = None) -> AppServerConfig | None:
        """Build the SDK runtime configuration."""
        if not self.settings.codex_bin and not cwd:
            return None
        return AppServerConfig(
            codex_bin=self.settings.codex_bin,
            cwd=cwd,
        )

    def _build_thread_start_kwargs(self) -> dict[str, str]:
        """Provide optional thread start parameters for the active environment."""
        if not self.settings.codex_model:
            return {}
        return {"model": self.settings.codex_model}

    def _warn_if_misconfigured(self) -> None:
        """Emit a prominent warning for configurations that weaken workspace isolation.

        When authentication is disabled every request resolves to the same
        ``local-development`` principal.  If session workspaces are active at
        the same time, all concurrent requests share a *single* workspace
        directory, which completely undermines the isolation guarantee.
        This combination is only acceptable for local single-user development.
        """
        if (
            self.settings.auth.mode == "disabled"
            and self.settings.codex_sessions_base_path
        ):
            LOGGER.warning(
                "SECURITY WARNING: auth_mode=disabled with an active codex_sessions_base_path. "
                "All requests share the 'local-development' workspace – no user isolation. "
                "Do NOT use this configuration in multi-user or production environments."
            )
