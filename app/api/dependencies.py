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
    """Expose the process-wide monitoring service."""
    return request.app.state.monitoring_service


def get_request_id(request: Request) -> str:
    """Expose the active request id from request state to endpoint handlers."""
    return getattr(request.state, "request_id", "-")


def get_codex_execution_service(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> CodexExecutionService:
    """Create a request-scoped Codex execution service from shared settings."""
    return CodexExecutionService(
        settings=settings,
        monitoring_service=get_monitoring_service(request),
    )


def get_authentication_service(
    settings: AppSettings = Depends(get_settings),
) -> AuthenticationService:
    """Create a request-scoped authentication service from shared settings."""
    return AuthenticationService(settings=settings)


def get_current_principal(
    request: Request,
    auth_service: AuthenticationService = Depends(get_authentication_service),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> UserPrincipal | None:
    """Resolve and cache the current principal for the active request."""
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
    """Require a principal with sufficient privileges for task execution."""
    return auth_service.require_execute_task_access(principal)


def require_admin_principal(
    principal: UserPrincipal | None = Depends(get_current_principal),
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> UserPrincipal:
    """Require a principal with admin access."""
    return auth_service.require_admin_access(principal)
