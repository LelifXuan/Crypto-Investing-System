from __future__ import annotations

import asyncio
import logging
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
from app.schemas.market import PrecomputeHintRequest
from app.services.bootstrap import seed_local_defaults, warm_local_market_data
from app.services.network.http_client_factory import init_network
from app.services.precompute import precompute_service
from app.web.router import web_router

logger = logging.getLogger(__name__)

STRATEGY_CRITICAL_WARMUP_PLAN = (
    ("strategy", ["strategy", "market_context"], ("30d", "1w", "1d", "4h", "1h", "15m")),
    ("analysis", ["analysis"], ("1w", "1d", "4h", "1h")),
    ("structure", ["structure"], ("1w", "1d", "4h", "1h")),
    ("monitoring", ["monitoring"], ("1d",)),
    ("macro", ["macro"], ("1d",)),
    ("events", ["events"], ("1d",)),
)


async def _enqueue_strategy_critical_warmup(
    instrument_ids: list[str],
    *,
    reason: str,
    priority: int,
    initial_delay_seconds: float = 0.0,
) -> None:
    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)
    for target_instrument_id in instrument_ids:
        for page, candidates, timeframes in STRATEGY_CRITICAL_WARMUP_PLAN:
            for timeframe in timeframes:
                await precompute_service.enqueue_hint(
                    PrecomputeHintRequest(
                        current_page=page,
                        instrument_id=target_instrument_id,
                        timeframe=timeframe,
                        reason=reason,
                        visible=False,
                        candidates=list(candidates),
                        priority=priority,
                    )
                )
    await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="btc-derivatives",
            reason=reason,
            visible=False,
            candidates=["btc_derivatives"],
            priority=priority,
        )
    )
    # Unified synthesis consumes the strategy timeframes and BTC derivatives
    # queued above. Keep it last so a cold start cannot publish an empty but
    # apparently fresh cross-validation matrix.
    for target_instrument_id in instrument_ids:
        await precompute_service.enqueue_hint(
            PrecomputeHintRequest(
                current_page="strategy",
                instrument_id=target_instrument_id,
                timeframe="1d",
                reason=reason,
                visible=False,
                candidates=["strategy_unified"],
                priority=priority,
            )
        )


def _should_start_worker(name: str) -> bool:
    profile = settings.worker_profile.lower()
    if profile in {"none", "off", "disabled"}:
        return False
    if profile == "desktop_light":
        enabled = {
            "indicator_monitor", "precompute", "market_event_translation", "market_events_feed"
        }
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
    cold_source_start = False
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
            probe_instrument_id = warmup_instrument_ids[0]
            cold_source_start = not bool(
                await market_repository.list_candles(
                    probe_instrument_id,
                    "1d",
                    limit=1,
                )
            )
    worker_names = [
        ("event_bus", "event_bus"),
        ("market_stream", "market_stream"),
        ("indicator_monitor", "indicator_monitor"),
        ("market_events_feed", "market_events_feed"),
        ("market_event_translation", "market_event_translation"),
        ("precompute", "precompute"),
    ]
    async def start_workers() -> None:
        for profile_key, worker_name in worker_names:
            if _should_start_worker(profile_key):
                try:
                    await _load_worker(profile_key).start()
                    logger.info("worker %s: started", worker_name)
                except Exception:
                    logger.exception("worker %s: failed to start", worker_name)
            else:
                logger.info(
                    "worker %s: skipped (profile=%s)",
                    worker_name,
                    settings.worker_profile,
                )

    if cold_source_start:
        logger.info("cold source database detected; deferring workers until source warmup")
    else:
        await start_workers()
    logger.info(
        "startup complete: profile=%s workers=%d warmup=%s",
        settings.worker_profile,
        sum(1 for k, _ in worker_names if _should_start_worker(k)),
        bool(warmup_instrument_ids),
    )
    if settings.local_auto_bootstrap_enabled and warmup_instrument_ids:

        async def run_startup_warmup(instrument_ids: list[str]) -> None:
            await _enqueue_strategy_critical_warmup(
                instrument_ids,
                reason="startup_critical_snapshot",
                priority=3,
                initial_delay_seconds=1.0,
            )
            if cold_source_start:
                for target_instrument_id in instrument_ids:
                    # A genuinely cold database has no candles for queued
                    # analysis/strategy work. Rebuild sources before allowing
                    # any derived writer worker to consume the queue.
                    async with db_manager.writer_session() as session:
                        await warm_local_market_data(
                            MarketRepository(session), target_instrument_id
                        )
                await start_workers()
            else:
                await asyncio.sleep(45)
            for target_instrument_id in instrument_ids:
                await precompute_service.enqueue_hint(
                    PrecomputeHintRequest(
                        current_page="strategy",
                        instrument_id=target_instrument_id,
                        timeframe="1d",
                        reason="startup_strategy_snapshot_finalize",
                        visible=False,
                        candidates=["strategy_unified"],
                        priority=2,
                    )
                )

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
        version=settings.app_version,
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

    from app.core.http_cache import revalidate_frontend

    app.middleware("http")(revalidate_frontend)

    app.mount("/static", StaticFiles(directory=str(app_paths.static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/monitoring-page")

    return app


app = create_app()
