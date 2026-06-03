"""Acceptance tests for T09: monitoring overview row redesign.

The audit found three issues with the decision_brief rows:

1. The MTF conflict was rendered as a single abstract sentence
   (``4h/1d/1w 多周期方向不一致``) that hid the actual per-TF
   disagreement. The user wants the per-TF list rendered so they
   can decide based on their own trading horizon.
2. The ``trading_guidance`` row re-rendered the strategy page
   (next_trigger, plan levels, gates, no_trade_reasons, permission).
   That violates the "summary layer, not recomputation" principle.
3. The ``risk_invalidation`` row enumerated every chip / divergence /
   structure risk and re-rendered the strategy gates.

T09 redesign:

* ``market_situation``: rich headline that embeds the per-TF breakdown
  when the TFs disagree, plus chip + divergence bullets (which are
  aggregations, not re-renders).
* ``mtf_breakdown``: a new dedicated row that appears only when the
  TFs disagree, showing the per-TF list.
* ``key_risk`` (renamed from ``risk_invalidation``): only data gaps
  and the single most critical invalidation condition. No chip /
  divergence / structure risk enumeration. The futures margin pressure
  bullet is gated by T10 (only when the strategy has an actionable
  plan).
"""

from __future__ import annotations

from app.services.terminal_summary_engine import (
    TerminalSummaryEngine,
    _decision_format_mtf_breakdown,
    _decision_mtf_has_conflict,
    _decision_pick_critical_invalidation,
)

# ruff: noqa: I001


# ---------------------------------------------------------------------------
# _decision_format_mtf_breakdown
# ---------------------------------------------------------------------------


def test_format_mtf_breakdown_omits_empty_input() -> None:
    assert _decision_format_mtf_breakdown({}) == ""


def test_format_mtf_breakdown_orders_high_to_low() -> None:
    """TFs are emitted in canonical order (1w → 1d → 4h → 1h → 15m)."""
    out = _decision_format_mtf_breakdown(
        {
            "4h": {"bias": "bearish", "score": 30},
            "1w": {"bias": "bullish", "score": 70},
            "1d": {"bias": "neutral", "score": 50},
        }
    )
    assert out.startswith("1w 偏多(score 70)")
    assert "1d 偏空" in out or "1d 偏中性" in out or "1d 方向未明" in out
    # The 4h must come last
    assert out.index("1w") < out.index("1d") < out.index("4h")


def test_format_mtf_breakdown_includes_score_label() -> None:
    out = _decision_format_mtf_breakdown(
        {"1w": {"bias": "bearish", "score": 35.0}}
    )
    assert "score 35" in out


def test_format_mtf_breakdown_without_score_omits_score_label() -> None:
    out = _decision_format_mtf_breakdown(
        {"1d": {"bias": "bullish"}}
    )
    assert "score" not in out
    assert "1d 偏多" in out


def test_format_mtf_breakdown_skips_score_when_include_scores_false() -> None:
    out = _decision_format_mtf_breakdown(
        {"1w": {"bias": "bearish", "score": 35}}, include_scores=False
    )
    assert "score" not in out
    assert "1w 偏空" in out


def test_format_mtf_breakdown_handles_unknown_timeframes() -> None:
    out = _decision_format_mtf_breakdown(
        {"1w": {"bias": "bullish"}, "3d": {"bias": "bearish"}}
    )
    assert "1w 偏多" in out
    assert "3d 偏空" in out


def test_mtf_has_conflict_returns_true_when_directions_differ() -> None:
    assert _decision_mtf_has_conflict(
        {"1w": {"bias": "bullish"}, "1d": {"bias": "bearish"}}
    ) is True


def test_mtf_has_conflict_returns_false_when_directions_agree() -> None:
    assert _decision_mtf_has_conflict(
        {"1w": {"bias": "bullish"}, "1d": {"bias": "bullish"}}
    ) is False


def test_mtf_has_conflict_returns_false_when_empty() -> None:
    assert _decision_mtf_has_conflict({}) is False


def test_mtf_has_conflict_ignores_tfs_with_unknown_direction() -> None:
    """A TF without a direction does not count as a conflict partner."""
    assert _decision_mtf_has_conflict(
        {"1w": {"bias": "bullish"}, "1d": {"score": 50}}
    ) is False


# ---------------------------------------------------------------------------
# _decision_pick_critical_invalidation
# ---------------------------------------------------------------------------


def test_pick_critical_invalidation_prefers_chip() -> None:
    """The chip's first invalidation condition wins over structure."""
    out = _decision_pick_critical_invalidation(
        chip={
            "invalidation_conditions": [
                "若价格重新站回 EMA50，则当前空头判断失效。"
            ]
        },
        divergence={},
        structure={
            "invalidation_conditions": ["跌破前低后失效"]
        },
    )
    assert out is not None
    assert "EMA50" in out["text"]
    assert "alerts.chip_structure" in out["source"]


def test_pick_critical_invalidation_falls_back_to_structure() -> None:
    out = _decision_pick_critical_invalidation(
        chip={},
        divergence={},
        structure={"invalidation_conditions": ["跌破前低后失效"]},
    )
    assert out is not None
    assert "前低" in out["text"]


def test_pick_critical_invalidation_returns_none_when_no_input() -> None:
    out = _decision_pick_critical_invalidation(
        chip={}, divergence={}, structure={}
    )
    assert out is None


# ---------------------------------------------------------------------------
# End-to-end: _build_decision_brief new contract
# ---------------------------------------------------------------------------


def test_build_decision_brief_market_row_embeds_mtf_breakdown() -> None:
    """When the TFs disagree, market_situation's summary names them."""
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bearish"},
        },
        strategy_bundle={
            "decision": {
                "strategy_state": "OBSERVE",
                "strategy_bias": "neutral",
            }
        },
        timeframe_snapshots={
            "1w": {"bias": "bullish", "score": 70},
            "1d": {"bias": "bearish", "score": 35},
            "4h": {"bias": "bearish", "score": 28},
        },
    )
    market = next(
        row for row in summary["decision_brief"]["rows"]
        if row["key"] == "market_situation"
    )
    assert "方向冲突" in market["summary"]
    assert "1w 偏多" in market["summary"]
    assert "1d 偏空" in market["summary"]
    assert "4h 偏空" in market["summary"]
    # And the mtf_breakdown row is also present.
    mtf = next(
        row for row in summary["decision_brief"]["rows"]
        if row["key"] == "mtf_breakdown"
    )
    assert "1w 偏多(score 70)" in mtf["bullets"][0] or "1w 偏多(score 70)" in mtf["summary"]


def test_build_decision_brief_omits_trading_guidance() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bearish"},
        },
        strategy_bundle={
            "decision": {
                "strategy_state": "OBSERVE",
                "strategy_state_label": "观察",
                "strategy_bias": "neutral",
                "strategy_permission": "observe_only",
                "next_trigger": "等待 4H 突破",
                "gates": ["OI 不足"],
                "no_trade_reasons": ["合约准入未通过"],
            }
        },
        timeframe_snapshots={
            "1w": {"bias": "bullish"},
            "1d": {"bias": "bearish"},
        },
    )
    keys = [row["key"] for row in summary["decision_brief"]["rows"]]
    assert "trading_guidance" not in keys
    # The strategy page fields do NOT leak into the overview rows.
    joined = " ".join(
        row["summary"] + " " + " ".join(row["bullets"])
        for row in summary["decision_brief"]["rows"]
    )
    assert "OI 不足" not in joined
    assert "合约准入" not in joined
    assert "等待 4H 突破" not in joined


def test_build_decision_brief_key_risk_only_shows_data_gaps_and_critical() -> None:
    """The key_risk row carries data gaps + 1 critical invalidation only."""
    summary = TerminalSummaryEngine().build(
        alerts_bundle={},  # no chip / divergence
        strategy_bundle={
            "decision": {
                "strategy_state": "OBSERVE",
                "strategy_bias": "neutral",
            }
        },
        structure={
            "invalidation_conditions": [
                "跌破前低后失效",
                "第二个条件不应出现",
            ]
        },
    )
    risk = next(
        row for row in summary["decision_brief"]["rows"]
        if row["key"] == "key_risk"
    )
    joined = " ".join(risk["bullets"])
    # Only the first critical invalidation is shown
    assert "前低" in joined
    assert "第二个条件不应出现" not in joined
    # Data gaps from source_alignment are surfaced
    assert "数据缺口" in joined


def test_build_decision_brief_omits_mtf_breakdown_when_aligned() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bullish"},
        },
        strategy_bundle={
            "decision": {
                "strategy_state": "ready",
                "strategy_bias": "bullish",
            }
        },
        timeframe_snapshots={
            "1w": {"bias": "bullish"},
            "1d": {"bias": "bullish"},
            "4h": {"bias": "bullish"},
        },
    )
    keys = [row["key"] for row in summary["decision_brief"]["rows"]]
    assert "mtf_breakdown" not in keys
    # market_situation still cites the aligned source.
    market = next(
        row for row in summary["decision_brief"]["rows"]
        if row["key"] == "market_situation"
    )
    assert "偏多" in " ".join([market["summary"], *market["bullets"]])
