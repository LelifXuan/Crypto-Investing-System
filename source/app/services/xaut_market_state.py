from __future__ import annotations

# ruff: noqa: E501
import math
from statistics import mean, pstdev
from typing import Any

from app.core.timeframes import normalize_timeframe_for_cache, normalize_timeframe_for_provider
from app.repositories.market_repository import MarketRepository
from app.services.market import MarketService

XAUT_INSTRUMENT_ID = "xaut-usdt-perp"
XAUT_SYMBOL = "XAUT_USDT"


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _field(candle: Any, key: str) -> Any:
    return candle.get(key) if isinstance(candle, dict) else getattr(candle, key, None)


def _close(candle: Any) -> float | None:
    return _float(_field(candle, "close"))


def _volume(candle: Any) -> float | None:
    return _float(_field(candle, "volume"))


def _timestamp(candle: Any) -> str | None:
    value = _field(candle, "ts_open") or _field(candle, "timestamp") or _field(candle, "updated_at")
    return str(value) if value is not None else None


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return mean(values[-window:])


def _ret(closes: list[float], days: int) -> float | None:
    if len(closes) <= days:
        return None
    previous = closes[-days - 1]
    latest = closes[-1]
    if not previous:
        return None
    return (latest - previous) / previous


def _natr(candles: list[Any], window: int = 14) -> float | None:
    if len(candles) < window + 1:
        return None
    ranges: list[float] = []
    for candle in candles[-window:]:
        high = _float(_field(candle, "high"))
        low = _float(_field(candle, "low"))
        if high is not None and low is not None:
            ranges.append(max(0.0, high - low))
    close = _close(candles[-1])
    if not ranges or not close:
        return None
    return mean(ranges) / close


def _volume_zscore(candles: list[Any], window: int = 30) -> float | None:
    volumes = [
        value for value in (_volume(candle) for candle in candles[-window:]) if value is not None
    ]
    if len(volumes) < 10:
        return None
    sigma = pstdev(volumes)
    if not sigma:
        return 0.0
    return (volumes[-1] - mean(volumes)) / sigma


def _window_payload(
    candles: list[Any], label: str, ma_window: int, return_window: int
) -> dict[str, Any]:
    closes = [value for value in (_close(candle) for candle in candles) if value is not None]
    latest = closes[-1] if closes else None
    ma = _sma(closes, ma_window)
    ret_window = _ret(closes, return_window) if len(closes) > return_window else None
    recent_high = max(closes[-26:]) if closes else None
    drawdown = (
        ((latest - recent_high) / recent_high) if latest is not None and recent_high else None
    )
    if latest is None:
        logic = f"{label}窗口暂无 XAUT 代理行情，执行判断降级。"
        trend = "missing"
    elif ma is not None and latest >= ma:
        logic = f"{label}仍在关键均线之上，长期配置结构未被破坏。"
        trend = "above_key_ma"
    elif ma is not None:
        logic = f"{label}跌破关键均线，新增配置需要更强调分批和等待稳定。"
        trend = "below_key_ma"
    else:
        logic = f"{label}样本不足，暂以最近价格变化辅助判断。"
        trend = "sample_limited"
    return {
        "label": label,
        "trend": trend,
        "ret_30d" if label == "日线" else "ret_12w": ret_window,
        "drawdown": drawdown,
        "logic": logic,
        "updated_at": _timestamp(candles[-1]) if candles else None,
    }


def build_xaut_market_state_from_candles(
    candles_1d: list[Any],
    candles_1w: list[Any] | None = None,
) -> dict[str, Any]:
    candles_1w = candles_1w or []
    closes = [value for value in (_close(candle) for candle in candles_1d) if value is not None]
    latest = closes[-1] if closes else None
    sma_50 = _sma(closes, 50)
    sma_200 = _sma(closes, 200)
    recent_high = max(closes[-60:]) if closes else None
    drawdown_60d = (
        ((latest - recent_high) / recent_high) if latest is not None and recent_high else None
    )
    natr_14 = _natr(candles_1d)
    ret_7d = _ret(closes, 7)
    state = {
        "instrument_id": XAUT_INSTRUMENT_ID,
        "xaut_symbol": XAUT_SYMBOL,
        "source": "gateio",
        "role": "real_time_gold_proxy",
        "timeframes": ["4h", "1d", "1w"],
        "price": latest,
        "ret_1d": _ret(closes, 1),
        "ret_7d": ret_7d,
        "ret_30d": _ret(closes, 30),
        "drawdown_60d": drawdown_60d,
        "natr_14": natr_14,
        "volume_zscore": _volume_zscore(candles_1d),
        "above_ma50": latest > sma_50 if latest is not None and sma_50 is not None else None,
        "above_ma200": latest > sma_200 if latest is not None and sma_200 is not None else None,
        "updated_at": _timestamp(candles_1d[-1]) if candles_1d else None,
        "daily_window": _window_payload(candles_1d, "日线", 50, 30),
        "weekly_window": _window_payload(candles_1w, "周线", 40, 12),
        "sma_50": sma_50,
        "sma_200": sma_200,
        "evidence_level": "proxy" if latest is not None else "missing",
        "data_quality_note": "XAUT_USDT Gate.io 日线代理行情"
        if latest is not None
        else "XAUT 代理行情暂缺",
    }
    state.update(
        {
            "xaut_price": state["price"],
            "xaut_change_7d_pct": ret_7d * 100 if ret_7d is not None else None,
            "natr_pct": natr_14 * 100 if natr_14 is not None else None,
            "distance_to_ma50_pct": ((latest - sma_50) / sma_50 * 100)
            if latest is not None and sma_50
            else None,
            "drawdown_pct": drawdown_60d * 100 if drawdown_60d is not None else None,
        }
    )
    return state


class XautMarketStateService:
    def __init__(self, repository: MarketRepository | None = None) -> None:
        self.repository = repository

    async def _load_candles(self, timeframe: str, limit: int, *, force: bool) -> list[Any]:
        if self.repository is None:
            return []
        if force:
            try:
                return await MarketService(self.repository).sync_candles_from_provider(
                    XAUT_INSTRUMENT_ID,
                    normalize_timeframe_for_provider(timeframe),
                    limit=limit,
                )
            except Exception:
                pass
        return await self.repository.list_candles(
            XAUT_INSTRUMENT_ID,
            normalize_timeframe_for_cache(timeframe),
            limit=limit,
        )

    async def build_state(self, *, force: bool = False) -> dict[str, Any]:
        if self.repository is None:
            return build_xaut_market_state_from_candles([])
        try:
            candles = await self._load_candles("1d", 220, force=force)
            weekly = await self._load_candles("1w", 120, force=force)
        except Exception:
            candles = []
            weekly = []
        return build_xaut_market_state_from_candles(candles, weekly)
