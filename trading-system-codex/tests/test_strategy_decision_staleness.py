from __future__ import annotations

import pytest

from app.services.strategy_unified.trade_decision import (
    TradeDecisionEngine,
    reconcile_cached_strategy,
)


def _engine():
    return TradeDecisionEngine()


def test_staleness_returns_zero_when_price_inside_zone():
    """When the live price is already inside the planned entry zone
    there is no gap to surface — staleness score stays at 0 and the
    distance helper returns a 0% distance instead of pretending the
    user must travel through the price to trigger the order."""
    engine = _engine()
    distance_pct, stale_score, reason = engine._plan_distance_and_staleness(
        "SHORT", 64850.0, [64737.54, 64997.01], "CONDITIONAL_LIMIT"
    )
    assert distance_pct == 0
    assert stale_score == 0
    assert reason == ""


def test_staleness_classifies_warning_band_for_short_below_zone_distance():
    """The user's reported case: SHORT at 66,697 with the planned
    entry zone up around 64,737–64,997. The order cannot trigger
    until BTC drops ~2.6%, so this lands in the warning band
    (50/100 + "价格需先顺趋势运行") rather than the stale band.
    """
    engine = _engine()
    distance_pct, stale_score, reason = engine._plan_distance_and_staleness(
        "SHORT", 66697.4, [64737.54, 64997.01], "CONDITIONAL_LIMIT"
    )
    assert 2.0 <= distance_pct <= 3.0
    assert stale_score == 50
    assert "顺趋势运行" in reason


def test_staleness_classifies_stale_for_extreme_distance():
    """When the live price is more than 3% from the zone we classify
    the plan as outright stale — the trader should not be relying on
    it for a near-term decision and the message tells them so."""
    engine = _engine()
    distance_pct, stale_score, reason = engine._plan_distance_and_staleness(
        "SHORT", 70000.0, [64737.54, 64997.01], "CONDITIONAL_LIMIT"
    )
    assert distance_pct >= 3.0
    assert stale_score == 100
    assert "已远离入场区" in reason


def test_staleness_uses_correct_target_edge_per_side():
    """SHORT plans must measure gap to the upper zone edge (price must
    travel *down* to trigger); LONG plans measure gap to the lower
    edge (price must travel *up*). A LONG at 66,697 with zone
    [67,300, 67,500] must report ~0.9% distance to 67,300 — *not*
    ~1.2% to 67,500."""
    engine = _engine()
    short_d, _, _ = engine._plan_distance_and_staleness(
        "SHORT", 66697.0, [64737.54, 64997.01], "CONDITIONAL_LIMIT"
    )
    # Distance to upper edge (64,997) = 1,700 / 66,697 ≈ 2.55%
    assert 2.0 <= short_d <= 3.0

    long_d, _, _ = engine._plan_distance_and_staleness(
        "LONG", 66697.0, [67300.0, 67500.0], "CONDITIONAL_LIMIT"
    )
    # Distance to lower edge (67,300) = 603 / 66,697 ≈ 0.90%
    assert 0.7 <= long_d <= 1.0


def test_staleness_returns_zero_for_market_or_none_orders():
    """Stale awareness only applies to CONDITIONAL_LIMIT orders.
    MARKET orders execute immediately and NONE orders have no plan to
    drift from — both should return score 0 and an empty reason so
    the UI hides the stale chip."""
    engine = _engine()
    for order_type in ("MARKET", "NONE", ""):
        distance_pct, stale_score, reason = engine._plan_distance_and_staleness(
            "SHORT", 70000.0, [64737.54, 64997.01], order_type
        )
        assert distance_pct == 0
        assert stale_score == 0
        assert reason == ""


def test_staleness_handles_empty_zone_gracefully():
    engine = _engine()
    distance_pct, stale_score, reason = engine._plan_distance_and_staleness(
        "SHORT", 66697.0, [], "CONDITIONAL_LIMIT"
    )
    assert distance_pct == 0
    assert stale_score == 0
    assert reason == ""


def test_staleness_handles_none_price_gracefully():
    engine = _engine()
    distance_pct, stale_score, reason = engine._plan_distance_and_staleness(
        "SHORT", None, [64737.54, 64997.01], "CONDITIONAL_LIMIT"
    )
    assert distance_pct == 0
    assert stale_score == 0
    assert reason == ""


def test_screenshot_short_plan_uses_conservative_edge_and_fails_rr_gate() -> None:
    risk_reward = _engine()._planned_risk_reward(
        side="SHORT",
        entry_zone=[64_757.75, 65_017.30],
        fallback_entry=None,
        stop=65_861.23,
        targets=[64_150.25, 62_341.76],
        threshold=1.5,
    )

    assert risk_reward["entry_price_used"] == "64757.75"
    assert float(risk_reward["risk_amount"]) == pytest.approx(1_103.48)
    assert float(risk_reward["reward_amount"]) == pytest.approx(607.50)
    assert float(risk_reward["tp1_ratio"]) == pytest.approx(0.55053105)
    assert float(risk_reward["tp2_ratio"]) == pytest.approx(2.18942799)
    assert risk_reward["valid"] is True
    assert risk_reward["passed"] is False


def test_cached_untriggered_short_is_invalidated_above_stop_and_recompute_queued() -> None:
    cached = {
        "unified_state": {"permission": "conditional", "position_cap": "reduced"},
        "trade_decision": {
            "side": "SHORT",
            "status": "WAIT_TRIGGER",
            "permission": "conditional",
            "order_type": "CONDITIONAL_LIMIT",
            "order_status": "WAIT_PRICE",
            "lifecycle_state": "SETUP_DETECTED",
            "invalidation": 65_861.23,
            "entry_zone": [64_757.75, 65_017.30],
        },
        "trade_plans": [
            {
                "direction": "SHORT",
                "order_type": "CONDITIONAL_LIMIT",
                "permission": "conditional",
            }
        ],
    }

    guarded, invalidated = reconcile_cached_strategy(
        cached,
        latest_price=66_382,
        price_as_of="2026-07-22T01:45:00+00:00",
        price_source="gateio:futures.contracts",
    )

    assert invalidated is True
    assert guarded["trade_decision"]["lifecycle_state"] == "SETUP_INVALIDATED"
    assert guarded["trade_decision"]["order_status"] == "INVALIDATED"
    assert guarded["trade_decision"]["permission"] == "no_trade"
    assert guarded["unified_state"]["permission"] == "no_trade"
    assert guarded["recompute_status"] == "enqueued"


def test_cached_active_short_crossing_stop_is_recorded_as_stop_hit() -> None:
    cached = {
        "unified_state": {},
        "trade_decision": {
            "side": "SHORT",
            "lifecycle_state": "SHORT_TRIGGERED",
            "invalidation": 65_861.23,
        },
    }
    guarded, invalidated = reconcile_cached_strategy(
        cached,
        latest_price=66_382,
        price_as_of="2026-07-22T01:45:00+00:00",
        price_source="live",
    )

    assert invalidated is True
    assert guarded["trade_decision"]["lifecycle_state"] == "STOP_HIT"
