"""Dependency providers used by FastAPI endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import Depends, Request

from app.core.config import AppSettings, get_settings
from app.security.authentication import AuthenticationService
from app.security.models import UserPrincipal
from app.services.codex_service import CodexExecutionService
from app.services.monitoring_service import MonitoringService

_PRINCIPAL_CACHE_KEY = "_principal_cache"
_PRINCIPAL_CACHE_MISS = object()


def get_monitoring_service(request: Request) -> MonitoringService:
    """Exposes the process-wide monitoring service.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The `MonitoringService` instance stored in the application state.
    """
    return request.app.state.monitoring_service


def get_request_id(request: Request) -> str:
    """Exposes the active request ID from request state to endpoint handlers.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The request ID string or "-" if not bound.
    """
    return getattr(request.state, "request_id", "-")


def get_codex_execution_service(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> CodexExecutionService:
    """Creates a request-scoped Codex execution service from shared settings.

    Args:
        request: The incoming FastAPI request.
        settings: The current application settings.

    Returns:
        A new instance of `CodexExecutionService`.
    """
    return CodexExecutionService(
        settings=settings,
        monitoring_service=get_monitoring_service(request),
    )


def get_authentication_service(
    settings: AppSettings = Depends(get_settings),
) -> AuthenticationService:
    """Creates a request-scoped authentication service from shared settings.

    Args:
        settings: The current application settings.

    Returns:
        A new instance of `AuthenticationService`.
    """
    return AuthenticationService(settings=settings)


def get_current_principal(
    request: Request,
    auth_service: AuthenticationService = Depends(get_authentication_service),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> UserPrincipal | None:
    """Resolves and caches the current principal for the active request.

    This dependency performs the actual authentication logic and caches
    the result in the request state to avoid redundant work if accessed
    multiple times during the same request.

    Args:
        request: The incoming FastAPI request.
        auth_service: The authentication service instance.
        monitoring_service: The monitoring service instance.

    Returns:
        The resolved `UserPrincipal` or None if authentication is disabled
        or failed.
    """
    cached_principal = getattr(
        request.state, _PRINCIPAL_CACHE_KEY, _PRINCIPAL_CACHE_MISS
    )
    if cached_principal is not _PRINCIPAL_CACHE_MISS:
        return cast("UserPrincipal | None", cached_principal)

    principal = auth_service.resolve_principal(request)
    if principal is not None:
        monitoring_service.record_principal_resolved(
            request_id=get_request_id(request),
            principal=principal,
        )
    setattr(request.state, _PRINCIPAL_CACHE_KEY, principal)
    return principal


def require_task_execution_principal(
    principal: UserPrincipal | None = Depends(get_current_principal),
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> UserPrincipal:
    """Requires a principal with sufficient privileges for task execution.

    Args:
        principal: The resolved principal from `get_current_principal`.
        auth_service: The authentication service instance.

    Returns:
        The validated `UserPrincipal`.

    Raises:
        AuthenticationRequiredError: If no principal is resolved.
        AuthorizationDeniedError: If the principal lacks 'execute' permissions.
    """
    return auth_service.require_execute_task_access(principal)


def require_admin_principal(
    principal: UserPrincipal | None = Depends(get_current_principal),
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> UserPrincipal:
    """Requires a principal with administrative access.

    Args:
        principal: The resolved principal from `get_current_principal`.
        auth_service: The authentication service instance.

    Returns:
        The validated `UserPrincipal`.

    Raises:
        AuthenticationRequiredError: If no principal is resolved.
        AuthorizationDeniedError: If the principal lacks 'admin' permissions.
    """
    return auth_service.require_admin_access(principal)
