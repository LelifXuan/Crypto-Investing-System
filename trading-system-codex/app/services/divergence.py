from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.core.decimal_utils import DECIMAL_ZERO
from app.quant.indicators import (
    adx_wilder_series,
    atr_wilder_series,
    ema_series,
    macd_series,
    obv_series,
    rsi_wilder_series,
    sma_series,
)

UTC = timezone.utc
logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _to_float(value: Decimal | None) -> float:
    return float(value or DECIMAL_ZERO)


@dataclass(slots=True)
class Pivot:
    index: int
    ts: datetime
    price: float
    kind: str


class DivergenceService:
    WEIGHTS = {"RSI": 0.25, "MACD": 0.25, "OBV": 0.20, "CCI": 0.15, "KDJ": 0.10}
    COOLDOWN_BY_TIMEFRAME = {"1h": 6, "4h": 4, "1d": 3, "1w": 2, "1M": 1}

    def analyze(
        self,
        instrument_id: str,
        timeframe: str,
        candles: list,
        indicator_matrix: dict | None = None,
    ) -> dict:
        if len(candles) < 40:
            return self._empty_payload(instrument_id, timeframe, "insufficient_data")
        closes = [_to_decimal(_field(item, "close")) for item in candles]
        highs = [_to_decimal(_field(item, "high")) for item in candles]
        lows = [_to_decimal(_field(item, "low")) for item in candles]
        volumes = [_to_decimal(_field(item, "volume")) for item in candles]
        price_highs, price_lows = self._price_pivots(candles, highs, lows)
        if len(price_highs) < 2 and len(price_lows) < 2:
            return self._empty_payload(instrument_id, timeframe, "insufficient_pivots")

        series = indicator_matrix.get("series", {}) if indicator_matrix else {}
        rsi = self._series_or_build(
            series.get("rsi_14"),
            candles,
            lambda: rsi_wilder_series(closes, 14).series,
        )
        macd_hist = self._series_or_build(
            series.get("macd_hist"), candles, lambda: macd_series(closes).histogram.series
        )
        obv = self._series_or_build(
            series.get("obv"),
            candles,
            lambda: obv_series(closes, volumes).series,
        )
        cci = self._series_or_build(
            series.get("cci_20"),
            candles,
            lambda: self._cci_series(highs, lows, closes),
        )
        kdj = self._series_or_build(
            series.get("kdj_j"),
            candles,
            lambda: self._kdj_j_series(highs, lows, closes),
        )
        adx_series = self._series_or_build(
            series.get("adx_14"),
            candles,
            lambda: adx_wilder_series(highs, lows, closes, 14)["adx"].series,
        )
        atr_series = self._series_or_build(
            series.get("atr_14"),
            candles,
            lambda: atr_wilder_series(highs, lows, closes, 14).series,
        )
        adx = _to_decimal(next((item for item in reversed(adx_series) if item is not None), 0))
        atr = _to_decimal(next((item for item in reversed(atr_series) if item is not None), 0))
        trend_context = self._trend_context(closes)

        signals = []
        signals.extend(
            self._detect_for_indicator(
                "RSI", rsi, candles, price_highs, price_lows, timeframe, trend_context
            )
        )
        signals.extend(
            self._detect_for_indicator(
                "MACD", macd_hist, candles, price_highs, price_lows, timeframe, trend_context
            )
        )
        signals.extend(
            self._detect_for_indicator(
                "OBV", obv, candles, price_highs, price_lows, timeframe, trend_context
            )
        )
        signals.extend(
            self._detect_for_indicator(
                "CCI", cci, candles, price_highs, price_lows, timeframe, trend_context
            )
        )
        signals.extend(
            self._detect_for_indicator(
                "KDJ", kdj, candles, price_highs, price_lows, timeframe, trend_context
            )
        )

        overall = self._overall(signals, timeframe, instrument_id, adx, atr, trend_context)
        filters = self._filters(signals, adx, atr, trend_context)
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "overall": overall,
            "signals": signals[:8],
            "filters": filters,
            "trend_context": trend_context,
            "generated_at": (
                _to_datetime(_field(candles[-1], "ts_open"))
                if candles
                else datetime.now(timezone.utc)
            ),
        }

    def _series_or_build(self, values, candles: list, builder):
        if isinstance(values, list) and len(values) == len(candles):
            return [None if item is None else _to_decimal(item) for item in values]
        return builder()

    def _empty_payload(self, instrument_id: str, timeframe: str, message: str) -> dict:
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "overall": {
                "tone": "neutral",
                "title": "",
                "score": 0.0,
                "confidence": 0.0,
                "leaders": [],
                "message": message,
                "trend_context": "unknown",
                "signal_kind": "warning",
                "entry_signal": False,
            },
            "signals": [],
            "filters": [],
            "trend_context": "unknown",
            "generated_at": datetime.now(timezone.utc),
        }

    def _price_pivots(
        self, candles: list, highs: list[Decimal], lows: list[Decimal]
    ) -> tuple[list[Pivot], list[Pivot]]:
        high_pivots: list[Pivot] = []
        low_pivots: list[Pivot] = []
        for index in range(2, len(candles) - 2):
            high = highs[index]
            low = lows[index]
            if (
                high > highs[index - 1]
                and high > highs[index - 2]
                and high >= highs[index + 1]
                and high >= highs[index + 2]
            ):
                high_pivots.append(
                    Pivot(
                        index=index,
                        ts=_to_datetime(_field(candles[index], "ts_open")),
                        price=float(high),
                        kind="high",
                    )
                )
            if (
                low < lows[index - 1]
                and low < lows[index - 2]
                and low <= lows[index + 1]
                and low <= lows[index + 2]
            ):
                low_pivots.append(
                    Pivot(
                        index=index,
                        ts=_to_datetime(_field(candles[index], "ts_open")),
                        price=float(low),
                        kind="low",
                    )
                )
        return high_pivots[-4:], low_pivots[-4:]

    def _indicator_pivots(self, series: list[Decimal | None], kind: str) -> list[int]:
        pivots: list[int] = []
        for index in range(2, len(series) - 2):
            value = series[index]
            if value is None:
                continue
            window = series[index - 2 : index + 3]
            if any(item is None for item in window):
                continue
            if (
                kind == "high"
                and value > window[1]
                and value > window[0]
                and value >= window[3]
                and value >= window[4]
            ):
                pivots.append(index)
            if (
                kind == "low"
                and value < window[1]
                and value < window[0]
                and value <= window[3]
                and value <= window[4]
            ):
                pivots.append(index)
        return pivots

    def _nearest_indicator_pivot(
        self, pivots: list[int], target: int, width: int = 4
    ) -> int | None:
        candidates = [item for item in pivots if abs(item - target) <= width]
        if not candidates:
            return None
        return min(candidates, key=lambda item: abs(item - target))

    def _normalized(self, left: float, right: float, *, scale: float = 1.0) -> float:
        denominator = max(abs(left), abs(right), scale, 1e-9)
        return (right - left) / denominator

    def _detect_for_indicator(
        self,
        name: str,
        series: list[Decimal | None],
        candles: list,
        price_highs: list[Pivot],
        price_lows: list[Pivot],
        timeframe: str,
        trend_context: str,
    ) -> list[dict]:
        signals: list[dict] = []
        indicator_highs = self._indicator_pivots(series, "high")
        indicator_lows = self._indicator_pivots(series, "low")
        weight = self.WEIGHTS[name]

        if len(price_highs) >= 2:
            first, second = price_highs[-2], price_highs[-1]
            left = self._nearest_indicator_pivot(indicator_highs, first.index)
            right = self._nearest_indicator_pivot(indicator_highs, second.index)
            if left is not None and right is not None:
                price_change = self._normalized(first.price, second.price, scale=1.0)
                indicator_change = self._normalized(
                    _to_float(series[left]),
                    _to_float(series[right]),
                    scale=self._indicator_scale(name),
                )
                if price_change > 0.004 and indicator_change < -0.004:
                    signals.append(
                        self._signal(
                            name,
                            "regular_bearish",
                            "bearish",
                            weight,
                            price_change,
                            indicator_change,
                            second,
                            candles,
                            timeframe,
                            trend_context,
                        )
                    )
                if price_change < -0.004 and indicator_change > 0.004:
                    signals.append(
                        self._signal(
                            name,
                            "hidden_bearish",
                            "bearish",
                            weight,
                            price_change,
                            indicator_change,
                            second,
                            candles,
                            timeframe,
                            trend_context,
                        )
                    )

        if len(price_lows) >= 2:
            first, second = price_lows[-2], price_lows[-1]
            left = self._nearest_indicator_pivot(indicator_lows, first.index)
            right = self._nearest_indicator_pivot(indicator_lows, second.index)
            if left is not None and right is not None:
                price_change = self._normalized(first.price, second.price, scale=1.0)
                indicator_change = self._normalized(
                    _to_float(series[left]),
                    _to_float(series[right]),
                    scale=self._indicator_scale(name),
                )
                if price_change < -0.004 and indicator_change > 0.004:
                    signals.append(
                        self._signal(
                            name,
                            "regular_bullish",
                            "bullish",
                            weight,
                            price_change,
                            indicator_change,
                            second,
                            candles,
                            timeframe,
                            trend_context,
                        )
                    )
                if price_change > 0.004 and indicator_change < -0.004:
                    signals.append(
                        self._signal(
                            name,
                            "hidden_bullish",
                            "bullish",
                            weight,
                            price_change,
                            indicator_change,
                            second,
                            candles,
                            timeframe,
                            trend_context,
                        )
                    )
        return signals

    def _signal(
        self,
        indicator: str,
        divergence_type: str,
        direction: str,
        weight: float,
        price_change: float,
        indicator_change: float,
        pivot: Pivot,
        candles: list,
        timeframe: str,
        trend_context: str,
    ) -> dict:
        strength = _clamp((abs(price_change) * 18) + (abs(indicator_change) * 6), 0.12, 1.0)
        recency = _clamp(1 - ((len(candles) - 1 - pivot.index) / 80), 0.60, 1.0)
        score_sign = 1 if direction == "bullish" else -1
        score = score_sign * weight * strength * recency
        last_close = _to_float(_to_decimal(_field(candles[-1], "close")))
        invalidation_price = (
            min(
                _to_float(_to_decimal(_field(candles[max(pivot.index - 2, 0)], "low"))),
                pivot.price,
            )
            if direction == "bullish"
            else max(
                _to_float(_to_decimal(_field(candles[max(pivot.index - 2, 0)], "high"))),
                pivot.price,
            )
        )
        confirmation_price = (
            max(last_close, pivot.price) if direction == "bullish" else min(last_close, pivot.price)
        )
        return {
            "indicator": indicator,
            "type": divergence_type,
            "direction": direction,
            "signal_kind": "warning",
            "entry_signal": False,
            "tone": "bullish" if direction == "bullish" else "bearish",
            "title": self._title(indicator, divergence_type),
            "message": self._message(indicator, divergence_type, price_change, indicator_change),
            "weight": weight,
            "strength": round(strength, 4),
            "recency": round(recency, 4),
            "score": round(score, 4),
            "trend_context": trend_context,
            "confirmation": self._confirmation(direction, confirmation_price),
            "invalidation": self._invalidation(direction, invalidation_price),
            "cooldown": self.COOLDOWN_BY_TIMEFRAME.get(timeframe, 3),
            "dedupe_key": f"{indicator}:{divergence_type}:{timeframe}:{pivot.ts.isoformat()}",
            "event_ts": pivot.ts,
        }

    def _overall(
        self,
        signals: list[dict],
        timeframe: str,
        instrument_id: str,
        adx: Decimal,
        atr: Decimal,
        trend_context: str,
    ) -> dict:
        if not signals:
            return {
                "tone": "neutral",
                "title": "未发现有效背离",
                "score": 0.0,
                "confidence": 0.12,
                "leaders": [],
                "message": (f"??????????????ADX {_to_float(adx):.1f}?ATR {_to_float(atr):.1f}?"),
                "trend_context": trend_context,
                "signal_kind": "warning",
                "entry_signal": False,
                "instrument_id": instrument_id,
                "timeframe": timeframe,
            }
        score = round(sum(float(item["score"]) for item in signals), 4)
        leaders = [
            item["indicator"]
            for item in sorted(signals, key=lambda item: abs(item["score"]), reverse=True)[:3]
        ]
        confidence = _clamp(abs(score) * 1.7 + min(len(signals), 4) * 0.08, 0.15, 0.92)
        if {"RSI", "MACD", "OBV"}.issubset(set(leaders)):
            confidence = _clamp(confidence + 0.10, 0.15, 0.95)
        if score >= 0.35:
            title, tone, message = (
                "多指标底背离偏强",
                "bullish",
                "多个指标同步指向潜在上行动能修复。",
            )
        elif score >= 0.15:
            title, tone, message = "底背离观察", "bullish", "部分指标出现底背离，需要价格确认。"
        elif score <= -0.35:
            title, tone, message = (
                "多指标顶背离偏强",
                "bearish",
                "多个指标同步指向潜在上行动能衰减。",
            )
        elif score <= -0.15:
            title, tone, message = "顶背离观察", "bearish", "部分指标出现顶背离，需要价格确认。"
        else:
            title, tone, message = "背离信号较弱", "event", "当前背离强度不足，仅作为风险提示。"
        return {
            "tone": tone,
            "title": title,
            "score": score,
            "confidence": round(confidence, 4),
            "leaders": leaders,
            "message": message,
            "trend_context": trend_context,
            "signal_kind": "warning",
            "entry_signal": False,
            "instrument_id": instrument_id,
            "timeframe": timeframe,
        }

    def _filters(
        self, signals: list[dict], adx: Decimal, atr: Decimal, trend_context: str
    ) -> list[dict]:
        filters: list[dict] = []
        adx_value = _to_float(adx)
        atr_value = _to_float(atr)
        if signals and adx_value < 20:
            filters.append(
                {
                    "tone": "event",
                    "title": "趋势强度不足",
                    "message": f"ADX {adx_value:.1f}，背离信号需要额外价格确认。",
                }
            )
        if signals and atr_value <= 0:
            filters.append(
                {
                    "tone": "event",
                    "title": "波动率数据不足",
                    "message": "ATR 不可用，止损与目标位需要人工复核。",
                }
            )
        if trend_context == "sideways":
            filters.append(
                {
                    "tone": "event",
                    "title": "震荡环境",
                    "message": "当前处于震荡结构，背离更适合作为观察信号。",
                }
            )
        return filters

    def _trend_context(self, closes: list[Decimal]) -> str:
        ema20 = ema_series(closes, 20).value
        ema50 = ema_series(closes, 50).value
        last = closes[-1]
        if last >= ema20 >= ema50:
            return "uptrend"
        if last <= ema20 <= ema50:
            return "downtrend"
        return "sideways"

    def _indicator_scale(self, name: str) -> float:
        return {
            "RSI": 100.0,
            "MACD": 5.0,
            "OBV": 1_000_000.0,
            "CCI": 300.0,
            "KDJ": 100.0,
        }.get(name, 1.0)

    def _title(self, indicator: str, divergence_type: str) -> str:
        mapping = {
            "regular_bearish": "常规顶背离",
            "regular_bullish": "常规底背离",
            "hidden_bullish": "隐藏底背离",
            "hidden_bearish": "隐藏顶背离",
        }
        return f"{indicator} {mapping.get(divergence_type, '背离')}"

    def _message(
        self, indicator: str, divergence_type: str, price_change: float, indicator_change: float
    ) -> str:
        label = {
            "regular_bearish": "常规顶背离",
            "regular_bullish": "常规底背离",
            "hidden_bullish": "隐藏底背离",
            "hidden_bearish": "隐藏顶背离",
        }.get(divergence_type, "背离信号")
        return (
            f"???? {price_change * 100:.2f}%?"
            f"{indicator} ?? {indicator_change * 100:.2f}%???{label}?"
        )

    def _confirmation(self, direction: str, price: float) -> str:
        if direction == "bullish":
            return f"{price:.2f} "
        return f"{price:.2f} "

    def _invalidation(self, direction: str, price: float) -> str:
        if direction == "bullish":
            return f"{price:.2f}"
        return f"{price:.2f} "

    def _cci_series(
        self, highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], period: int = 20
    ) -> list[Decimal | None]:
        typical = [
            (highs[idx] + lows[idx] + closes[idx]) / Decimal("3") for idx in range(len(closes))
        ]
        basis = sma_series(typical, period).series
        values: list[Decimal | None] = []
        for index, tp in enumerate(typical):
            middle = basis[index]
            if middle is None or index + 1 < period:
                values.append(None)
                continue
            sample = typical[index - period + 1 : index + 1]
            mean_dev = sum(abs(item - middle) for item in sample) / Decimal(period)
            values.append(
                (tp - middle) / (Decimal("0.015") * mean_dev) if mean_dev else DECIMAL_ZERO
            )
        return values

    def _kdj_j_series(
        self, highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], period: int = 9
    ) -> list[Decimal | None]:
        k = Decimal("50")
        d = Decimal("50")
        j_values: list[Decimal | None] = []
        for index in range(len(closes)):
            start = max(0, index - period + 1)
            high = max(highs[start : index + 1])
            low = min(lows[start : index + 1])
            rsv = (
                Decimal("50")
                if high == low
                else ((closes[index] - low) / (high - low)) * Decimal("100")
            )
            k = (Decimal("2") / Decimal("3")) * k + (Decimal("1") / Decimal("3")) * rsv
            d = (Decimal("2") / Decimal("3")) * d + (Decimal("1") / Decimal("3")) * k
            j_values.append((Decimal("3") * k) - (Decimal("2") * d))
        return j_values
