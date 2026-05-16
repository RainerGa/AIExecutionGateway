"""Version 1 router assembly.

This module aggregates all version 1 endpoints (health, codex, monitoring)
into a single router instance.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.codex import router as codex_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.monitoring import router as monitoring_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(codex_router, tags=["codex"])
router.include_router(monitoring_router, tags=["monitoring"])
