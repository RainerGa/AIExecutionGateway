"""Domain-specific exception types mapped to stable HTTP error payloads."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base exception for controlled, client-facing application failures.

    This exception is caught by the central exception handler and converted
    into a structured JSON response.

    Attributes:
        status_code (int): The HTTP status code to return.
        error_code (str): A stable string identifier for the error category.
        message (str): A human-readable error message.
        details (str | None): Optional detailed information about the error.
        headers (dict[str, str]): Optional HTTP headers to include in the response.
    """

    status_code = 500
    error_code = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        details: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initializes the application error.

        Args:
            message: The human-readable error message.
            details: Optional technical or detailed information.
            headers: Optional HTTP headers for the error response.
        """
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers or {}


class InvalidTaskRequestError(ApplicationError):
    """Raised when Codex rejects the logical content of a task request.

    This typically happens if the input prompt or parameters are invalid
    according to the upstream model's requirements.
    """

    status_code = 400
    error_code = "invalid_task_request"


class CodexRuntimeBusyError(ApplicationError):
    """Raised when the upstream Codex runtime cannot accept new work.

    Indicates that the system is at capacity or the background process
    is temporarily unavailable.
    """

    status_code = 503
    error_code = "codex_runtime_busy"


class CodexExecutionError(ApplicationError):
    """Raised when task execution fails for an internal or upstream reason.

    Used for general failures during the task lifecycle that are not
    attributed to user input or capacity issues.
    """

    status_code = 500
    error_code = "codex_execution_failed"


class ConfigurationError(ApplicationError):
    """Raised when the local service runtime is configured incorrectly.

    This usually indicates missing environment variables, invalid config
    profiles, or unreachable local resources (like the codex binary).
    """

    status_code = 500
    error_code = "configuration_error"


class AuthenticationRequiredError(ApplicationError):
    """Raised when a protected endpoint is called without valid credentials.

    Triggers a 401 response prompting the client to authenticate.
    """

    status_code = 401
    error_code = "authentication_required"


class AuthenticationFailedError(ApplicationError):
    """Raised when provided authentication material is malformed or invalid.

    Includes cases like expired tokens, invalid signatures, or failed
    trusted header validation.
    """

    status_code = 401
    error_code = "authentication_failed"


class AuthorizationDeniedError(ApplicationError):
    """Raised when an authenticated user lacks the required application role.

    Used when a user is known but does not have the permissions to
    perform the requested action (e.g., executing a task without the 'user' role).
    """

    status_code = 403
    error_code = "authorization_denied"
