from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.indicator_judgement import (
    build_indicator_judgement,
    load_indicator_judgement_registry,
)
from app.services.strategy_unified.contracts import TimeframeNode
from app.services.strategy_unified.trade_decision import TradeDecisionEngine


def _node(timeframe: str, direction: str, *, freshness: str = "fresh") -> TimeframeNode:
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
        timeframe_state="BULLISH"
        if direction == "LONG"
        else "BEARISH"
        if direction == "SHORT"
        else "RANGE",
        freshness=freshness,
    )


def _bundles(rr: float | None = 2.0, *, max_leverage: float = 5.0) -> dict:
    plan = {
        "entry_zone": [99, 101],
        "stop_price": 105,
        "take_profit_1": 100 - (rr * 5 if rr is not None else 10),
        "entry_condition": "等待反抽失败",
        "max_leverage": max_leverage,
        "chase_distance_atr": 0.5,
        "spread_bps": 5,
        "slippage_bps": 8,
    }
    if rr is not None:
        plan["risk_reward_ratio"] = rr
    return {"4h": {"decision": {"short_plan": plan}}}


def test_registry_marks_non_directional_indicators() -> None:
    registry = load_indicator_judgement_registry()
    assert registry["atr_14"]["directional"] is False
    assert registry["bbands"]["directional"] is False
    assert registry["funding_rate"]["directional"] is False
    assert registry["max_pain"]["default_action_effect"] == "LEVEL_ONLY"


@pytest.mark.parametrize(
    "key,state",
    [("atr_14", "event"), ("bbands", "volatility_breakout_down"), ("funding_rate", "positive_hot")],
)
def test_non_directional_indicator_never_emits_trade_direction(key: str, state: str) -> None:
    judgement = build_indicator_judgement(
        {"indicator_key": key, "signal_state": state, "value_num": 1},
        timeframe="1d",
    )
    assert judgement["direction"] == "NONE"


def test_unregistered_indicator_is_data_quality_not_neutral() -> None:
    judgement = build_indicator_judgement(
        {"indicator_key": "unknown_indicator", "signal_state": "bullish"}
    )
    assert judgement["axis"] == "data_quality"
    assert judgement["state"] == "UNREGISTERED"
    assert judgement["data_status"] == "unregistered"
    assert judgement["direction"] == "NONE"


def test_daily_short_with_neutral_4h_waits_for_setup() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "NEUTRAL"),
            _node("1h", "NEUTRAL"),
            _node("15m", "NEUTRAL"),
        ],
        bundles=_bundles(),
        risk_alerts=[],
        position_cap="standard",
        next_check="next_4h_close",
    )
    assert decision.side == "SHORT"
    assert decision.status == "WAIT_SETUP"
    assert decision.order_type == "NONE"
    assert decision.order_status == "WAIT_SETUP"
    assert decision.conflict_timeframe == ""
    assert decision.confirmation_timeframe == "4h"
    assert decision.primary_reason["code"] == "WAIT_FOUR_HOUR_ALIGNMENT"
    assert decision.recommended_leverage == 0
    assert decision.max_leverage == 0


def test_aligned_daily_4h_waits_for_1h_trigger() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "NEUTRAL"),
            _node("15m", "NEUTRAL"),
        ],
        bundles=_bundles(),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.status == "WAIT_TRIGGER"
    assert decision.primary_reason["code"] == "WAIT_RECURSIVE_CONFIRMATION"
    assert decision.recommended_leverage == 0
    assert decision.max_leverage == 0
    assert decision.planned_leverage == 3
    assert decision.order_type == "CONDITIONAL_LIMIT"
    assert decision.trade_timeframe == "4h"
    assert decision.direction_timeframes == ["1d", "4h"]
    assert decision.execution_timeframes == ["1h", "15m"]
    assert decision.direction_source == "1d+4h"


def test_full_short_chain_is_ready() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT"),
            _node("15m", "SHORT"),
        ],
        bundles=_bundles(),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.status == "READY"
    assert decision.order_type == "MARKET"
    assert decision.order_status == "READY"
    assert decision.permission == "allow"
    assert decision.recommended_leverage == 5
    assert decision.max_leverage == 5
    assert decision.leverage_status == "full_alignment"


@pytest.mark.parametrize(
    ("directions", "conflict_timeframe"),
    [
        (("SHORT", "LONG", "SHORT"), "1h"),
        (("SHORT", "SHORT", "LONG"), "15m"),
    ],
)
def test_first_lower_timeframe_conflict_builds_conditional_limit(
    directions: tuple[str, str, str], conflict_timeframe: str
) -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", directions[0]),
            _node("1h", directions[1]),
            _node("15m", directions[2]),
        ],
        bundles=_bundles(),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.order_type == "CONDITIONAL_LIMIT"
    assert decision.conflict_timeframe == conflict_timeframe
    assert decision.side == "SHORT"
    assert decision.trade_timeframe == "4h"
    assert decision.direction_source == "1d+4h"
    assert decision.recommended_leverage == 0
    assert decision.planned_leverage == 3
    assert len(decision.activation_conditions) == 2


def test_missing_lower_timeframe_data_blocks_order_generation() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT", freshness="missing"),
            _node("15m", "SHORT"),
        ],
        bundles=_bundles(),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.order_type == "NONE"
    assert decision.order_status == "BLOCKED"
    assert decision.primary_reason["code"] == "EXECUTION_DATA_UNAVAILABLE"


def test_market_price_protection_failure_blocks_market_order() -> None:
    bundles = _bundles()
    bundles["4h"]["decision"]["short_plan"]["slippage_bps"] = 41
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT"),
            _node("15m", "SHORT"),
        ],
        bundles=bundles,
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.order_type == "NONE"
    assert decision.order_status == "BLOCKED"
    assert decision.primary_reason["code"] == "MARKET_PRICE_PROTECTION_FAILED"


def test_low_risk_reward_blocks_aligned_setup() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT"),
            _node("15m", "SHORT"),
        ],
        bundles=_bundles(1.0),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.status == "BLOCKED"
    assert decision.primary_reason["code"] == "RISK_REWARD_BELOW_THRESHOLD"
    assert decision.recommended_leverage == 0


def test_risk_blocker_has_priority() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[_node("1d", "SHORT")],
        bundles=_bundles(),
        risk_alerts=[
            SimpleNamespace(severity="blocker", message="事件窗口", action="等待事件落地")
        ],
        position_cap="standard",
        next_check=None,
    )
    assert decision.status == "BLOCKED"
    assert decision.permission == "no_trade"
    assert decision.primary_reason["code"] == "RISK_GATE_BLOCKED"
    assert decision.max_leverage == 0


def test_warning_downgrades_ready_trade_to_three_x() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT"),
            _node("15m", "SHORT"),
        ],
        bundles=_bundles(),
        risk_alerts=[SimpleNamespace(severity="warning", message="拥挤度升高", action="降低杠杆")],
        position_cap="standard",
        next_check=None,
    )
    assert decision.status == "READY"
    assert decision.recommended_leverage == 3
    assert decision.max_leverage == 3
    assert decision.leverage_status == "risk_adjusted"


def test_upstream_hard_cap_is_never_exceeded() -> None:
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT"),
            _node("15m", "SHORT"),
        ],
        bundles=_bundles(max_leverage=3),
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.recommended_leverage == 3
    assert decision.max_leverage == 3


@pytest.mark.parametrize("legacy_cap", [None, 0])
def test_legacy_plan_without_usable_cap_inherits_platform_cap(legacy_cap: float | None) -> None:
    bundles = _bundles()
    if legacy_cap is None:
        bundles["4h"]["decision"]["short_plan"].pop("max_leverage")
    else:
        bundles["4h"]["decision"]["short_plan"]["max_leverage"] = legacy_cap
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT"),
            _node("15m", "SHORT"),
        ],
        bundles=bundles,
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.recommended_leverage == 5
    assert decision.max_leverage == 5


def test_leverage_cap_scans_all_same_side_legacy_plans() -> None:
    bundles = _bundles(max_leverage=0)
    bundles["1d"] = {
        "decision": {"short_plan": {**_bundles()["4h"]["decision"]["short_plan"]}}
    }
    decision = TradeDecisionEngine().build(
        nodes=[
            _node("1d", "SHORT"),
            _node("4h", "SHORT"),
            _node("1h", "SHORT"),
            _node("15m", "SHORT"),
        ],
        bundles=bundles,
        risk_alerts=[],
        position_cap="standard",
        next_check=None,
    )
    assert decision.max_leverage == 5


def test_strategy_frontend_separates_timeframe_and_aggregate_semantics() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    stack = (root / "app/static/pages/strategy/renderHorizonStack.js").read_text(encoding="utf-8")
    decision = (root / "app/static/pages/strategy/renderTradeDecision.js").read_text(
        encoding="utf-8"
    )
    crypto_surfaces = [
        root / "app/static/pages/analysis.js",
        root / "app/static/pages/monitoring.js",
        root / "app/static/pages/structure.js",
        root / "app/static/pages/btc_derivatives.js",
        root / "app/static/pages/strategy",
    ]
    assert "structureState" in stack
    assert "verdictLabel" not in stack
    assert "primary_reason" in decision
    for surface in crypto_surfaces:
        paths = [surface] if surface.is_file() else list(surface.glob("*.js"))
        for path in paths:
            assert "无优势" not in path.read_text(encoding="utf-8"), path
