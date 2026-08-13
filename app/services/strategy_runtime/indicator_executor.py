"""Bounded dedicated executor for pure CPU/Decimal indicator computation.

CRITICAL RULES:
- Only pass immutable pure-Python inputs (tuples, strings, numbers, frozensets).
- NEVER pass: repository, SQLAlchemy session, SQLite connection, ORM objects,
  request-scoped dependencies, mutable shared cache, or transaction context.
- Database reads must happen BEFORE submitting to the executor.
- Database writes must happen AFTER the executor returns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from .singleflight import _SimpleMetrics

logger = logging.getLogger(__name__)

R = TypeVar("R")


class IndicatorExecutor:
    """Bounded thread pool for synchronous Decimal/CPU work.

    The executor has a hard cap on both worker count and queue depth.
    Submitting when the queue is full raises QueueFullError.
    """

    def __init__(
        self,
        *,
        max_workers: int = 2,
        queue_limit: int = 4,
        metrics: _SimpleMetrics | None = None,
    ) -> None:
        if max_workers < 1 or queue_limit < 1:
            raise ValueError("max_workers and queue_limit must be positive")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="indicator-compute",
        )
        # Total concurrency = workers + queue slots. This bounds memory and
        # prevents unbounded submission under load.
        self._slots = asyncio.Semaphore(max_workers + queue_limit)
        self._metrics = metrics or _SimpleMetrics()
        self._closed = False

    async def compute(
        self,
        func: Callable[..., R],
        /,
        *args: Any,
        timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> R:
        """Run a pure function in the thread pool.

        Args:
            func: A synchronous callable that performs only pure computation.
                  It MUST NOT access repositories, sessions, or shared state.
            *args, **kwargs: Immutable arguments to pass to func.
            optional timeout_seconds: Max wait before TimeoutError.
        """
        if self._closed:
            raise RuntimeError("indicator executor is closed")

        queued_at = time.perf_counter()
        await self._slots.acquire()
        self._metrics.observe(
            "indicator_executor_queue_wait_seconds",
            time.perf_counter() - queued_at,
        )

        loop = asyncio.get_running_loop()
        started = time.perf_counter()

        def invoke() -> R:
            return func(*args, **kwargs)

        future = loop.run_in_executor(self._executor, invoke)
        try:
            if timeout_seconds is None:
                return await future
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        finally:
            self._metrics.observe(
                "indicator_compute_duration_seconds",
                time.perf_counter() - started,
            )
            self._slots.release()

    def shutdown(self, *, wait: bool = True) -> None:
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)
