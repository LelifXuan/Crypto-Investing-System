from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.encoders import jsonable_encoder

from app.quant.indicators import (
    adx_wilder_series,
    atr_wilder_series,
    bbands_series,
    ema_series,
    kdj_series,
    macd_series,
    obv_series,
    rsi_wilder_series,
)
from app.repositories.market_repository import MarketRepository
from app.services.cache_registry import (
    CACHE_SOURCE_VERSION,
    expires_at_for_dataset,
    indicator_series_cache_key,
)

UTC = timezone.utc


def _to_decimal_list(values: list) -> list[Decimal]:
    return [item if isinstance(item, Decimal) else Decimal(str(item)) for item in values]


def _field(item, key: str):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key)


def _to_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _series_to_json(values: list) -> list[float | None]:
    output: list[float | None] = []
    for item in values:
        if item is None:
            output.append(None)
        else:
            output.append(float(item))
    return output


def _rolling_change(values: list[Decimal | None], period: int) -> list[Decimal | None]:
    output: list[Decimal | None] = []
    for index, value in enumerate(values):
        if index < period or value is None or values[index - period] is None:
            output.append(None)
            continue
        output.append(value - values[index - period])
    return output


def _obv_slope(
    values: list[Decimal | None],
    volumes: list[Decimal],
    period: int = 5,
) -> list[Decimal | None]:
    output: list[Decimal | None] = []
    for index, value in enumerate(values):
        if index < period or value is None or values[index - period] is None:
            output.append(None)
            continue
        volume_window = volumes[max(0, index - period + 1) : index + 1]
        denominator = sum((abs(item) for item in volume_window), Decimal("0"))
        if denominator == 0:
            output.append(None)
            continue
        output.append((value - values[index - period]) / denominator)
    return output


def _adx_part(adx: dict, canonical: str, legacy: str):
    value = adx.get(canonical) or adx.get(legacy)
    if value is None:
        raise KeyError(f"ADX output missing {canonical}/{legacy}; keys={sorted(adx.keys())}")
    return value


def _cci_series(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    period: int = 20,
) -> list[Decimal | None]:
    typical = [
        (highs[index] + lows[index] + close) / Decimal("3")
        for index, close in enumerate(closes)
    ]
    series: list[Decimal | None] = []
    for index in range(len(typical)):
        if index + 1 < period:
            series.append(None)
            continue
        sample = typical[index - period + 1 : index + 1]
        mean = sum(sample, Decimal("0")) / Decimal(period)
        mean_deviation = sum(abs(item - mean) for item in sample) / Decimal(period)
        if mean_deviation == 0:
            series.append(Decimal("0"))
        else:
            series.append((typical[index] - mean) / (Decimal("0.015") * mean_deviation))
    return series


class ComputedDatasetCacheService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_or_build_indicator_series(
        self,
        *,
        instrument_id: str,
        timeframe: str,
        candles: list,
        indicator_group: str,
    ) -> dict:
        source_data_ts = _to_datetime(_field(candles[-1], "ts_open")) if candles else None
        cache_key = indicator_series_cache_key(
            instrument_id, timeframe, indicator_group, source_data_ts, CACHE_SOURCE_VERSION
        )
        cached = await self.repository.get_computed_dataset_cache(cache_key)
        if cached is not None and cached.payload_json and cached.cache_state in {"fresh", "ready"}:
            return cached.payload_json

        started = time.perf_counter()
        payload = self._build_indicator_series(candles, indicator_group)
        cost_ms = int((time.perf_counter() - started) * 1000)
        await self.repository.upsert_computed_dataset_cache(
            cache_key=cache_key,
            dataset_type=f"indicator_series_{indicator_group}",
            instrument_id=instrument_id,
            timeframe=timeframe,
            source_data_ts=source_data_ts,
            payload_json=jsonable_encoder(payload),
            cache_state="fresh",
            source_version=CACHE_SOURCE_VERSION,
            calculated_at=source_data_ts if source_data_ts else datetime.now(timezone.utc),
            expires_at=expires_at_for_dataset(f"indicator_series_{indicator_group}"),
            cost_ms=cost_ms,
            meta_json={"points": len(candles)},
        )
        payload["_cache"] = {"cost_ms": cost_ms, "cache_key": cache_key}
        return payload

    def _build_indicator_series(self, candles: list, indicator_group: str) -> dict:
        closes = _to_decimal_list([_field(item, "close") for item in candles])
        highs = _to_decimal_list([_field(item, "high") for item in candles])
        lows = _to_decimal_list([_field(item, "low") for item in candles])
        volumes = _to_decimal_list([_field(item, "volume") for item in candles])
        if indicator_group == "core":
            macd = macd_series(closes)
            atr = atr_wilder_series(highs, lows, closes, 14)
            return {
                "ema_20": _series_to_json(ema_series(closes, 20).series),
                "ema_50": _series_to_json(ema_series(closes, 50).series),
                "ema_200": _series_to_json(ema_series(closes, 200).series),
                "ema_30": _series_to_json(ema_series(closes, 30).series),
                "ema_60": _series_to_json(ema_series(closes, 60).series),
                "ema_120": _series_to_json(ema_series(closes, 120).series),
                "ema_12": _series_to_json(ema_series(closes, 12).series),
                "rsi_14": _series_to_json(rsi_wilder_series(closes, 14).series),
                "macd_line": _series_to_json(macd.macd.series),
                "macd_signal": _series_to_json(macd.signal.series),
                "macd_hist": _series_to_json(macd.histogram.series),
                "atr_14": _series_to_json(atr.series),
                "natr_14": _series_to_json(
                    [
                        ((value / close) * Decimal("100")) if value is not None and close else None
                        for value, close in zip(atr.series, closes, strict=False)
                    ]
                ),
            }
        adx = adx_wilder_series(highs, lows, closes, 14)
        boll = bbands_series(closes, 20, Decimal("2"))
        kdj = kdj_series(highs, lows, closes, 9)
        obv_values = obv_series(closes, volumes).series
        return {
            "bbands_upper": _series_to_json(boll.upper.series),
            "bbands_middle": _series_to_json(boll.middle.series),
            "bbands_lower": _series_to_json(boll.lower.series),
            "bbands_width": _series_to_json(boll.bandwidth.series),
            "percent_b": _series_to_json(boll.percent_b.series),
            "adx_14": _series_to_json(adx["adx"].series),
            "plus_di": _series_to_json(_adx_part(adx, "plus_di", "+di").series),
            "minus_di": _series_to_json(_adx_part(adx, "minus_di", "-di").series),
            "obv": _series_to_json(obv_values),
            "obv_change_5": _series_to_json(_rolling_change(obv_values, 5)),
            "obv_slope": _series_to_json(_obv_slope(obv_values, volumes, 5)),
            "kdj_k": _series_to_json(kdj.k.series),
            "kdj_d": _series_to_json(kdj.d.series),
            "kdj_j": _series_to_json(kdj.j.series),
            "cci_20": _series_to_json(_cci_series(highs, lows, closes, 20)),
            "volume": _series_to_json(volumes),
        }
