from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone

# A quote held in market_cache is considered fresh while its provider-side
# timestamp is no older than this threshold. MarketService.get_best_mark uses
# the same value as its fast-path cutoff, so the two definitions stay aligned.
LIVE_MARK_MAX_AGE_SECONDS = 15

UTC = timezone.utc


def is_mark_fresh(
    payload: Mapping | None,
    *,
    now: datetime | None = None,
    max_age_seconds: int = LIVE_MARK_MAX_AGE_SECONDS,
) -> bool:
    """Return True when a cache payload's ts_event is within the age budget.

    A missing payload, missing/empty ``ts_event``, unparsable timestamp,
    future timestamp (clock skew), or older than ``max_age_seconds`` all
    return False. Centralising the rule lets the cache and the service
    agree on what "fresh" means without duplicating the parse/age math.
    """
    if not payload:
        return False
    raw_ts = payload.get("ts_event")
    if not raw_ts:
        return False
    if isinstance(raw_ts, datetime):
        ts = raw_ts
    else:
        try:
            ts = datetime.fromisoformat(str(raw_ts))
        except (TypeError, ValueError):
            return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    age = (reference - ts).total_seconds()
    return age >= 0 and age <= max_age_seconds


class MarketCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._marks: dict[str, dict] = {}
        self._book_tickers: dict[str, dict] = {}
        self._candles: dict[tuple[str, str, str], dict] = {}

    async def set_mark(self, instrument_id: str, payload: Mapping) -> None:
        async with self._lock:
            self._marks[instrument_id] = dict(payload)

    async def get_mark(self, instrument_id: str) -> dict | None:
        async with self._lock:
            item = self._marks.get(instrument_id)
            return dict(item) if item else None

    async def clear_mark(self, instrument_id: str) -> None:
        async with self._lock:
            self._marks.pop(instrument_id, None)

    async def clear_marks(self, instrument_ids: Iterable[str]) -> None:
        # Bulk eviction for a stream of instruments (e.g. a single spot/futures
        # websocket that just disconnected). Distinct from `clear_mark` (one)
        # and `clear` (everything): callers do not need to enumerate what to
        # keep, and unrelated streams stay warm.
        ids = list(instrument_ids)
        if not ids:
            return
        async with self._lock:
            for instrument_id in ids:
                self._marks.pop(instrument_id, None)

    async def set_book_ticker(self, instrument_id: str, payload: Mapping) -> None:
        async with self._lock:
            self._book_tickers[instrument_id] = dict(payload)

    async def get_book_ticker(self, instrument_id: str) -> dict | None:
        async with self._lock:
            item = self._book_tickers.get(instrument_id)
            return dict(item) if item else None

    async def clear_book_ticker(self, instrument_id: str) -> None:
        async with self._lock:
            self._book_tickers.pop(instrument_id, None)

    async def set_candle(
        self, instrument_id: str, timeframe: str, source: str, payload: Mapping
    ) -> None:
        async with self._lock:
            self._candles[(instrument_id, timeframe, source)] = dict(payload)

    async def get_candle(
        self, instrument_id: str, timeframe: str, source: str | None = None
    ) -> dict | None:
        async with self._lock:
            if source is not None:
                item = self._candles.get((instrument_id, timeframe, source))
                return dict(item) if item else None
            candidates = [
                value
                for (inst, tf, _src), value in self._candles.items()
                if inst == instrument_id and tf == timeframe
            ]
            if not candidates:
                return None
            latest = max(candidates, key=lambda item: item.get("ts_open", ""))
            return dict(latest)

    async def clear(self) -> None:
        async with self._lock:
            self._marks.clear()
            self._book_tickers.clear()
            self._candles.clear()


market_cache = MarketCache()
