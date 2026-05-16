"""Operational health endpoints for monitoring and readiness checks."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_authentication_service, get_codex_execution_service
from app.core.config import AppSettings, get_settings
from app.schemas.health import HealthComponent, HealthResponse
from app.security.authentication import AuthenticationService
from app.services.codex_service import CodexExecutionService

router = APIRouter()


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns whether the API process is running and able to answer requests.",
)
async def read_liveness(
    settings: AppSettings = Depends(get_settings),
) -> HealthResponse:
    """Return the lightweight liveness state of the API process."""
    return HealthResponse(
        status="up",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description=(
        "Returns whether the API is prepared to process requests, including "
        "basic validation of the configured Codex runtime."
    ),
)
async def read_readiness(
    settings: AppSettings = Depends(get_settings),
    service: CodexExecutionService = Depends(get_codex_execution_service),
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> HealthResponse:
    """Return readiness information for orchestration and load balancers."""
    components = [
        component
        if isinstance(component, HealthComponent)
        else HealthComponent.model_validate(component)
        for component in [
            *auth_service.readiness_components(),
            *service.readiness_components(),
        ]
    ]
    status = (
        "up"
        if all(component.status == "up" for component in components)
        else "degraded"
    )
    return HealthResponse(
        status=status,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        components=components,
    )
