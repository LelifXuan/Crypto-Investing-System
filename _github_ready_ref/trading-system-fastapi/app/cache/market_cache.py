from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    value: dict[str, Any]
    ts_update: datetime
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and datetime.now(UTC) >= self.expires_at


class AsyncMarketCache:
    def __init__(self) -> None:
        self._marks: dict[str, CacheEntry] = {}
        self._book_tickers: dict[str, CacheEntry] = {}
        self._candles: dict[str, CacheEntry] = {}
        self._lock = __import__("asyncio").Lock()

    def _with_ttl(self, value: dict[str, Any], ttl_seconds: int | None) -> CacheEntry:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        return CacheEntry(value=value, ts_update=now, expires_at=expires)

    async def set_mark(self, instrument_id: str, payload: dict[str, Any], ttl_seconds: int = 120) -> None:
        async with self._lock:
            self._marks[instrument_id] = self._with_ttl(payload, ttl_seconds)

    async def get_mark(self, instrument_id: str) -> dict[str, Any] | None:
        async with self._lock:
            entry = self._marks.get(instrument_id)
            if entry is None or entry.is_expired():
                self._marks.pop(instrument_id, None)
                return None
            return dict(entry.value)

    async def set_book_ticker(self, instrument_id: str, payload: dict[str, Any], ttl_seconds: int = 120) -> None:
        async with self._lock:
            self._book_tickers[instrument_id] = self._with_ttl(payload, ttl_seconds)

    async def get_book_ticker(self, instrument_id: str) -> dict[str, Any] | None:
        async with self._lock:
            entry = self._book_tickers.get(instrument_id)
            if entry is None or entry.is_expired():
                self._book_tickers.pop(instrument_id, None)
                return None
            return dict(entry.value)

    async def set_candle(
        self,
        instrument_id: str,
        timeframe: str,
        source: str,
        payload: dict[str, Any],
        ttl_seconds: int = 7200,
    ) -> None:
        key = self._candle_key(instrument_id, timeframe, source)
        async with self._lock:
            self._candles[key] = self._with_ttl(payload, ttl_seconds)

    async def get_candle(self, instrument_id: str, timeframe: str, source: str) -> dict[str, Any] | None:
        key = self._candle_key(instrument_id, timeframe, source)
        async with self._lock:
            entry = self._candles.get(key)
            if entry is None or entry.is_expired():
                self._candles.pop(key, None)
                return None
            return dict(entry.value)

    async def snapshot(self) -> dict[str, int]:
        async with self._lock:
            self._evict_expired_locked()
            return {
                "marks": len(self._marks),
                "book_tickers": len(self._book_tickers),
                "candles": len(self._candles),
            }

    def _evict_expired_locked(self) -> None:
        for store in (self._marks, self._book_tickers, self._candles):
            expired = [key for key, entry in store.items() if entry.is_expired()]
            for key in expired:
                store.pop(key, None)

    @staticmethod
    def _candle_key(instrument_id: str, timeframe: str, source: str) -> str:
        return f"{instrument_id}:{timeframe}:{source}"


market_cache = AsyncMarketCache()
