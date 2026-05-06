from __future__ import annotations

from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.indicators import IndicatorService


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
