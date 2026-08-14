from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RefreshStatus = Literal["queued", "running", "success", "failed", "missing"]


class RefreshReceipt(BaseModel):
    job_id: str
    scope: str
    status: RefreshStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    poll_after_ms: int = 750
    result_cache_key: str | None = None
    error: str | None = None
