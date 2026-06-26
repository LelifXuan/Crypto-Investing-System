from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.refresh_jobs import RefreshJobService


@pytest.mark.asyncio
async def test_refresh_job_is_deduped_and_reaches_success() -> None:
    service = RefreshJobService()
    calls = 0

    async def operation() -> dict[str, str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"cache_key": "btc-derivatives:dashboard"}

    first = service.enqueue(
        scope="btc_derivatives",
        dedupe_key="btc:default",
        operation=operation,
    )
    second = service.enqueue(
        scope="btc_derivatives",
        dedupe_key="btc:default",
        operation=operation,
    )

    assert second.job_id == first.job_id
    assert second.status in {"queued", "running"}
    completed = await service.wait(first.job_id, timeout_seconds=1)
    assert completed.status == "success"
    assert completed.result_cache_key == "btc-derivatives:dashboard"
    assert calls == 1


@pytest.mark.asyncio
async def test_refresh_job_records_failure_without_raising_to_status_reader() -> None:
    service = RefreshJobService()

    async def operation() -> None:
        raise RuntimeError("provider unavailable")

    receipt = service.enqueue(
        scope="btc_derivatives",
        dedupe_key="btc:failure",
        operation=operation,
    )
    completed = await service.wait(receipt.job_id, timeout_seconds=1)

    assert completed.status == "failed"
    assert completed.error == "provider unavailable"


@pytest.mark.asyncio
async def test_refresh_job_wait_timeout_returns_running_state() -> None:
    service = RefreshJobService()
    blocker = asyncio.Event()

    async def operation() -> None:
        await blocker.wait()

    receipt = service.enqueue(
        scope="btc_derivatives",
        dedupe_key="btc:slow",
        operation=operation,
    )
    state = await service.wait(receipt.job_id, timeout_seconds=0.01)

    assert state.status in {"queued", "running"}
    blocker.set()
    await service.wait(receipt.job_id, timeout_seconds=1)


@pytest.mark.asyncio
async def test_refresh_job_terminal_state_survives_service_restart(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "refresh_jobs.sqlite3"
    service = RefreshJobService(state_path=state_path)

    receipt = service.enqueue(
        scope="btc_derivatives",
        dedupe_key="btc:persisted",
        operation=lambda: {"cache_key": "btc:dashboard"},
    )
    completed = await service.wait(receipt.job_id, timeout_seconds=1)

    restored = RefreshJobService(state_path=state_path).status(receipt.job_id)

    assert completed.status == "success"
    assert restored.status == "success"
    assert restored.result_cache_key == "btc:dashboard"
