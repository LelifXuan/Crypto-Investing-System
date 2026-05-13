from fastapi import APIRouter, HTTPException

from app.core.db import db_manager

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    try:
        await db_manager.ping()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"database not ready: {exc}") from exc
    return {"status": "ready"}
