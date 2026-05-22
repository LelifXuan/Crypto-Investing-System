from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.db import db_manager
from app.core.paths import app_paths, bootstrap_runtime_environment
from app.db.models.market import PageSnapshotCache
from app.middleware.local_only import LocalOnlyMiddleware
from app.repositories.auth_repository import AuthRepository
from app.repositories.bootstrap_repository import BootstrapRepository
from app.repositories.market_repository import MarketRepository
from app.services.bootstrap import seed_local_defaults, warm_local_market_data
from app.services.network.http_client_factory import init_network
from app.web.router import web_router


def _should_start_worker(name: str) -> bool:
    profile = settings.worker_profile.lower()
    if profile in {"none", "off", "disabled"}:
        return False
    if profile == "desktop_light":
        enabled = {"indicator_monitor", "precompute"}
        return name in enabled
    if profile == "desktop_full":
        enabled = {
            "event_bus",
            "market_stream",
            "indicator_monitor",
            "market_events_feed",
            "market_event_translation",
            "precompute",
        }
        return name in enabled
    return True


def _load_worker(name: str):
    if name == "event_bus":
        from app.events.bus import event_bus_worker

        return event_bus_worker
    if name == "market_stream":
        from app.workers.realtime_market import market_stream_worker

        return market_stream_worker
    if name == "indicator_monitor":
        from app.workers.indicator_monitor import indicator_monitor_worker

        return indicator_monitor_worker
    if name == "market_events_feed":
        from app.workers.market_events_feed import market_event_feed_worker

        return market_event_feed_worker
    if name == "market_event_translation":
        from app.workers.market_event_translation import market_event_translation_worker

        return market_event_translation_worker
    if name == "precompute":
        from app.workers.precompute_worker import precompute_worker

        return precompute_worker
    raise KeyError(name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    warmup_task: asyncio.Task | None = None
    warmup_instrument_ids: list[str] | None = None
    bootstrap_runtime_environment()
    init_network()
    await db_manager.connect()
    if settings.auto_create_schema:
        await db_manager.create_schema()
        await db_manager.ensure_schema_compatibility()
    if settings.precompute_enabled:
        await db_manager.create_tables(PageSnapshotCache.__table__)
    if settings.local_auto_bootstrap_enabled:
        async with db_manager.session() as session:
            market_repository = MarketRepository(session)
            instruments = await market_repository.list_instruments()
            if not instruments:
                result = await seed_local_defaults(
                    BootstrapRepository(session),
                    market_repository,
                    AuthRepository(session),
                )
                instruments = await market_repository.list_instruments()
                warmup_instrument_ids = [result.instrument_id]
            else:
                warmup_instrument_ids = [
                    next(
                        (
                            instrument.instrument_id
                            for instrument in instruments
                            if instrument.instrument_id == "btc-usdt-perp"
                        ),
                        instruments[0].instrument_id,
                    )
                ]
            if settings.local_bootstrap_warmup_all_instruments:
                warmup_instrument_ids = [instrument.instrument_id for instrument in instruments]
    if _should_start_worker("event_bus"):
        await _load_worker("event_bus").start()
    if _should_start_worker("market_stream"):
        await _load_worker("market_stream").start()
    if _should_start_worker("indicator_monitor"):
        await _load_worker("indicator_monitor").start()
    if _should_start_worker("market_events_feed"):
        await _load_worker("market_events_feed").start()
    if _should_start_worker("market_event_translation"):
        await _load_worker("market_event_translation").start()
    if _should_start_worker("precompute"):
        await _load_worker("precompute").start()
    if settings.local_auto_bootstrap_enabled and warmup_instrument_ids:

        async def run_startup_warmup(instrument_ids: list[str]) -> None:
            # Let interactive page requests and precompute hints take the lead first.
            await asyncio.sleep(8)
            async with db_manager.session() as warmup_session:
                warmup_repository = MarketRepository(warmup_session)
                for target_instrument_id in instrument_ids:
                    await warm_local_market_data(warmup_repository, target_instrument_id)

        warmup_task = asyncio.create_task(
            run_startup_warmup(warmup_instrument_ids),
            name="startup-market-warmup",
        )
    try:
        yield
    finally:
        if warmup_task is not None:
            warmup_task.cancel()
            with suppress(asyncio.CancelledError):
                await warmup_task
        for worker_name in (
            "precompute",
            "market_event_translation",
            "market_events_feed",
            "indicator_monitor",
            "market_stream",
            "event_bus",
        ):
            with suppress(Exception):
                await _load_worker(worker_name).stop()
        await db_manager.disconnect()


def create_app(*, enable_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan if enable_lifespan else None,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_openapi else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LocalOnlyMiddleware)

    app.include_router(api_router)
    app.include_router(web_router)

    @app.middleware("http")
    async def static_cache_control(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
        return response

    app.mount("/static", StaticFiles(directory=str(app_paths.static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/monitoring-page")

    return app


app = create_app()
