"""Codex execution service with runtime abstraction and error translation."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from os import X_OK, access
from pathlib import Path
from time import perf_counter

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
from app.services.monitoring_service import MonitoringService

LOGGER = logging.getLogger(__name__)
INHERITED_MODEL_NAME = "codex-default"
SAFE_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_SESSION_ID_LENGTH = 128
FALLBACK_SESSION_LABEL_LENGTH = 48
FALLBACK_SESSION_HASH_LENGTH = 12


class CodexExecutionService:
    """Application service responsible for executing tasks through Codex."""

    def __init__(
        self,
        settings: AppSettings,
        monitoring_service: MonitoringService | None = None,
    ) -> None:
        self.settings = settings
        self.monitoring_service = monitoring_service
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

        session_id = self._resolve_session_id(request, principal)
        if self.monitoring_service is not None:
            self.monitoring_service.record_task_started(
                request_id=request_id,
                session_id=session_id,
                principal=principal,
                task_description=request.task_description,
                model=self.settings.codex_model or INHERITED_MODEL_NAME,
            )

        cwd = None

        if self.settings.codex_sessions_base_path:
            # Normalize and resolve base path
            base_dir = os.path.realpath(self.settings.codex_sessions_base_path)
            # Construct target path using sanitized session_id
            target_path = os.path.realpath(os.path.join(base_dir, session_id))

            # Defense-in-depth: explicit prefix check (standard CodeQL sanitizer)
            if (
                not target_path.startswith(base_dir + os.sep)
                and target_path != base_dir
            ):
                LOGGER.error(
                    "Path traversal attempt blocked. actor=%s",
                    principal.display_name,
                )
                raise InvalidTaskRequestError(
                    "Invalid session_id: resolved path escapes the allowed workspace area.",
                )

            cwd = target_path

            session_dir = Path(target_path)
            created_workspace = False
            if not session_dir.exists():
                if self.settings.codex_project_source:
                    source_path = Path(
                        os.path.realpath(self.settings.codex_project_source)
                    )
                    if not source_path.exists():
                        self._record_task_failure(
                            request_id,
                            ConfigurationError(
                                f"Configured project source not found: {source_path}"
                            ),
                            start,
                        )
                        raise ConfigurationError(
                            f"Configured project source not found: {source_path}"
                        )
                    try:
                        shutil.copytree(source_path, session_dir, symlinks=True)
                        created_workspace = True
                    except Exception as exc:
                        self._record_task_failure(request_id, exc, start)
                        raise CodexExecutionError(
                            f"Failed to provision session workspace: {exc}"
                        ) from exc
                else:
                    try:
                        session_dir.mkdir(parents=True, exist_ok=True)
                        created_workspace = True
                    except Exception as exc:
                        self._record_task_failure(request_id, exc, start)
                        raise CodexExecutionError(
                            f"Failed to create session workspace: {exc}"
                        ) from exc
            if self.monitoring_service is not None:
                self.monitoring_service.record_workspace_event(
                    request_id=request_id,
                    session_id=session_id,
                    workspace_path=str(session_dir),
                    created=created_workspace,
                )

        try:
            with Codex(config=self._build_app_server_config(cwd=cwd)) as codex:
                thread = codex.thread_start(**self._build_thread_start_kwargs())
                result = thread.run(request.task_description)
        except ServerBusyError as exc:
            self._record_task_failure(request_id, exc, start)
            raise CodexRuntimeBusyError(
                "Codex is currently busy. Please retry later.",
                details=str(exc),
            ) from exc
        except JsonRpcError as exc:
            self._record_task_failure(request_id, exc, start)
            raise InvalidTaskRequestError(
                "Codex rejected the submitted task request.",
                details=str(exc),
            ) from exc
        except FileNotFoundError as exc:
            self._record_task_failure(request_id, exc, start)
            raise ConfigurationError(
                "The configured Codex runtime could not be found.",
                details=str(exc),
            ) from exc
        except Exception as exc:
            self._record_task_failure(request_id, exc, start)
            raise CodexExecutionError(
                "Task execution failed unexpectedly.",
                details=str(exc),
            ) from exc

        duration_ms = int((perf_counter() - start) * 1000)
        final_response = (
            result.final_response if result.final_response is not None else ""
        )

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
        if self.monitoring_service is not None:
            self.monitoring_service.record_task_completed(
                request_id=request_id,
                duration_ms=duration_ms,
                result_length=len(final_response),
            )

        return TaskExecutionResponse(
            result=final_response,
            metadata=TaskExecutionMetadata(
                request_id=request_id,
                model=self.settings.codex_model or INHERITED_MODEL_NAME,
                duration_ms=duration_ms,
            ),
        )

    def _resolve_session_id(
        self,
        request: TaskExecutionRequest,
        principal: UserPrincipal,
    ) -> str:
        """Resolve the effective workspace session id for this task."""
        if request.session_id is not None:
            return self._validate_explicit_session_id(request.session_id)
        return self._derive_principal_session_id(principal)

    def _validate_explicit_session_id(self, raw_session_id: str) -> str:
        """Validate a client-provided session id as one safe path segment."""
        session_id = os.path.basename(str(raw_session_id))

        if (
            not session_id
            or session_id in {".", ".."}
            or session_id != raw_session_id
            or len(session_id) > MAX_SESSION_ID_LENGTH
            or not SAFE_SESSION_ID_PATTERN.fullmatch(session_id)
        ):
            raise InvalidTaskRequestError(
                "Invalid session_id: must be a single safe path segment (alphanumeric, underscores, or hyphens).",
            )
        return session_id

    def _derive_principal_session_id(self, principal: UserPrincipal) -> str:
        """Build a deterministic safe session id from the authenticated identity."""
        raw_identity = principal.username or principal.subject or "local-development"
        session_id = os.path.basename(str(raw_identity))
        if (
            session_id
            and session_id not in {".", ".."}
            and session_id == raw_identity
            and len(session_id) <= MAX_SESSION_ID_LENGTH
            and SAFE_SESSION_ID_PATTERN.fullmatch(session_id)
        ):
            return session_id

        normalized_identity = re.sub(r"[^A-Za-z0-9_-]+", "-", raw_identity).strip("-_")
        normalized_identity = re.sub(r"-{2,}", "-", normalized_identity)
        normalized_identity = (
            normalized_identity[:FALLBACK_SESSION_LABEL_LENGTH].rstrip("-_")
            or "session"
        )
        identity_fingerprint = "::".join(
            part
            for part in (
                principal.auth_mode,
                principal.tenant_id,
                principal.subject,
                principal.username,
            )
            if part
        )
        digest = hashlib.sha256(identity_fingerprint.encode("utf-8")).hexdigest()[
            :FALLBACK_SESSION_HASH_LENGTH
        ]
        return f"{normalized_identity}-{digest}"

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

    def _build_app_server_config(
        self, cwd: str | None = None
    ) -> AppServerConfig | None:
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

    def _record_task_failure(
        self,
        request_id: str,
        exc: Exception,
        start: float,
    ) -> None:
        """Record a failed task in the monitoring subsystem when enabled."""
        if self.monitoring_service is None:
            return
        self.monitoring_service.record_task_failed(
            request_id=request_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            duration_ms=int((perf_counter() - start) * 1000),
        )

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
