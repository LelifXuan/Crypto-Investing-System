"""Single-flight strategy build coordinator.

Guarantees that for any given BuildKey, at most one background build is alive.
Concurrent requests with the same key share the same job and result.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, Mapping, MutableMapping, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BuildJobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PUBLISHING = "publishing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class BuildJob(Generic[T]):
    job_id: str
    key_digest: str
    state: BuildJobState
    task: asyncio.Task[T]
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    error_message: str | None = None

    def transition(self, state: BuildJobState) -> None:
        self.state = state
        self.updated_at = _utc_now()


class BuildQueueFullError(RuntimeError):
    """Raised when the build queue has reached its maximum inflight limit."""


# ---------------------------------------------------------------------------
# Lightweight metrics (in-process counters). No external dependency required.
# ---------------------------------------------------------------------------


class _SimpleMetrics:
    """Minimal metrics sink. Production can replace with Prometheus/StatsD."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._observations: dict[str, list[float]] = {}

    def increment(self, name: str, value: int = 1, *, labels: Mapping[str, str] | None = None) -> None:
        key = self._key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        key = self._key(name, labels)
        self._gauges[key] = value

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        key = self._key(name, labels)
        self._observations.setdefault(key, []).append(value)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "observations": {k: {"count": len(v), "sum": sum(v), "max": max(v) if v else 0}
                             for k, v in self._observations.items()},
        }

    @staticmethod
    def _key(name: str, labels: Mapping[str, str] | None) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# ---------------------------------------------------------------------------
# SingleFlight coordinator
# ---------------------------------------------------------------------------


class SingleFlightBuildCoordinator(Generic[T]):
    """One live task per build key. Waiting request cancellation is isolated.

    Concurrency guarantee: for any key digest, at most one build is RUNNING
    at a time. Subsequent requests with the same key join the existing job.
    """

    def __init__(self, *, max_inflight: int = 3, metrics: _SimpleMetrics | None = None) -> None:
        if max_inflight < 1:
            raise ValueError("max_inflight must be >= 1")
        self._max_inflight = max_inflight
        self._metrics = metrics or _SimpleMetrics()
        self._jobs: MutableMapping[str, BuildJob[T]] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        key_digest: str,
        builder: Callable[[str], Awaitable[T]],
    ) -> BuildJob[T]:
        """Submit a build or join an existing one.

        Returns the BuildJob (existing or new). Caller can await
        ``coordinator.wait(job)`` for the result.
        """
        async with self._lock:
            existing = self._jobs.get(key_digest)
            if existing is not None and not existing.task.done():
                self._metrics.increment(
                    "strategy_build_deduplicated_total",
                    labels={"result": "joined"},
                )
                return existing
            # Clean up finished (done) jobs before creating a new one.
            # This allows retry after FAILED/CANCELLED/READY.
            if existing is not None and existing.task.done():
                self._jobs.pop(key_digest, None)

            if self.inflight_count >= self._max_inflight:
                self._metrics.increment(
                    "strategy_build_rejected_total",
                    labels={"reason": "queue_full"},
                )
                raise BuildQueueFullError(
                    f"build queue full: {self.inflight_count}/{self._max_inflight}"
                )

            job_id = str(uuid.uuid4())

            async def runner() -> T:
                job = self._jobs[key_digest]
                job.transition(BuildJobState.RUNNING)
                started = time.perf_counter()
                try:
                    result = await builder(job_id)
                    job.transition(BuildJobState.READY)
                    self._metrics.increment("strategy_build_total", labels={"result": "ready"})
                    return result
                except asyncio.CancelledError:
                    job.transition(BuildJobState.CANCELLED)
                    self._metrics.increment("strategy_build_total", labels={"result": "cancelled"})
                    raise
                except Exception as exc:
                    job.error_code = exc.__class__.__name__
                    job.error_message = str(exc)
                    job.transition(BuildJobState.FAILED)
                    self._metrics.increment("strategy_build_total", labels={"result": "failed"})
                    logger.exception(
                        "strategy build failed",
                        extra={"job_id": job.job_id, "build_key": key_digest},
                    )
                    raise
                finally:
                    self._metrics.observe(
                        "strategy_build_duration_seconds",
                        time.perf_counter() - started,
                    )
                    self._metrics.gauge("strategy_build_inflight", float(self.inflight_count))

            task = asyncio.create_task(runner(), name=f"strategy-build:{key_digest[:12]}:{job_id[:8]}")
            now = _utc_now()
            job = BuildJob(
                job_id=job_id,
                key_digest=key_digest,
                state=BuildJobState.QUEUED,
                task=task,
                created_at=now,
                updated_at=now,
            )
            self._jobs[key_digest] = job
            self._metrics.increment("strategy_build_total", labels={"result": "queued"})
            return job

    async def wait(self, job: BuildJob[T]) -> T:
        """Wait for a build job to complete. Isolated from other waiters."""
        return await asyncio.shield(job.task)

    async def get(self, key_digest: str) -> BuildJob[T] | None:
        """Get the current job for a key, if any."""
        async with self._lock:
            return self._jobs.get(key_digest)

    async def purge_finished(self, *, older_than_seconds: float = 300.0) -> int:
        """Remove completed jobs older than the threshold."""
        cutoff = _utc_now() - timedelta(seconds=older_than_seconds)
        removed = 0
        async with self._lock:
            for digest, job in list(self._jobs.items()):
                if job.task.done() and job.updated_at < cutoff:
                    self._jobs.pop(digest, None)
                    removed += 1
        return removed

    @property
    def inflight_count(self) -> int:
        return sum(1 for job in self._jobs.values() if not job.task.done())

    @property
    def metrics(self) -> _SimpleMetrics:
        return self._metrics
