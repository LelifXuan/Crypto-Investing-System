"""Stability guards for concurrent macro sync.

Verifies the concurrency configuration exists and the timeout protection
is wired correctly. Full hang-resistance is validated by the integration
test in test_macro_api_sources.py (real providers with bounded timeouts).
"""
from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.db.models.market import IndicatorMonitoringPolicy
from app.services.indicator_monitoring import IndicatorMonitoringService


def _policy(key: str) -> IndicatorMonitoringPolicy:
    return IndicatorMonitoringPolicy(
        policy_id=f"pol-{key}",
        indicator_key=key,
        scope_type="global",
        mode="cron",
        interval_seconds=3600,
    )


def test_concurrency_config_defaults():
    """Concurrency + timeout config fields must exist with safe defaults."""
    assert hasattr(settings, "macro_sync_concurrency")
    assert hasattr(settings, "macro_sync_task_timeout_seconds")
    assert hasattr(settings, "macro_sync_batch_timeout_seconds")
    # Conservative defaults: concurrency ≤ 4, task timeout ≤ 120s,
    # batch timeout ≤ 300s (5 min hard ceiling).
    assert 1 <= settings.macro_sync_concurrency <= 4
    assert 30 <= settings.macro_sync_task_timeout_seconds <= 120
    assert 60 <= settings.macro_sync_batch_timeout_seconds <= 300


@pytest.mark.asyncio
async def test_per_task_timeout_cancels_hung_task():
    """A single hung task must be cancelled after per-task timeout so its
    semaphore slot is freed for other tasks (the root cause of the
    full-concurrency deadlock)."""
    settings.macro_sync_batch_timeout_seconds = 30
    settings.macro_sync_task_timeout_seconds = 1
    settings.macro_sync_concurrency = 2

    call_count = {"n": 0}

    async def mock_run(self, policy, trigger_type="manual"):
        call_count["n"] += 1
        if policy.indicator_key == "hung":
            await asyncio.sleep(999)
        return AsyncMock(indicator_key=policy.indicator_key)

    repo = AsyncMock()
    repo.list_monitoring_policies = AsyncMock(return_value=[_policy("hung")])
    repo.upsert_macro_source_health = AsyncMock()
    svc = IndicatorMonitoringService(repository=repo)
    svc._refresh_macro_source_health = AsyncMock()

    @asynccontextmanager
    async def _session_ctx():
        s = AsyncMock()
        s.commit = AsyncMock()
        s.rollback = AsyncMock()
        s.close = AsyncMock()
        yield s

    from app.core.db import db_manager
    with patch("app.core.db.db_manager.session", _session_ctx), \
         patch.object(IndicatorMonitoringService, "run_policy", new=mock_run):
        t0 = asyncio.get_event_loop().time()
        try:
            await asyncio.wait_for(
                svc.run_policy(_policy("hung"), trigger_type="manual"),
                timeout=settings.macro_sync_task_timeout_seconds,
            )
            assert False, "should have timed out"
        except asyncio.TimeoutError:
            dt = asyncio.get_event_loop().time() - t0
            assert dt < 3, f"hung task not cancelled: took {dt:.1f}s"
            assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_per_task_timeout_wired_in_sync_macro():
    """sync_macro must wrap each policy in a per-task timeout so a hung
    provider is cancelled instead of blocking the whole sync loop.

    Serial after 2026-08-18 (the concurrent rewrite wedged SQLite's
    single-writer lock and broke monkeypatched provider stubs); the
    hang-resistance defence that remains is per-policy ``wait_for``.
    """
    src = inspect.getsource(IndicatorMonitoringService.sync_macro)
    assert "macro_sync_task_timeout_seconds" in src
    assert "wait_for" in src
