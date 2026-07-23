from __future__ import annotations

from app.repositories.market_repository import MarketRepository
from app.services.computed_dataset_cache import ComputedDatasetCacheService
from app.services.market_data_bundle import MarketDataBundleService


class IndicatorMatrixService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.dataset_cache = ComputedDatasetCacheService(repository)
        self.market_data = MarketDataBundleService(repository)

    async def get_matrix(
        self,
        *,
        instrument_id: str,
        timeframe: str,
        limit: int,
    ) -> dict:
        market_bundle = await self.market_data.get_bundle(
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=limit,
            allow_stale=True,
            refresh=False,
        )
        candles = market_bundle.get("candles", [])
        core = await self.dataset_cache.get_or_build_indicator_series(
            instrument_id=instrument_id,
            timeframe=timeframe,
            candles=candles,
            indicator_group="core",
        )
        secondary = await self.dataset_cache.get_or_build_indicator_series(
            instrument_id=instrument_id,
            timeframe=timeframe,
            candles=candles,
            indicator_group="secondary",
        )
        maturity = {
            "vegas_576": "ready" if len(candles) >= 576 else "immature",
            "vegas_676": "ready" if len(candles) >= 676 else "immature",
        }
        return {
            "instrument_id": instrument_id,
            "timeframe": market_bundle.get("cache_timeframe", timeframe),
            "source_max_ts": market_bundle.get("source_max_ts"),
            "cache_state": market_bundle.get("cache_state", "missing"),
            "series": {
                **core,
                **secondary,
            },
            "maturity": maturity,
        }
