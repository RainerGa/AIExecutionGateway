"""Version 1 endpoint for Codex-backed task execution."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, status

from app.api.dependencies import (
    get_codex_execution_service,
    get_request_id,
    require_task_execution_principal,
)
from app.schemas.codex import TaskExecutionRequest, TaskExecutionResponse
from app.schemas.errors import ErrorResponse
from app.security.models import UserPrincipal
from app.services.codex_service import CodexExecutionService

router = APIRouter()


@router.post(
    "/execute_task",
    response_model=TaskExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute a task using OpenAI Codex",
    description=(
        "Accepts a task description, forwards it to the configured Codex runtime, "
        "and returns the final response together with execution metadata."
    ),
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Codex rejected the task as a logical request error.",
        },
        401: {
            "model": ErrorResponse,
            "description": "Authentication is required or provided credentials are invalid.",
        },
        403: {
            "model": ErrorResponse,
            "description": "The authenticated user is not authorized to execute tasks.",
        },
        422: {
            "model": ErrorResponse,
            "description": "The HTTP request payload does not match the API contract.",
        },
        500: {
            "model": ErrorResponse,
            "description": "The execution failed internally or the service is misconfigured.",
        },
        503: {
            "model": ErrorResponse,
            "description": "The Codex runtime is temporarily overloaded or unavailable.",
        },
    },
)
async def execute_task(
    request: TaskExecutionRequest = Body(
        ...,
        description="The task description to execute using OpenAI Codex.",
    ),
    service: CodexExecutionService = Depends(get_codex_execution_service),
    request_id: str = Depends(get_request_id),
    principal: UserPrincipal = Depends(require_task_execution_principal),
) -> TaskExecutionResponse:
    """Execute a single task request using the service layer."""
    return service.execute_task(request, request_id=request_id, principal=principal)
