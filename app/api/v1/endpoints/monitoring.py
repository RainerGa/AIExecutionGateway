"""Admin monitoring endpoints for live runtime visibility."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_monitoring_service, require_admin_principal
from app.schemas.monitoring import MonitoringSnapshot
from app.security.models import UserPrincipal
from app.services.monitoring_service import MonitoringService

router = APIRouter()


@router.get(
    "/monitoring/snapshot",
    response_model=MonitoringSnapshot,
    status_code=status.HTTP_200_OK,
    summary="Read the current live monitoring snapshot",
)
async def read_monitoring_snapshot(
    _: UserPrincipal = Depends(require_admin_principal),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> MonitoringSnapshot:
    """Return the current monitoring state snapshot for administrators."""
    return monitoring_service.snapshot()


@router.get(
    "/monitoring/events",
    status_code=status.HTTP_200_OK,
    summary="Stream live monitoring events",
)
async def stream_monitoring_events(
    _: UserPrincipal = Depends(require_admin_principal),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    last_event_id: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """Expose monitoring events as a lightweight server-sent event stream."""

    async def event_generator():
        cursor = last_event_id
        while True:
            events = monitoring_service.events_after(cursor)
            if events:
                for event in events:
                    cursor = event.event_id
                    yield (
                        f"id: {event.event_id}\n"
                        f"event: {event.event_type}\n"
                        f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
                    )
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(monitoring_service.refresh_interval_ms / 1000)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
