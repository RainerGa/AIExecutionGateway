"""Dependency providers used by FastAPI endpoints."""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.config import AppSettings, get_settings
from app.security.authentication import AuthenticationService
from app.security.models import UserPrincipal
from app.services.codex_service import CodexExecutionService

_PRINCIPAL_CACHE_KEY = "_principal_cache"
_PRINCIPAL_CACHE_MISS = object()


def get_request_id(request: Request) -> str:
    """Expose the active request id from request state to endpoint handlers."""
    return getattr(request.state, "request_id", "-")


def get_codex_execution_service(
    settings: AppSettings = Depends(get_settings),
) -> CodexExecutionService:
    """Create a request-scoped Codex execution service from shared settings."""
    return CodexExecutionService(settings=settings)


def get_authentication_service(
    settings: AppSettings = Depends(get_settings),
) -> AuthenticationService:
    """Create a request-scoped authentication service from shared settings."""
    return AuthenticationService(settings=settings)


def get_current_principal(
    request: Request,
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> UserPrincipal | None:
    """Resolve and cache the current principal for the active request."""
    cached_principal = getattr(request.state, _PRINCIPAL_CACHE_KEY, _PRINCIPAL_CACHE_MISS)
    if cached_principal is not _PRINCIPAL_CACHE_MISS:
        return cached_principal

    principal = auth_service.resolve_principal(request)
    setattr(request.state, _PRINCIPAL_CACHE_KEY, principal)
    return principal


def require_task_execution_principal(
    principal: UserPrincipal | None = Depends(get_current_principal),
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> UserPrincipal:
    """Require a principal with sufficient privileges for task execution."""
    return auth_service.require_execute_task_access(principal)
