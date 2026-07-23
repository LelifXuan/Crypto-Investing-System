from __future__ import annotations

from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest
from app.services.cache_registry import strategy_unified_cache_key
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.indicators import IndicatorService
from app.services.precompute import precompute_service
from app.services.strategy_unified.trade_decision import reconcile_cached_strategy


async def handle_domain_event(session, event) -> None:
    payload = event.payload
    event_type = event.event_type

    if event_type == "market.candle.closed":
        market_repo = MarketRepository(session)
        policies = await market_repo.list_indicator_refresh_policies(
            instrument_id=str(payload["instrument_id"]),
            timeframe=str(payload["timeframe"]),
            enabled_only=True,
        )
        indicator_service = IndicatorService(market_repo)
        for policy in policies:
            await indicator_service.run_policy(policy)
        monitoring_service = IndicatorMonitoringService(market_repo)
        await monitoring_service.sync_technical(
            instrument_id=str(payload["instrument_id"]),
            timeframe=str(payload["timeframe"]),
        )
        if str(payload["timeframe"]) in {"15m", "1h", "4h"}:
            await precompute_service.enqueue_hint(
                PrecomputeHintRequest(
                    current_page="strategy",
                    instrument_id=str(payload["instrument_id"]),
                    timeframe=str(payload["timeframe"]),
                    reason="strategy_period_close",
                    visible=False,
                    candidates=["market_context", "strategy_unified"],
                    priority=2,
                )
            )
        return

    if event_type == "market.mark_price.updated":
        instrument_id = str(payload["instrument_id"])
        market_repo = MarketRepository(session)
        cache = await market_repo.get_page_snapshot_cache(
            strategy_unified_cache_key(instrument_id)
        )
        if cache is None or not cache.payload_json:
            return
        _, invalidated = reconcile_cached_strategy(
            dict(cache.payload_json),
            latest_price=float(payload["mark_price"]),
            price_as_of=str(payload.get("ts_event") or event.ts_event.isoformat()),
            price_source=str(payload.get("source") or event.source),
        )
        if invalidated:
            await precompute_service.enqueue_hint(
                PrecomputeHintRequest(
                    current_page="strategy",
                    instrument_id=instrument_id,
                    timeframe="1d",
                    reason="strategy_price_level_crossed",
                    visible=False,
                    candidates=["strategy_unified"],
                    priority=1,
                )
            )
