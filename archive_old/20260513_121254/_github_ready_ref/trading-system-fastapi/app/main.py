from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.db import db_manager
from app.events.bus import event_bus_worker
from app.middleware.idempotency import FillIdempotencyMiddleware
from app.middleware.localhost_only import LocalhostOnlyMiddleware
from app.workers.market_events import market_event_poll_worker
from app.workers.realtime_market import market_stream_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_manager.connect()
    await event_bus_worker.start()
    await market_stream_worker.start()
    await market_event_poll_worker.start()
    try:
        yield
    finally:
        await market_event_poll_worker.stop()
        await market_stream_worker.stop()
        await event_bus_worker.stop()
        await db_manager.disconnect()


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(LocalhostOnlyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(FillIdempotencyMiddleware)

app.include_router(api_router)


@app.get("/", tags=["root"])
async def root() -> dict[str, str | bool]:
    return {
        "message": "Trading System API is running.",
        "single_user_mode": settings.single_user_mode,
        "local_only_enforced": settings.local_only_enforced,
    }
