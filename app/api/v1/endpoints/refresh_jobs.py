from __future__ import annotations

from fastapi import APIRouter

from app.schemas.refresh import RefreshReceipt
from app.services.refresh_jobs import refresh_job_service

router = APIRouter(prefix="/refresh-jobs", tags=["refresh-jobs"])


@router.get("/{job_id}", response_model=RefreshReceipt)
async def get_refresh_job(job_id: str) -> RefreshReceipt:
    return refresh_job_service.status(job_id)
