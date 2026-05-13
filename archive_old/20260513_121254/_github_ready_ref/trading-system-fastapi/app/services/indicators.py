from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.core.decimal_utils import D, DECIMAL_ZERO
from app.db.models.market import IndicatorRefreshPolicy, IndicatorValue
from app.repositories.market_repository import MarketRepository
from app.services.market import MarketService


class IndicatorService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.market_service = MarketService(repository)

    async def calculate_all(
        self,
        instrument_id: str,
        timeframe: str,
        source_preference: str = "gateio",
        fetch_limit: int = 300,
        persist_candles: bool = True,
        price_kind: str = "last",
        sma_window: int = 14,
        ema_window: int = 14,
        rsi_window: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bbands_window: int = 20,
        bbands_stddev: Decimal = Decimal("2"),
    ) -> list[IndicatorValue]:
        if source_preference.lower() == "gateio":
            candles = await self.market_service.sync_candles_from_provider(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=fetch_limit,
                price_kind=price_kind,
                persist=persist_candles,
            )
        else:
            candles = await self.repository.list_candles(instrument_id=instrument_id, timeframe=timeframe, limit=500)

        closes = [D(c.close) for c in candles]
        if not candles:
            return []

        ts_value = candles[-1].ts_open
        results = [
            await self._persist(
                instrument_id,
                timeframe,
                "SMA",
                ts_value,
                {"window": sma_window, "source": source_preference, "price_kind": price_kind, "value": str(self.sma(closes, sma_window))},
            ),
            await self._persist(
                instrument_id,
                timeframe,
                "EMA",
                ts_value,
                {"window": ema_window, "source": source_preference, "price_kind": price_kind, "value": str(self.ema(closes, ema_window))},
            ),
            await self._persist(
                instrument_id,
                timeframe,
                "RSI",
                ts_value,
                {"window": rsi_window, "source": source_preference, "price_kind": price_kind, "value": str(self.rsi(closes, rsi_window))},
            ),
        ]

        macd_line, signal_line, histogram = self.macd(closes, macd_fast, macd_slow, macd_signal)
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
                    "macd": str(macd_line),
                    "signal_line": str(signal_line),
                    "histogram": str(histogram),
                },
            )
        )

        middle, upper, lower = self.bollinger_bands(closes, bbands_window, bbands_stddev)
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
                    "middle": str(middle),
                    "upper": str(upper),
                    "lower": str(lower),
                },
            )
        )
        return results

    async def calculate_from_policy(self, policy: IndicatorRefreshPolicy) -> list[IndicatorValue]:
        params = {
            "sma_window": 14,
            "ema_window": 14,
            "rsi_window": 14,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bbands_window": 20,
            "bbands_stddev": Decimal("2"),
        }
        raw_params = policy.parameters_json or {}
        for key in list(params):
            if key not in raw_params:
                continue
            params[key] = Decimal(str(raw_params[key])) if key == "bbands_stddev" else int(raw_params[key])
        return await self.calculate_all(
            instrument_id=policy.instrument_id,
            timeframe=policy.timeframe,
            source_preference=policy.source_preference,
            fetch_limit=policy.fetch_limit,
            persist_candles=policy.persist_candles,
            price_kind=policy.price_kind,
            **params,
        )

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

    def sma(self, values: Sequence[Decimal], window: int) -> Decimal:
        chunk = values[-window:] if len(values) >= window else values
        return sum(chunk, DECIMAL_ZERO) / Decimal(len(chunk)) if chunk else DECIMAL_ZERO

    def ema(self, values: Sequence[Decimal], window: int) -> Decimal:
        if not values:
            return DECIMAL_ZERO
        multiplier = Decimal("2") / (Decimal(window) + Decimal("1"))
        ema_value = values[0]
        for price in values[1:]:
            ema_value = (price - ema_value) * multiplier + ema_value
        return ema_value

    def rsi(self, values: Sequence[Decimal], window: int) -> Decimal:
        if len(values) < 2:
            return DECIMAL_ZERO
        deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
        sample = deltas[-window:] if len(deltas) >= window else deltas
        gains = sum((d for d in sample if d > 0), DECIMAL_ZERO)
        losses = abs(sum((d for d in sample if d < 0), DECIMAL_ZERO))
        if losses == 0:
            return Decimal("100")
        rs = gains / losses
        return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

    def macd(self, values: Sequence[Decimal], fast: int, slow: int, signal: int) -> tuple[Decimal, Decimal, Decimal]:
        if not values:
            return DECIMAL_ZERO, DECIMAL_ZERO, DECIMAL_ZERO
        macd_series: list[Decimal] = []
        for i in range(1, len(values) + 1):
            subset = values[:i]
            macd_series.append(self.ema(subset, fast) - self.ema(subset, slow))
        macd_line = macd_series[-1]
        signal_line = self.ema(macd_series, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def bollinger_bands(self, values: Sequence[Decimal], window: int, stddev: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        chunk = values[-window:] if len(values) >= window else values
        if not chunk:
            return DECIMAL_ZERO, DECIMAL_ZERO, DECIMAL_ZERO
        mean = sum(chunk, DECIMAL_ZERO) / Decimal(len(chunk))
        variance = sum(((v - mean) ** 2 for v in chunk), DECIMAL_ZERO) / Decimal(len(chunk))
        std = variance.sqrt()
        return mean, mean + (std * stddev), mean - (std * stddev)
