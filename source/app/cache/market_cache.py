from __future__ import annotations

import asyncio
from collections.abc import Mapping


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
