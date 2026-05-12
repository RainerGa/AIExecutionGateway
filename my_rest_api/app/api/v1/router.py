"""Versioned router assembly for v1 endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.codex import router as codex_router
from app.api.v1.endpoints.health import router as health_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(codex_router, tags=["codex"])
