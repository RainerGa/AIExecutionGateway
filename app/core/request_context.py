"""Request-scoped context helpers for correlation and observability."""

from __future__ import annotations

from contextvars import Token, ContextVar


_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Returns the request identifier currently bound to the active context.

    Returns:
        The current request ID string, or "-" if no ID is bound.
    """
    return _request_id_context.get()


def set_request_id(request_id: str) -> Token[str]:
    """Binds a request identifier to the current async context.

    Args:
        request_id: The unique identifier to bind to the context.

    Returns:
        A token used to restore the previous context state.
    """
    return _request_id_context.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Restores the previous request identifier after request processing.

    Args:
        token: The token returned by a previous call to `set_request_id`.
    """
    _request_id_context.reset(token)
