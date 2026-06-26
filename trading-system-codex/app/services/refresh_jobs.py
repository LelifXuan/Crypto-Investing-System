from __future__ import annotations

import asyncio
import inspect
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.paths import app_paths
from app.schemas.refresh import RefreshReceipt


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RefreshJobService:
    def __init__(self, *, state_path: Path | None = None) -> None:
        self._jobs: dict[str, RefreshReceipt] = {}
        self._dedupe: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._state_path = Path(state_path) if state_path else None
        if self._state_path:
            self._initialize_state()

    def _connect(self) -> sqlite3.Connection:
        if self._state_path is None:
            raise RuntimeError("refresh job persistence is not configured")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self._state_path)

    def _initialize_state(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_jobs (
                    job_id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            rows = connection.execute(
                "SELECT dedupe_key, payload FROM refresh_jobs"
            ).fetchall()
        for dedupe_key, payload in rows:
            receipt = RefreshReceipt.model_validate_json(payload)
            if receipt.status in {"queued", "running"}:
                receipt.status = "failed"
                receipt.error = "应用重启，刷新任务已中断"
                receipt.completed_at = _now()
                self._persist(receipt, dedupe_key)
            self._jobs[receipt.job_id] = receipt

    def _persist(self, receipt: RefreshReceipt, dedupe_key: str) -> None:
        if self._state_path is None:
            return
        payload = receipt.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO refresh_jobs (job_id, dedupe_key, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    dedupe_key = excluded.dedupe_key,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (receipt.job_id, dedupe_key, payload, _now().isoformat()),
            )

    def enqueue(
        self,
        *,
        scope: str,
        dedupe_key: str,
        operation: Callable[[], Awaitable[Any] | Any],
        poll_after_ms: int = 750,
    ) -> RefreshReceipt:
        active_id = self._dedupe.get(dedupe_key)
        if active_id:
            active = self._jobs.get(active_id)
            if active and active.status in {"queued", "running"}:
                return active.model_copy(deep=True)
        job_id = uuid4().hex
        receipt = RefreshReceipt(
            job_id=job_id,
            scope=scope,
            status="queued",
            created_at=_now(),
            poll_after_ms=poll_after_ms,
        )
        self._jobs[job_id] = receipt
        self._dedupe[dedupe_key] = job_id
        self._persist(receipt, dedupe_key)
        self._tasks[job_id] = asyncio.create_task(
            self._run(job_id, dedupe_key, operation),
            name=f"refresh:{scope}:{job_id[:8]}",
        )
        return receipt.model_copy(deep=True)

    async def _run(
        self,
        job_id: str,
        dedupe_key: str,
        operation: Callable[[], Awaitable[Any] | Any],
    ) -> None:
        async with self._lock:
            receipt = self._jobs[job_id]
            receipt.status = "running"
            receipt.started_at = _now()
            self._persist(receipt, dedupe_key)
        try:
            result = operation()
            if inspect.isawaitable(result):
                result = await result
            cache_key = result.get("cache_key") if isinstance(result, dict) else None
            async with self._lock:
                receipt = self._jobs[job_id]
                receipt.status = "success"
                receipt.result_cache_key = cache_key
                receipt.completed_at = _now()
                self._persist(receipt, dedupe_key)
        except Exception as exc:
            async with self._lock:
                receipt = self._jobs[job_id]
                receipt.status = "failed"
                receipt.error = str(exc)
                receipt.completed_at = _now()
                self._persist(receipt, dedupe_key)
        finally:
            async with self._lock:
                if self._dedupe.get(dedupe_key) == job_id:
                    self._dedupe.pop(dedupe_key, None)

    def status(self, job_id: str) -> RefreshReceipt:
        receipt = self._jobs.get(job_id)
        if receipt:
            return receipt.model_copy(deep=True)
        return RefreshReceipt(
            job_id=job_id,
            scope="unknown",
            status="missing",
            created_at=_now(),
        )

    async def wait(self, job_id: str, *, timeout_seconds: float) -> RefreshReceipt:
        task = self._tasks.get(job_id)
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout_seconds)
            except TimeoutError:
                pass
        return self.status(job_id)


refresh_job_service = RefreshJobService(
    state_path=app_paths.data_dir / "refresh_jobs.sqlite3"
)
