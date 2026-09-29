"""Choose a dated market price for decision inputs.

Publication time is not observation time. In particular, republishing an old
mark alongside fresh indicators must not make that mark a live strategy price.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.data_freshness import TIMEFRAME_SECONDS, normalize_timeframe, parse_ts


def select_reference_price(
    mark: Mapping[str, Any] | None,
    candles: Sequence[Mapping[str, Any]] | None,
    timeframe: str,
    *,
    now: datetime | None = None,
) -> dict[str, str | None]:
    """Take the latest usable observation, preserving its original timestamp.

    Candle timestamps refer to the opening of the current bar. Allow one full
    bar plus a short grace period, while a mark may be no older than ten minutes.
    This prevents an old quote from winning merely because it is non-null.
    """
    current = now or datetime.now(UTC)
    current = current.astimezone(UTC)
    duration = {"15m": 900, "30m": 1800, "30d": 30 * 86400}.get(
        normalize_timeframe(timeframe),
        TIMEFRAME_SECONDS.get(normalize_timeframe(timeframe), 86400),
    )
    options: list[tuple[datetime, Decimal, str]] = []

    def add(value: Any, timestamp: Any, source: str, max_age: timedelta) -> None:
        observed = parse_ts(timestamp)
        if observed is None or observed > current + timedelta(minutes=2):
            return
        if current - observed > max_age:
            return
        try:
            price = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return
        if price.is_finite() and price > 0:
            options.append((observed, price, source))

    mark = mark or {}
    add(
        mark.get("mark_price") or mark.get("price"),
        mark.get("ts_event"),
        str(mark.get("source") or "mark"),
        timedelta(minutes=10),
    )
    if candles:
        candle = candles[-1]
        add(
            candle.get("close"),
            candle.get("ts_open"),
            str(candle.get("source") or "candle"),
            timedelta(seconds=duration + max(600, duration // 10)),
        )
    if not options:
        return {"price": None, "price_as_of": None, "price_source": None}
    observed, price, source = max(options, key=lambda item: item[0])
    return {
        "price": str(price),
        "price_as_of": observed.isoformat(),
        "price_source": source,
    }
