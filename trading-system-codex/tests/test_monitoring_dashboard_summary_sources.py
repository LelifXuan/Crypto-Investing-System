from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import monitoring_dashboard
from app.services.monitoring_dashboard import MonitoringDashboardService


class _FakeRepository:
    def __init__(self, snapshot_by_key: dict[str, Any] | None = None) -> None:
        self.snapshot_by_key = snapshot_by_key or {}
        self.refreshed_strategy = False
        self.refreshed_alerts = False
        self.refreshed_analysis = False

    async def get_page_snapshot_cache(self, cache_key: str):
        payload = self.snapshot_by_key.get(cache_key)
        if payload is None:
            return None
        return SimpleNamespace(
            payload_json=payload,
            snapshot_at=datetime(2026, 6, 1, tzinfo=UTC),
            data_ts=datetime(2026, 6, 1, tzinfo=UTC),
            source_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
            expires_at=datetime(2026, 6, 2, tzinfo=UTC),
            source_version="v3",
            cost_ms=12,
            cache_state="fresh",
            status="ready",
        )


def _alerts_payload() -> dict[str, Any]:
    return {
        "chip_structure": {
            "direction": "bearish",
            "state": "pressure",
            "regime": "上方套牢压力",
            "invalidation_conditions": ["跌破前低后失效"],
        },
        "divergence_summary": {
            "overall": {"tone": "bearish", "title": "顶背离观察"},
            "warnings": ["顶背离需要价格确认"],
        },
        "final_decision": {"action": "no_trade", "state": "blocked"},
        "contract_snapshot": {"funding_rate": 0.0001},
    }


def _strategy_payload() -> dict[str, Any]:
    return {
        "decision": {
            "strategy_state": "blocked",
            "strategy_permission": "等待确认",
            "strategy_bias": "bearish",
            "next_trigger": {"timeframe": "4h", "condition": "反弹不破 VWAP50"},
            "gates": ["OI 不足"],
            "no_trade_reasons": ["合约准入未通过"],
        }
    }


def _analysis_payload() -> dict[str, Any]:
    return {
        "module_scores": {
            "technical_trend": {
                "impact": "bearish",
                "score": 35,
                "state": "弱势下行",
                "confidence": 0.7,
            }
        }
    }


@pytest.mark.asyncio
async def test_dashboard_forwards_alerts_and_strategy_into_terminal_summary() -> None:
    fake = _FakeRepository(
        snapshot_by_key={
            "alerts_bundle:btc-usdt-perp:1d:v3": _alerts_payload(),
            "strategy_bundle:btc-usdt-perp:1d:v3": _strategy_payload(),
            "analysis:btc-usdt-perp:4h:240:v3": _analysis_payload(),
            "analysis:btc-usdt-perp:1d:240:v3": _analysis_payload(),
            "analysis:btc-usdt-perp:1w:240:v3": _analysis_payload(),
        }
    )
    service = MonitoringDashboardService(repository=fake)

    alerts_bundle = await service._load_cached_alerts_bundle(  # noqa: SLF001
        "btc-usdt-perp", "1d"
    )
    strategy_bundle = await service._load_cached_strategy_bundle(  # noqa: SLF001
        "btc-usdt-perp", "1d"
    )
    timeframe_snapshots = await service._load_cached_analysis_timeframes(  # noqa: SLF001
        "btc-usdt-perp"
    )

    summary = service._terminal_summary_payload(  # noqa: SLF001
        None,
        {"total_score": 45, "score_band": "温和偏紧"},
        [],
        alerts_bundle=alerts_bundle,
        strategy_bundle=strategy_bundle,
        timeframe_snapshots=timeframe_snapshots,
    )

    brief = summary["decision_brief"]
    assert brief["version"] == "monitoring_decision_brief_v1"
    alignment = brief["source_alignment"]
    assert "alerts_bundle" in alignment["primary_sources"]
    assert "strategy_bundle" in alignment["primary_sources"]
    assert "analysis_bundle" in alignment["primary_sources"]
    assert set(alignment["timeframes"]) == {"4h", "1d", "1w"}
    market = next(row for row in brief["rows"] if row["key"] == "market_situation")
    assert "alerts.chip_structure" in market["source_refs"]
    assert "alerts.divergence_summary" in market["source_refs"]
    assert any("analysis.4h" in ref for ref in market["source_refs"])
    # T09: the trading_guidance row is gone. The overview is a summary
    # layer and does not re-render the strategy page. The strategy page
    # still owns the strategy.decision references; the overview's
    # market_situation row cites the chip / divergence / analysis
    # sources that the strategy page also depends on, so callers can
    # navigate from the overview to the strategy page by following the
    # source chips.
    assert "trading_guidance" not in {row["key"] for row in brief["rows"]}
    assert "key_risk" in {row["key"] for row in brief["rows"]}


@pytest.mark.asyncio
async def test_dashboard_does_not_trigger_strategy_refresh() -> None:
    fake = _FakeRepository(
        snapshot_by_key={
            "strategy_bundle:btc-usdt-perp:1d:v3": _strategy_payload(),
        }
    )
    service = MonitoringDashboardService(repository=fake)

    bundle = await service._load_cached_strategy_bundle(  # noqa: SLF001
        "btc-usdt-perp", "1d"
    )
    assert bundle["decision"]["strategy_state"] == "blocked"


@pytest.mark.asyncio
async def test_dashboard_marks_degraded_when_alerts_and_strategy_missing() -> None:
    fake = _FakeRepository(snapshot_by_key={})
    service = MonitoringDashboardService(repository=fake)

    alerts = await service._load_cached_alerts_bundle(  # noqa: SLF001
        "btc-usdt-perp", "1d"
    )
    strategy = await service._load_cached_strategy_bundle(  # noqa: SLF001
        "btc-usdt-perp", "1d"
    )
    timeframes = await service._load_cached_analysis_timeframes(  # noqa: SLF001
        "btc-usdt-perp"
    )

    summary = service._terminal_summary_payload(  # noqa: SLF001
        None,
        None,
        [],
        alerts_bundle=alerts,
        strategy_bundle=strategy,
        timeframe_snapshots=timeframes,
    )

    alignment = summary["decision_brief"]["source_alignment"]
    assert alignment["consistency"] == "degraded"
    assert "alerts_bundle" in alignment["missing_sources"]
    assert "strategy_bundle" in alignment["missing_sources"]
    assert "analysis_bundle.4h_1d_1w" in alignment["missing_sources"]


def test_dashboard_constants_expose_summary_timeframes() -> None:
    assert monitoring_dashboard.MONITORING_SUMMARY_TIMEFRAMES == ("4h", "1d", "1w")
    assert monitoring_dashboard.MONITORING_PRIMARY_TIMEFRAME == "1d"
