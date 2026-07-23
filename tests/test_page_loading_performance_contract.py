from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.alerts_bundle import AlertsBundleService
from app.services.macro_overview import MacroOverviewService
from app.services.page_snapshot_cache import source_freshness

ROOT = Path(__file__).resolve().parents[1]


class _MacroRepo:
    async def list_latest_observations_by_key(self, **_kwargs):
        return []

    async def list_indicator_definitions(self, **_kwargs):
        return []

    async def list_macro_events(self, **_kwargs):
        return []


@pytest.mark.asyncio
async def test_macro_overview_read_path_never_fetches_external_history(monkeypatch) -> None:
    service = MacroOverviewService(_MacroRepo())  # type: ignore[arg-type]

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("macro overview GET must be local-only")

    monkeypatch.setattr(service, "_apply_transform", fail_if_called)
    await service.build_overview(now=datetime(2026, 6, 23, tzinfo=UTC))


class _AlertsRepo:
    def __init__(self, cache) -> None:
        self.cache = cache

    async def get_page_snapshot_cache(self, _cache_key):
        return self.cache


def _stale_alert_cache():
    return SimpleNamespace(
        payload_json={
            "chip_structure": None,
            "divergence_summary": None,
            "technical_risk": None,
            "alert_events": [],
            "final_decision": {},
            "contract_snapshot": {},
        },
        cache_state="ready",
        status="ready",
        snapshot_at=datetime.now(UTC) - timedelta(minutes=10),
        data_ts=datetime.now(UTC) - timedelta(hours=2),
        source_updated_at=datetime.now(UTC) - timedelta(hours=2),
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
        source_version="v3",
        cost_ms=50,
    )


def test_stale_alert_bundle_returns_without_synchronous_refresh() -> None:
    service = AlertsBundleService(_AlertsRepo(_stale_alert_cache()))  # type: ignore[arg-type]

    async def fail_refresh(*_args, **_kwargs):
        raise AssertionError("GET must not synchronously rebuild stale alerts")

    service.refresh_bundle = fail_refresh  # type: ignore[method-assign]
    result = asyncio.run(service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True))

    assert result.cache_state == "stale"
    assert result.refresh_enqueued is True


def test_source_freshness_uses_business_timeframe_not_cache_age() -> None:
    now = datetime(2026, 6, 23, 12, tzinfo=UTC)

    daily = source_freshness(now - timedelta(hours=40), "1d", now=now)
    hourly = source_freshness(now - timedelta(hours=2), "1h", now=now)
    very_old = source_freshness(now - timedelta(days=4), "1d", now=now)

    assert daily.state == "usable_stale"
    assert hourly.state == "usable_stale"
    assert very_old.state == "expired"


def test_frontend_critical_paths_are_progressive() -> None:
    analysis = (ROOT / "app/static/pages/analysis.js").read_text(encoding="utf-8")
    monitoring = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
    gold = (ROOT / "app/static/pages/gold_allocation.js").read_text(encoding="utf-8")
    main = (ROOT / "app/static/main.js").read_text(encoding="utf-8")

    initial_analysis = analysis[
        analysis.index("async function loadAll") : analysis.index("function renderChartBatch")
    ]
    assert "Promise.all([" not in initial_analysis
    assert "preferLive: true" not in initial_analysis
    assert "enhanceLatestMark" in analysis

    assert "macroPromise.then" in monitoring
    monitoring_load = monitoring[monitoring.index("async function loadDashboard") :]
    assert "await api.getMacroOverview" not in monitoring_load

    render_gold = gold[gold.index("export async function renderGoldAllocation"):]
    assert "await loadExecutionPlan()" not in render_gold
    assert "ready: loadPromise" in render_gold

    assert "https://cdn.jsdelivr.net/npm/chart.js" not in main
    assert "/static/vendor/chart.umd.js" in main
