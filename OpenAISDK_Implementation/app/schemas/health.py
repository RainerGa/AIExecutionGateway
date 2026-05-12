"""Service health schemas for liveness and readiness endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class HealthComponent(BaseModel):
    """Represents the health of one runtime dependency or subsystem."""

    name: str
    status: str
    details: str


class HealthResponse(BaseModel):
    """Shared schema for liveness and readiness responses."""

    status: str = Field(..., description="Overall service state.")
    service: str = Field(..., description="Service name for dashboards and probes.")
    version: str = Field(..., description="Application version currently deployed.")
    environment: str = Field(..., description="Runtime environment identifier.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the health snapshot.",
    )
    components: list[HealthComponent] = Field(default_factory=list)
