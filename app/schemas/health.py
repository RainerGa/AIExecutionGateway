"""Service health schemas for liveness and readiness endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class HealthComponent(BaseModel):
    """Represents the health of one runtime dependency or subsystem.

    Attributes:
        name: Name of the component (e.g., "codex_runtime").
        status: Current state ("up", "down", or "degraded").
        details: Human-readable status details or error messages.
    """

    name: str
    status: str
    details: str


class HealthResponse(BaseModel):
    """Shared schema for liveness and readiness responses.

    Attributes:
        status: Overall service state ("up" or "degraded").
        service: Display name of the service.
        version: Application version.
        environment: Deployment environment name.
        timestamp: UTC timestamp of the health check.
        components: Detailed health state of individual subsystems.
    """

    status: str = Field(..., description="Overall service state.")
    service: str = Field(..., description="Service name for dashboards and probes.")
    version: str = Field(..., description="Application version currently deployed.")
    environment: str = Field(..., description="Runtime environment identifier.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the health snapshot.",
    )
    components: list[HealthComponent] = Field(default_factory=list)
