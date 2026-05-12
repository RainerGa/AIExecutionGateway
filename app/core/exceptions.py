"""Domain-specific exception types mapped to stable HTTP error payloads."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base exception for controlled, client-facing application failures."""

    status_code = 500
    error_code = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        details: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers or {}


class InvalidTaskRequestError(ApplicationError):
    """Raised when Codex rejects the logical content of a task request."""

    status_code = 400
    error_code = "invalid_task_request"


class CodexRuntimeBusyError(ApplicationError):
    """Raised when the upstream Codex runtime cannot accept new work."""

    status_code = 503
    error_code = "codex_runtime_busy"


class CodexExecutionError(ApplicationError):
    """Raised when task execution fails for an internal or upstream reason."""

    status_code = 500
    error_code = "codex_execution_failed"


class ConfigurationError(ApplicationError):
    """Raised when the local service runtime is configured incorrectly."""

    status_code = 500
    error_code = "configuration_error"


class AuthenticationRequiredError(ApplicationError):
    """Raised when a protected endpoint is called without valid credentials."""

    status_code = 401
    error_code = "authentication_required"


class AuthenticationFailedError(ApplicationError):
    """Raised when provided authentication material is malformed or invalid."""

    status_code = 401
    error_code = "authentication_failed"


class AuthorizationDeniedError(ApplicationError):
    """Raised when an authenticated user lacks the required application role."""

    status_code = 403
    error_code = "authorization_denied"
