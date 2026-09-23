# ruff: noqa: E501
"""Unit tests for the V2.2 leverage sizing engine.

Covers: budget gating (tight/wide stops), liquidation buffer blocks,
missing-stop fail-closed, upstream cap respect, and the decision-level
tighten-only integration (sizing can lower the 5x policy bucket, never
raise it).
"""

from __future__ import annotations

from app.services.strategy_unified import leverage_sizing as sizing
from app.services.strategy_unified.contracts import TimeframeNode
from app.services.strategy_unified.trade_decision import TradeDecisionEngine


def _node(timeframe: str, direction: str) -> TimeframeNode:
    return TimeframeNode(
        timeframe=timeframe,
        cache_timeframe=timeframe,
        role="test",
        role_label="test",
        horizon="test",
        direction=direction,
        bias=direction,
        structure_state="READY",
        state="READY",
        long_score=70 if direction == "LONG" else 30,
        short_score=70 if direction == "SHORT" else 30,
        neutral_score=20,
        confidence=80,
        current_price=100,
        key_support=95,
        key_resistance=105,
        invalidation=108 if direction == "SHORT" else 92,
        timeframe_state="BEARISH" if direction == "SHORT" else "BULLISH",
        freshness="fresh",
    )


def _bundles(stop: float, tp1: float, *, max_leverage: float = 5.0) -> dict:
    plan = {
        "entry_zone": [99, 101],
        "stop_price": stop,
        "take_profit_1": tp1,
        "entry_condition": "等待反抽失败",
        "max_leverage": max_leverage,
        "chase_distance_atr": 0.5,
        "spread_bps": 5,
        "slippage_bps": 8,
    }
    return {"4h": {"decision": {"short_plan": plan}}}


def _aligned_nodes() -> list:
    return [_node("1d", "SHORT"), _node("4h", "SHORT"), _node("1h", "SHORT"), _node("15m", "SHORT")]


def test_moderate_stop_keeps_three_x() -> None:
    rec = sizing.evaluate_leverage(stop_distance_pct=3.03, hard_cap=5)
    assert rec.recommended_leverage == 3
    assert rec.leverage_status == "risk_adjusted"
    assert [level.leverage for level in rec.levels if level.allowed] == [1, 2, 3]


def test_wide_stop_collapses_to_one_x() -> None:
    rec = sizing.evaluate_leverage(stop_distance_pct=10.1, hard_cap=5)
    assert rec.recommended_leverage == 1
    assert rec.max_leverage == 1
    assert "1×" in rec.leverage_reason


def test_extreme_stop_blocks_all_levels() -> None:
    rec = sizing.evaluate_leverage(stop_distance_pct=25.0, hard_cap=5)
    assert rec.recommended_leverage == 0
    assert rec.leverage_status == "blocked"
    assert rec.binding_constraint == "risk_budget"


def test_missing_stop_is_fail_closed() -> None:
    rec = sizing.evaluate_leverage(stop_distance_pct=0.0, hard_cap=5)
    assert rec.recommended_leverage == 0
    assert rec.binding_constraint == "missing_stop_distance"


def test_zero_upstream_cap_blocks() -> None:
    rec = sizing.evaluate_leverage(stop_distance_pct=1.0, hard_cap=0)
    assert rec.recommended_leverage == 0
    assert rec.binding_constraint == "upstream_cap"


def test_atr_impact_reported_per_level() -> None:
    rec = sizing.evaluate_leverage(stop_distance_pct=1.0, atr_pct=2.0, hard_cap=5)
    by_lev = {level.leverage: level for level in rec.levels}
    assert by_lev[3].one_atr_margin_impact_pct == 6.0
    assert by_lev[5].one_atr_margin_impact_pct == 10.0


def test_decision_tightens_five_x_policy_to_sizing_optimum() -> None:
    decision = TradeDecisionEngine().build(
        nodes=_aligned_nodes(),
        bundles=_bundles(102, 90),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.status == "READY"
    # Policy bucket says 5x; stop geometry (3.03%) only supports 3x.
    assert decision.recommended_leverage == 3
    assert decision.max_leverage == 3
    assert decision.leverage_detail["optimal"] == 3
    assert decision.stop_distance_pct > 3.0


def test_decision_blocks_when_stop_geometry_supports_nothing() -> None:
    decision = TradeDecisionEngine().build(
        nodes=_aligned_nodes(),
        bundles=_bundles(130, 40),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.recommended_leverage == 0
    assert decision.max_leverage == 0
    assert decision.leverage_status == "blocked"
    assert "止损几何" in decision.leverage_reason


def test_wait_trigger_carries_planned_cap_and_detail_table() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[_node("1d", "SHORT"), _node("4h", "SHORT"), _node("1h", "NEUTRAL"), _node("15m", "NEUTRAL")],
        bundles=_bundles(102, 90),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.status == "WAIT_TRIGGER"
    assert decision.planned_leverage == 3
    assert decision.leverage_detail["optimal"] == 3
    assert len(decision.leverage_detail["levels"]) == 4
