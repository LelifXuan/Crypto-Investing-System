from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import CurrentUser, require_roles
from app.schemas.market import (
    PrecomputeHintRequest,
    PrecomputeHintResponse,
    PrecomputeStatusRead,
    PrecomputeTaskRead,
)
from app.services.precompute import precompute_service

router = APIRouter(prefix="/precompute", tags=["precompute"])


@router.post("/hint", response_model=PrecomputeHintResponse)
async def queue_precompute_hint(
    payload: PrecomputeHintRequest,
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await precompute_service.enqueue_hint(payload)


@router.get("/status", response_model=PrecomputeStatusRead)
async def get_precompute_status(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await precompute_service.status()


@router.get("/tasks/{task_key}", response_model=PrecomputeTaskRead)
async def get_precompute_task_status(
    task_key: str,
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await precompute_service.task_status(task_key)
