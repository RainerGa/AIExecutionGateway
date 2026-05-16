"""Application factory and runtime bootstrap for the Codex REST API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import register_exception_handlers
from app.api.router import build_api_router
from app.core.config import AppSettings, get_settings
from app.core.logging import configure_logging
from app.core.request_context import reset_request_id, set_request_id
from app.services.monitoring_service import MonitoringService

LOGGER = logging.getLogger(__name__)


def create_application(settings: AppSettings | None = None) -> FastAPI:
    """Builds the FastAPI application with shared middleware and handlers.

    This factory function initializes the logging system, configures the
    FastAPI app instance, attaches global middleware (CORS, Request Context),
    registers exception handlers, and includes the versioned API routers.

    Args:
        settings: Optional application settings. If not provided, they will
            be loaded from the environment/config file.

    Returns:
        A fully configured `FastAPI` application instance.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manages the application lifecycle (startup and shutdown)."""
        LOGGER.info(
            "Starting service. environment=%s api_prefix=%s",
            settings.environment,
            settings.api_prefix,
        )
        yield
        LOGGER.info("Stopping service.")

    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        lifespan=lifespan,
    )
    app.state.monitoring_service = MonitoringService(settings.monitoring)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        """Middleware to manage request-scoped correlation IDs and monitoring."""
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        token = set_request_id(request_id)
        start = perf_counter()
        app.state.monitoring_service.record_request_started(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(
            int((perf_counter() - start) * 1000)
        )
        return response

    @app.get("/", include_in_schema=False)
    async def root() -> Response:
        """Root health check endpoint returning 204 No Content."""
        return Response(status_code=204)

    app.dependency_overrides[get_settings] = lambda: settings
    register_exception_handlers(app)
    app.include_router(build_api_router(settings))
    return app


app = create_application()
