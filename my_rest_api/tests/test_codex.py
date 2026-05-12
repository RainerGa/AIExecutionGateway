"""Endpoint-level tests for route handlers and API-facing contracts."""

from __future__ import annotations

import asyncio

from app.api.v1.endpoints.codex import execute_task
from app.schemas.codex import TaskExecutionMetadata, TaskExecutionRequest, TaskExecutionResponse
from tests.support import build_test_principal


class StubCodexExecutionService:
    """Minimal service stub used to isolate the endpoint contract."""

    def execute_task(
        self,
        request: TaskExecutionRequest,
        *,
        request_id: str,
        principal,
    ) -> TaskExecutionResponse:
        return TaskExecutionResponse(
            result=f"processed: {request.task_description}",
            metadata=TaskExecutionMetadata(
                request_id=request_id,
                model="test-model",
                duration_ms=1,
            ),
        )


def test_execute_task_endpoint_delegates_to_service():
    """The endpoint should delegate work to the injected service instance."""
    response = asyncio.run(
        execute_task(
            request=TaskExecutionRequest(task_description="Say hello in one sentence."),
            service=StubCodexExecutionService(),
            request_id="req-endpoint-1",
            principal=build_test_principal(),
        )
    )

    assert response.model_dump()["result"] == "processed: Say hello in one sentence."
    assert response.model_dump()["metadata"]["request_id"] == "req-endpoint-1"
