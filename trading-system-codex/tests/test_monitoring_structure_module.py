"""Acceptance tests for T08: structure module reads real data.

The audit found that the monitoring overview's structure module always
rendered ``待确认`` because the cached monitoring payload never carried a
``structure`` key. The terminal summary engine then read
``payload.get("structure") or {}`` and the ``_optional_module`` wrapper
fell back to the placeholder. T08 fixes two things:

* MonitoringDashboardService._load_cached_structure_payload reads the
  structure page cache (and falls back to strategy.structure_overall).
* StructureSummaryAdapter translates the structure payload into a
  ModuleScore so the terminal summary's structure row reflects the real
  regime / bias instead of a permanent placeholder.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.cache_registry import structure_bundle_cache_key
from app.services.monitoring_dashboard import MonitoringDashboardService
from app.services.terminal_summary_engine import (
    StructureSummaryAdapter,
    TerminalSummaryEngine,
)


def _fake_cache(payload: dict | None, cache_state: str = "fresh"):
    return SimpleNamespace(
        payload_json=payload or {},
        snapshot_at=datetime(2026, 6, 1, tzinfo=UTC),
        data_ts=datetime(2026, 6, 1, tzinfo=UTC),
        source_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        expires_at=datetime(2026, 6, 2, tzinfo=UTC),
        source_version="v3",
        cost_ms=10,
        cache_state=cache_state,
        status="ready",
    )


class _Repo:
    def __init__(self, snapshot_by_key: dict | None = None):
        self.snapshot_by_key = snapshot_by_key or {}
        self.requests: list[str] = []

    async def get_page_snapshot_cache(self, cache_key: str):
        self.requests.append(cache_key)
        payload = self.snapshot_by_key.get(cache_key)
        if payload is None:
            return None
        return _fake_cache(payload)


def test_load_structure_payload_prefers_structure_bundle_cache() -> None:
    """When the structure page cache is hot, the loader reads from it."""
    cache_payload = {
        "regime": "trend",
        "bias": "bearish",
        "regime_label": "弱势下行",
        "score": 35.0,
        "watch_points": ["跌破前低"],
        "confidence": 0.7,
    }
    repo = _Repo(
        snapshot_by_key={
            structure_bundle_cache_key(
                instrument_id="btc-usdt-perp",
                timeframe="1d",
                include_geometry=False,
                candles_limit=220,
            ): cache_payload
        }
    )
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    out = asyncio.run(
        service._load_cached_structure_payload(  # noqa: SLF001
            instrument_id="btc-usdt-perp", timeframe="1d"
        )
    )
    assert out["regime"] == "trend"
    assert out["bias"] == "bearish"
    assert out["score"] == 35.0
    assert out["source"] == "structure_bundle"
    assert out["watch_points"] == ["跌破前低"]


def test_load_structure_payload_falls_back_to_strategy_overall() -> None:
    """When the structure page cache is missing, use the strategy bundle's
    structure_overall block so the overview still reflects the strategy page.
    """
    repo = _Repo(snapshot_by_key={})
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    strategy_bundle = {
        "decision": {
            "structure_overall": {
                "regime": "balance",
                "bias": "neutral",
                "regime_label_cn": "区间震荡",
                "bias_score": 50.0,
                "suggested_action": "等待区间边界突破",
            }
        }
    }
    out = asyncio.run(
        service._load_cached_structure_payload(  # noqa: SLF001
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            strategy_bundle=strategy_bundle,
        )
    )
    assert out["regime"] == "balance"
    assert out["bias"] == "neutral"
    assert out["label"] == "区间震荡"
    assert out["source"] == "strategy.structure_overall"


def test_load_structure_payload_returns_empty_when_no_source() -> None:
    repo = _Repo(snapshot_by_key={})
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    out = asyncio.run(
        service._load_cached_structure_payload(  # noqa: SLF001
            instrument_id="btc-usdt-perp", timeframe="1d", strategy_bundle={}
        )
    )
    assert out == {}


def test_load_structure_payload_falls_back_to_chip_structure() -> None:
    """When both the structure page cache and the strategy bundle are
    empty, derive a structure-shaped payload from the alerts bundle's
    chip_structure so the monitoring overview's structure module does
    not permanently render the 待确认 placeholder.
    """
    repo = _Repo(snapshot_by_key={})
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    alerts_bundle = {
        "chip_structure": {
            "regime": "low_confidence",
            "direction": "bearish",
            "direction_label": "偏空",
            "confidence_score": 0.35,
            "evidence_quality": "proxy_only",
            "evidence_quality_label": "证据不足（仅 K 线涨跌 proxy）",
            "invalidation_conditions": ["若价格重新回到关键区间内部。"],
        }
    }
    out = asyncio.run(
        service._load_cached_structure_payload(  # noqa: SLF001
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            strategy_bundle={},
            alerts_bundle=alerts_bundle,
        )
    )
    assert out["regime"] == "low_confidence"
    assert out["bias"] == "bearish"
    assert out["source"] == "alerts.chip_structure"
    assert "证据不足" in out["reason"]
    assert out["watch_points"] == ["若价格重新回到关键区间内部。"]


def test_load_structure_payload_handles_repository_exception() -> None:
    class _RepoError:
        async def get_page_snapshot_cache(self, cache_key: str):
            raise RuntimeError("db down")

    service = MonitoringDashboardService(repository=_RepoError())  # type: ignore[arg-type]
    out = asyncio.run(
        service._load_cached_structure_payload(  # noqa: SLF001
            instrument_id="btc-usdt-perp", timeframe="1d"
        )
    )
    assert out == {}


def test_structure_adapter_trend_bearish_emits_bearish_score() -> None:
    score = StructureSummaryAdapter().summarize(
        {"regime": "trend", "bias": "bearish", "score": 30}
    )
    assert score.state == "趋势结构"
    assert score.impact == "bearish"
    assert score.score < 50
    assert "趋势结构形成" in score.reason or "结构" in score.reason


def test_structure_adapter_trend_bullish_emits_bullish_score() -> None:
    score = StructureSummaryAdapter().summarize(
        {"regime": "trend", "bias": "bullish", "score": 70}
    )
    assert score.impact == "bullish"
    assert score.score > 50


def test_structure_adapter_balance_emits_neutral_with_区间() -> None:
    score = StructureSummaryAdapter().summarize({"regime": "balance"})
    assert score.state == "区间结构"
    assert score.impact == "neutral"
    assert "区间" in score.reason


def test_structure_adapter_transition_emits_warning() -> None:
    score = StructureSummaryAdapter().summarize({"regime": "transition"})
    assert score.state == "结构切换"
    assert score.impact == "warning"


def test_structure_adapter_empty_payload_returns_待确认() -> None:
    score = StructureSummaryAdapter().summarize(None)
    assert score.state == "待确认"
    assert score.impact == "neutral"
    assert score.score == 50.0


def test_structure_adapter_empty_dict_returns_待确认() -> None:
    score = StructureSummaryAdapter().summarize({})
    assert score.state == "待确认"
    assert score.impact == "neutral"


def test_structure_adapter_clamps_out_of_range_score() -> None:
    score = StructureSummaryAdapter().summarize(
        {"regime": "trend", "bias": "bullish", "score": 250}
    )
    assert 0 <= score.score <= 100


def test_terminal_engine_module_scores_structure_reflects_real_data() -> None:
    """End-to-end: TerminalSummaryEngine.build() uses StructureSummaryAdapter
    so a real structure payload produces a non-待确认 state.
    """
    engine = TerminalSummaryEngine()
    summary = engine.build(
        macro_overview={
            "total_score": 45,
            "data_completeness": {"effective_count": 0, "total_count": 0},
        },
        technical_observations=[],
        structure={
            "regime": "trend",
            "bias": "bearish",
            "score": 35,
            "label": "弱势下行",
            "reason": "趋势结构形成，方向由趋势模板权重决定。",
        },
        event_risk=None,
    )
    struct = summary["module_scores"]["structure"]
    assert struct["state"] != "待确认"
    assert struct["impact"] == "bearish"
    assert struct["score"] < 50
