"""Request-scoped context helpers for correlation and observability."""

from __future__ import annotations

from contextvars import Token, ContextVar


_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the request identifier currently bound to the active context."""
    return _request_id_context.get()


def set_request_id(request_id: str) -> Token[str]:
    """Bind a request identifier to the current async context."""
    return _request_id_context.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Restore the previous request identifier after request processing."""
    _request_id_context.reset(token)
