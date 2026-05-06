from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal, getcontext

from app.core.config import settings
from app.core.decimal_utils import D
from app.db.models.market import IndicatorRefreshPolicy, IndicatorValue, MarketCandle
from app.quant.indicators import bbands_series, ema_series, macd_series, rsi_wilder_series
from app.repositories.market_repository import MarketRepository
from app.services.market import MarketService

getcontext().prec = 28

DEFAULT_INDICATOR_PARAMETERS = {
    "ema_window": 14,
    "rsi_window": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "bbands_window": 20,
    "bbands_stddev": Decimal("2"),
}
SUPPORTED_INDICATOR_TIMEFRAMES = ("1h", "4h", "1d", "1w", "30d")


class IndicatorService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def calculate_all(
        self,
        instrument_id: str,
        timeframe: str,
        ema_window: int,
        rsi_window: int,
        macd_fast: int,
        macd_slow: int,
        macd_signal: int,
        bbands_window: int,
        bbands_stddev: Decimal,
        source_preference: str = "gateio",
        fetch_limit: int = 300,
        persist_candles: bool = True,
        price_kind: str = "last",
    ) -> list[IndicatorValue]:
        candles: list[MarketCandle]
        if source_preference.lower() == "gateio":
            market_service = MarketService(self.repository)
            candles = await market_service.sync_candles_from_provider(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=fetch_limit,
                price_kind=price_kind,
                persist=persist_candles,
            )
        else:
            candles = await self.repository.list_candles(
                instrument_id=instrument_id, timeframe=timeframe, limit=500
            )

        closes = [D(c.close) for c in candles]
        if not candles:
            return []

        ts_value = candles[-1].ts_open
        results = [
            await self._persist(
                instrument_id,
                timeframe,
                "EMA",
                ts_value,
                self._series_payload(
                    ema_series(closes, ema_window),
                    {"window": ema_window, "source": source_preference, "price_kind": price_kind},
                ),
            ),
            await self._persist(
                instrument_id,
                timeframe,
                "RSI",
                ts_value,
                self._series_payload(
                    rsi_wilder_series(closes, rsi_window),
                    {"window": rsi_window, "source": source_preference, "price_kind": price_kind},
                ),
            ),
        ]

        macd_result = macd_series(closes, macd_fast, macd_slow, macd_signal)
        results.append(
            await self._persist(
                instrument_id,
                timeframe,
                "MACD",
                ts_value,
                {
                    "fast": macd_fast,
                    "slow": macd_slow,
                    "signal": macd_signal,
                    "source": source_preference,
                    "price_kind": price_kind,
                    "macd": str(macd_result.macd.value),
                    "signal_line": str(macd_result.signal.value),
                    "histogram": str(macd_result.histogram.value),
                    "warmup": macd_result.histogram.warmup,
                    "lookback_ready": macd_result.histogram.lookback_ready,
                    "is_immature": macd_result.histogram.is_immature,
                },
            )
        )

        bands = bbands_series(closes, bbands_window, bbands_stddev)
        results.append(
            await self._persist(
                instrument_id,
                timeframe,
                "BBANDS",
                ts_value,
                {
                    "window": bbands_window,
                    "stddev": str(bbands_stddev),
                    "source": source_preference,
                    "price_kind": price_kind,
                    "middle": str(bands.middle.value),
                    "upper": str(bands.upper.value),
                    "lower": str(bands.lower.value),
                    "bandwidth": str(bands.bandwidth.value),
                    "percent_b": str(bands.percent_b.value),
                    "warmup": bands.middle.warmup,
                    "lookback_ready": bands.middle.lookback_ready,
                    "is_immature": bands.middle.is_immature,
                },
            )
        )
        return results

    async def run_policy(self, policy: IndicatorRefreshPolicy) -> list[IndicatorValue]:
        params = self.merge_parameters(policy.parameters_json)
        return await self.calculate_all(
            instrument_id=policy.instrument_id,
            timeframe=policy.timeframe,
            source_preference=policy.source_preference,
            fetch_limit=policy.fetch_limit,
            persist_candles=policy.persist_candles,
            price_kind=policy.price_kind,
            **params,
        )

    async def ensure_indicator_data(
        self,
        instrument_id: str,
        timeframe: str,
        indicator_name: str | None = None,
        limit: int = 50,
        auto_calculate: bool = True,
    ) -> tuple[list[IndicatorValue], bool]:
        values = await self.repository.list_indicator_values(
            instrument_id=instrument_id,
            timeframe=timeframe,
            indicator_name=indicator_name,
            limit=limit,
        )
        refreshed = False
        if values:
            newest = max(values, key=lambda item: item.ts_value)
            newest_ts = newest.ts_value
            if newest_ts.tzinfo is None:
                newest_ts = newest_ts.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - newest_ts).total_seconds()
            if age_seconds <= settings.indicator_refresh_interval_seconds or not auto_calculate:
                return values, refreshed
        elif not auto_calculate:
            return values, refreshed

        await self.calculate_all(
            instrument_id=instrument_id,
            timeframe=timeframe,
            source_preference="gateio",
            fetch_limit=300,
            persist_candles=True,
            price_kind="last",
            **self.default_parameters(),
        )
        refreshed = True
        return (
            await self.repository.list_indicator_values(
                instrument_id=instrument_id,
                timeframe=timeframe,
                indicator_name=indicator_name,
                limit=limit,
            ),
            refreshed,
        )

    @staticmethod
    def default_parameters() -> dict:
        return dict(DEFAULT_INDICATOR_PARAMETERS)

    @staticmethod
    def merge_parameters(overrides: dict | None = None) -> dict:
        merged = IndicatorService.default_parameters()
        for key, value in (overrides or {}).items():
            if key == "bbands_stddev":
                merged[key] = Decimal(str(value))
            elif key in merged:
                merged[key] = int(value)
        return merged

    async def _persist(
        self,
        instrument_id: str,
        timeframe: str,
        indicator_name: str,
        ts_value: datetime,
        value_json: dict,
    ) -> IndicatorValue:
        params_hash = hashlib.md5(str(sorted(value_json.items())).encode("utf-8")).hexdigest()
        model = IndicatorValue(
            instrument_id=instrument_id,
            timeframe=timeframe,
            indicator_name=indicator_name,
            params_hash=params_hash,
            ts_value=ts_value,
            value_json=value_json,
        )
        return await self.repository.add_indicator_value(model)

    @staticmethod
    def _series_payload(result, payload: dict) -> dict:
        enriched = dict(payload)
        enriched["value"] = str(result.value)
        enriched["warmup"] = result.warmup
        enriched["lookback_ready"] = result.lookback_ready
        enriched["is_immature"] = result.is_immature
        return enriched

    def ema(self, values: Sequence[Decimal], window: int) -> Decimal:
        return ema_series(values, window).value

    def rsi(self, values: Sequence[Decimal], window: int) -> Decimal:
        return rsi_wilder_series(values, window).value

    def macd(
        self, values: Sequence[Decimal], fast: int, slow: int, signal: int
    ) -> tuple[Decimal, Decimal, Decimal]:
        result = macd_series(values, fast, slow, signal)
        return result.macd.value, result.signal.value, result.histogram.value

    def bollinger_bands(
        self, values: Sequence[Decimal], window: int, stddev: Decimal
    ) -> tuple[Decimal, Decimal, Decimal]:
        result = bbands_series(values, window, stddev)
        return result.middle.value, result.upper.value, result.lower.value
