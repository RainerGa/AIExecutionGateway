"""Top-level router composition for all API versions."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.router import router as v1_router
from app.core.config import AppSettings


def build_api_router(settings: AppSettings) -> APIRouter:
    """Assemble the public router tree using runtime configuration."""
    router = APIRouter()
    router.include_router(v1_router, prefix=settings.api_prefix)
    return router
