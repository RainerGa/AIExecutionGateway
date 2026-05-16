"""Top-level router composition for all API versions."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.router import router as v1_router
from app.core.config import AppSettings


def build_api_router(settings: AppSettings) -> APIRouter:
    """Assembles the public router tree using runtime configuration.

    This function creates the root `APIRouter` and includes versioned
    sub-routers (like V1) with the configured API prefix.

    Args:
        settings: The current application settings, used for the API prefix.

    Returns:
        A fully configured `APIRouter` instance.
    """
    router = APIRouter()
    router.include_router(v1_router, prefix=settings.api_prefix)
    return router
