from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.instrument import Instrument
from app.main import create_app
from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest
from app.services.precompute import PrecomputeService, PrecomputeTaskPlanner, precompute_service


@pytest.fixture()
async def precompute_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "precompute.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    async with db_manager.session() as session:
        session.add(
            Instrument(
                instrument_id="btc-usdt-perp",
                venue="GATEIO",
                symbol="BTC_USDT",
                asset_class="PERP",
                base_ccy="BTC",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={
                    "gateio": {"product_type": "futures", "contract": "BTC_USDT", "settle": "usdt"}
                },
            )
        )
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_page_snapshot_cache_repo_roundtrip(precompute_db) -> None:
    async with db_manager.session() as session:
        repository = MarketRepository(session)
        now = datetime.now(UTC)
        created = await repository.upsert_page_snapshot_cache(
            cache_key="analysis:btc-usdt-perp:1d:default",
            page_type="analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            payload_json={"hello": "world"},
            status="ready",
            snapshot_at=now,
            expires_at=now,
            source_updated_at=now,
            meta_json={"view_window": "default"},
        )
        fetched = await repository.get_page_snapshot_cache(created.cache_key)

    assert fetched is not None
    assert fetched.page_type == "analysis"
    assert fetched.payload_json["hello"] == "world"


@pytest.mark.asyncio
async def test_precompute_hint_analysis_expands_related_tasks(precompute_db) -> None:
    # 2026-07-23: clear the singleton dedup state so this test is
    # order-independent. Without it, a prior test that enqueued the same
    # (page, instrument, timeframe, view_window) hint would mark this call
    # as 'deduped' and leave queued_keys empty, breaking the assertion
    # below that checks for analysis:* keys.
    precompute_service._queue.clear()  # noqa: SLF001
    precompute_service._queued.clear()  # noqa: SLF001
    precompute_service._last_seen_at.clear()  # noqa: SLF001
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            view_window="default",
            reason="test",
            priority=3,
        )
    )

    assert response.status in {"accepted", "deduped"}
    assert response.queue_depth >= 0
    assert (
        any(key.startswith("analysis:btc-usdt-perp:1d:500:") for key in response.queued_keys)
        or response.status == "deduped"
    )


@pytest.mark.asyncio
async def test_deduped_hint_still_returns_trackable_task_keys(precompute_db) -> None:
    precompute_service._queue.clear()  # noqa: SLF001
    precompute_service._queued.clear()  # noqa: SLF001
    precompute_service._last_seen_at.clear()  # noqa: SLF001
    request = PrecomputeHintRequest(
        current_page="market-analysis",
        instrument_id="xaut-usdt-perp",
        timeframe="1d",
        view_window="default",
        reason="gold_workbench_cold_read",
        candidates=["analysis"],
        priority=2,
    )
    first = await precompute_service.enqueue_hint(request)
    second = await precompute_service.enqueue_hint(request)

    assert first.queued_keys
    assert second.status == "deduped"
    assert second.queued_keys == first.queued_keys


@pytest.mark.asyncio
async def test_precompute_hint_strategy_expands_market_context_task(precompute_db) -> None:
    # Queue arithmetic (2026-09-23): a strategy hint refreshes only the
    # requested timeframe — the six-stack fan-out per hint produced more
    # tasks per cycle than the single-threaded worker could drain (queue
    # depth 200+ with the scan row untouched for hours). The periodic
    # worker walks every timeframe explicitly, so per-hint fan-out is
    # redundant.
    precompute_service._queue.clear()  # noqa: SLF001
    precompute_service._queued.clear()  # noqa: SLF001
    precompute_service._last_seen_at.clear()  # noqa: SLF001
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="ai-strategy",
            instrument_id="btc-usdt-perp",
            timeframe="4h",
            reason="test_market_context",
            priority=2,
        )
    )

    assert response.status in {"accepted", "deduped"}
    if response.status != "deduped":
        assert any(
            key.startswith("strategy_unified:btc-usdt-perp:") for key in response.queued_keys
        )
        assert any(
            key.startswith("strategy_bundle:btc-usdt-perp:4h:") for key in response.queued_keys
        )
        assert any(
            key.startswith("market_context:btc-usdt-perp:4h:") for key in response.queued_keys
        )
        # No six-stack fan-out: other timeframes must not be queued by a
        # single 4h hint.
        assert not any(
            key.startswith("strategy_bundle:btc-usdt-perp:1d:") for key in response.queued_keys
        )


def test_precompute_planner_strategy_unified_candidate() -> None:
    tasks = PrecomputeTaskPlanner().build_tasks(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            reason="startup_critical_snapshot",
            visible=False,
            candidates=["strategy_unified"],
            priority=2,
        )
    )

    unified = [task for task in tasks if task.task_type == "strategy_unified"]
    assert len(unified) == 1
    assert unified[0].page_type == "strategy_unified"
    assert unified[0].cache_key.startswith("strategy_unified:btc-usdt-perp:")


def test_analysis_visible_hint_outranks_matrix_warmup_and_promotes_duplicate() -> None:
    planner = PrecomputeTaskPlanner()
    warmup = planner.build_tasks(
        PrecomputeHintRequest(
            current_page="analysis",
            instrument_id="eth-usdt-perp",
            timeframe="4h",
            visible=False,
            candidates=["analysis"],
            reason="analysis_matrix_idle_warmup",
            priority=8,
        )
    )[0]
    visible = planner.build_tasks(
        PrecomputeHintRequest(
            current_page="analysis",
            instrument_id="eth-usdt-perp",
            timeframe="4h",
            visible=True,
            candidates=["analysis"],
            reason="analysis_manual_reload",
            priority=2,
        )
    )[0]

    assert visible.dedupe_key == warmup.dedupe_key
    assert visible.score > warmup.score

    service = PrecomputeService()
    assert service._enqueue_task_locked(warmup) == "accepted"  # noqa: SLF001
    assert service._enqueue_task_locked(visible) == "deduped"  # noqa: SLF001
    assert service._queue[0].score == visible.score  # noqa: SLF001
    assert service._queue[0].visible is True  # noqa: SLF001


@pytest.mark.asyncio
async def test_precompute_strategy_unified_task_persists_snapshot(monkeypatch) -> None:
    saved: dict = {}

    class DummyRepository:
        async def upsert_page_snapshot_cache(self, **kwargs):  # noqa: ANN003
            saved.update(kwargs)
            return object()

    async def fake_build(self, instrument_id: str = "btc-usdt-perp", *, force: bool = False):
        return {
            "instrument_id": instrument_id,
            "status": "ready",
            "generated_at": "2026-07-12T00:00:00+00:00",
            "refresh_state": "requested",
            "refresh_limitations": [],
            "unified_state": {
                "code": "TACTICAL_LONG",
                "label": "看多",
                "instruction": "后台预热完成",
                "permission": "conditional",
                "risk_level": "medium",
            },
            "horizon_views": {},
            "horizon_governance": {"position_cap": "reduced"},
            "market_operation": {"chain": {}},
            "timeframe_stack": [],
            "trade_plans": [],
            "risk_alerts": [],
            "risk_groups": {},
            "monitoring_focus": [],
            "event_watch": [],
            "evidence_trace": [],
            "narrative": {"headline": "后台预热完成", "layers": [], "watchlist": [], "action": ""},
            "snapshot_key": "btc-usdt-perp:abc",
            "payload_hash": "abc",
        }

    monkeypatch.setattr(
        "app.services.strategy_unified.unified_service.UnifiedStrategyService.build_unified_strategy",
        fake_build,
    )
    task = next(
        task
        for task in PrecomputeTaskPlanner().build_tasks(
            PrecomputeHintRequest(
                current_page="strategy",
                instrument_id="btc-usdt-perp",
                timeframe="1d",
                reason="startup_critical_snapshot",
                visible=False,
                candidates=["strategy_unified"],
                priority=2,
            )
        )
        if task.task_type == "strategy_unified"
    )

    await PrecomputeService()._execute_task(DummyRepository(), task)  # noqa: SLF001

    assert saved["cache_key"].startswith("strategy_unified:btc-usdt-perp:")
    assert saved["page_type"] == "strategy_unified"
    assert saved["payload_json"]["unified_state"]["label"] == "看多"
    assert saved["cache_state"] == "fresh"


@pytest.mark.asyncio
async def test_precompute_task_status_reports_queued_task(precompute_db) -> None:
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            view_window="default",
            reason="manual_refresh_click",
            priority=2,
        )
    )

    task_key = (
        response.queued_keys[0] if response.queued_keys else "analysis:btc-usdt-perp:1d:420:v2"
    )
    status = await precompute_service.task_status(task_key)

    assert status.status in {"queued", "running", "missing"}
    if status.status != "missing":
        assert status.cache_key
        assert status.task_type


@pytest.mark.asyncio
async def test_precompute_task_status_endpoint(precompute_db) -> None:
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            view_window="default",
            reason="manual_refresh_click",
            priority=2,
        )
    )
    task_key = (
        response.queued_keys[0] if response.queued_keys else "analysis:btc-usdt-perp:1d:420:v2"
    )

    with TestClient(create_app(enable_lifespan=False)) as client:
        task_response = client.get(f"/api/v1/precompute/tasks/{task_key}")

    assert task_response.status_code == 200
    payload = task_response.json()
    assert payload["status"] in {"queued", "running", "missing"}


@pytest.mark.asyncio
async def test_bundle_endpoints_return_missing_state_without_blocking(precompute_db) -> None:
    with TestClient(create_app(enable_lifespan=False)) as client:
        analysis_response = client.get(
            "/api/v1/analysis/bundle",
            params={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "view_window": "default",
            },
        )
        structure_response = client.get(
            "/api/v1/structure/tab/bundle",
            params={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "include_geometry": "true",
                "candles_limit": 180,
            },
        )

    assert analysis_response.status_code == 200
    assert structure_response.status_code == 200
    assert analysis_response.json()["status"] == "missing"
    assert analysis_response.json()["cache_state"] == "missing"
    assert structure_response.json()["cache_state"] == "missing"


def test_periodic_refresh_plans_stay_within_drain_budget() -> None:
    """Periodic production must fit the single writer's drain budget."""
    from app.services.precompute import PrecomputeTaskPlanner
    from app.workers.precompute_worker import (
        _PERIODIC_REFRESH_PLAN_FAST,
        _PERIODIC_REFRESH_PLAN_MEDIUM,
        _PERIODIC_REFRESH_PLAN_SLOW,
    )

    planner = PrecomputeTaskPlanner()
    instruments = 11  # must cover the listed universe; grows -> budgets grow

    def task_count(plan):
        return (
            sum(
                len(
                    planner.build_tasks(
                        PrecomputeHintRequest(
                            current_page=page,
                            instrument_id="btc-usdt-perp",
                            timeframe=timeframe,
                            candidates=list(candidates),
                            priority=6,
                            reason="periodic_cache_refresh",
                        )
                    )
                )
                for page, candidates, timeframes in plan
                for timeframe in timeframes
            )
            * instruments
        )

    fast_tasks = task_count(_PERIODIC_REFRESH_PLAN_FAST) + 1
    medium_tasks = task_count(_PERIODIC_REFRESH_PLAN_MEDIUM)
    slow_tasks = task_count(_PERIODIC_REFRESH_PLAN_SLOW) + 3
    # Conservative 15 s/task drain: 40 tasks per 10 min. The slow plan
    # must also fit its two-hour window while FAST continues to run.
    assert fast_tasks <= 40, f"FAST enqueues {fast_tasks} tasks per 10 min"
    # Every period bundle can enqueue one dependent unified synthesis. This
    # upper bound counts all of them even though the queue dedupes most.
    dependent_tasks = medium_tasks * 4 + 3 * instruments
    two_hour_tasks = fast_tasks * 12 + medium_tasks * 4 + slow_tasks + dependent_tasks
    assert two_hour_tasks <= 480, (
        f"periodic producer enqueues at most {two_hour_tasks} tasks per two hours"
    )


@pytest.mark.asyncio
async def test_period_bundle_publication_enqueues_unified_resynthesis(monkeypatch) -> None:
    calls = []

    async def fake_refresh(self, instrument_id, timeframe, *, reason):  # noqa: ARG001
        calls.append(("bundle", instrument_id, timeframe, reason))

    async def fake_enqueue(payload):
        calls.append(("unified", payload.instrument_id, payload.candidates, payload.priority))

    monkeypatch.setattr(
        "app.services.strategy_signal.service.StrategySignalService.refresh_bundle",
        fake_refresh,
    )
    service = PrecomputeService()
    monkeypatch.setattr(service, "enqueue_hint", fake_enqueue)
    tasks = PrecomputeTaskPlanner().build_tasks(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id="eth-usdt-perp",
            timeframe="1h",
            candidates=["strategy"],
            reason="periodic_cache_refresh",
            priority=6,
        )
    )
    assert len(tasks) == 1 and tasks[0].page_type == "strategy"
    await service._execute_task(object(), tasks[0])  # noqa: SLF001
    assert calls == [
        ("bundle", "eth-usdt-perp", "1h", "periodic_cache_refresh"),
        ("unified", "eth-usdt-perp", ["strategy_unified"], 9),
    ]


@pytest.mark.asyncio
async def test_dependent_unified_task_reads_published_bundles(monkeypatch) -> None:
    calls = []

    async def fake_build(self, instrument_id, *, force):  # noqa: ARG001
        calls.append((instrument_id, force))
        return {"status": "ready", "opportunity_decisions": {}}

    class Repository:
        async def upsert_page_snapshot_cache(self, **kwargs):
            assert kwargs["page_type"] == "strategy_unified"

    monkeypatch.setattr(
        "app.services.strategy_unified.unified_service.UnifiedStrategyService.build_unified_strategy",
        fake_build,
    )
    tasks = PrecomputeTaskPlanner().build_tasks(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id="eth-usdt-perp",
            timeframe="1d",
            candidates=["strategy_unified"],
            reason="strategy_bundle_published",
            priority=9,
        )
    )
    task = next(item for item in tasks if item.page_type == "strategy_unified")
    await PrecomputeService()._execute_task(Repository(), task)  # noqa: SLF001
    assert calls == [("eth-usdt-perp", False)]


def test_strategy_hint_does_not_fan_out_six_stack() -> None:
    """A single strategy hint must refresh only its own timeframe."""
    from app.services.precompute import PrecomputeTaskPlanner

    tasks = PrecomputeTaskPlanner().build_tasks(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id="eth-usdt-perp",
            timeframe="4h",
            candidates=["strategy", "market_context"],
            priority=6,
        )
    )
    bundle_frames = {task.timeframe for task in tasks if task.task_type == "strategy"}
    assert bundle_frames == {"4h"}, f"strategy fan-out leaked: {bundle_frames}"
