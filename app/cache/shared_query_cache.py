from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy


class SharedQueryCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._entries: dict[str, tuple[float, object]] = {}
        self._inflight: dict[str, asyncio.Task] = {}

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    async def get(self, key: str) -> object | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= self._now():
                self._entries.pop(key, None)
                return None
            return deepcopy(value)

    async def set(self, key: str, value: object, ttl_seconds: int) -> object:
        async with self._lock:
            self._entries[key] = (self._now() + max(1, ttl_seconds), deepcopy(value))
        return value

    async def get_or_set(
        self,
        key: str,
        ttl_seconds: int,
        producer: Callable[[], Awaitable[object]],
    ) -> object:
        cached = await self.get(key)
        if cached is not None:
            return cached

        async with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] > self._now():
                return deepcopy(entry[1])
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(producer(), name=f"shared-query-cache:{key}")
                self._inflight[key] = task

        try:
            value = await task
        finally:
            async with self._lock:
                self._inflight.pop(key, None)

        await self.set(key, value, ttl_seconds)
        return deepcopy(value)

    async def invalidate_prefix(self, prefix: str) -> None:
        async with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]
            for key in keys:
                self._entries.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


shared_query_cache = SharedQueryCache()
