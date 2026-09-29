from decimal import Decimal
from types import SimpleNamespace

from app.api.v1.endpoints.strategy import _block_cached_strategy_for_price
from app.services.strategy_unified.opportunity_scanner import _extract_scan_item
from app.services.strategy_unified.period_opportunity import build_period_opportunities


def node(timeframe: str, direction: str):
    return SimpleNamespace(
        timeframe=timeframe,
        direction=direction,
        freshness="fresh",
        confidence=92,
        evidence=[f"{timeframe}: {direction}"],
        invalidation=None,
        key_support=None,
        key_resistance=None,
    )


def bundle(
    side: str, entry: str, *, target_delta: str = "10", stop_delta: str = "3", atr_pct: str = "3"
):
    value = Decimal(entry)
    target_move = Decimal(target_delta)
    stop_move = Decimal(stop_delta)
    if side == "LONG":
        plan = {
            "direction": side,
            "entry_zone": [str(value), str(value + 1)],
            "stop_price": str(value - stop_move),
            "take_profit_1": str(value + target_move),
            "capital_pct": 5,
        }
        return {
            "decision": {"long_plan": plan, "strategy_state": "LONG_TRIGGERED"},
            "snapshot": {"atr_pct": atr_pct},
        }
    plan = {
        "direction": side,
        "entry_zone": [str(value), str(value + 1)],
        "stop_price": str(value + stop_move),
        "take_profit_1": str(value - target_move),
        "capital_pct": 5,
    }
    return {
        "decision": {"short_plan": plan, "strategy_state": "SHORT_TRIGGERED"},
        "snapshot": {"atr_pct": atr_pct},
    }


def test_fifteen_distinct_instrument_period_opportunities():
    ids = set()
    for instrument in ("btc", "eth", "hype", "bnb", "okb"):
        result = build_period_opportunities(
            instrument,
            [
                node("1M", "LONG"),
                node("1w", "LONG"),
                node("1d", "LONG"),
                node("4h", "LONG"),
                node("1h", "LONG"),
            ],
            {
                "1w": bundle("LONG", "100", target_delta="45", stop_delta="8", atr_pct="12"),
                "1d": bundle("LONG", "100", target_delta="25", stop_delta="4", atr_pct="6"),
                "4h": bundle("LONG", "101", target_delta="14", stop_delta="3", atr_pct="3"),
                "1h": bundle("LONG", "102", target_delta="5", stop_delta="2", atr_pct="1.5"),
            },
            [],
        )
        assert set(result) == {"1w", "1d", "4h"}
        assert [result[tf]["execution_timeframe"] for tf in ("1w", "1d", "4h")] == [
            "1d",
            "4h",
            "1h",
        ]
        assert all(result[tf]["status"] == "READY" for tf in result)
        assert [result[tf]["recommended_leverage"] for tf in ("1w", "1d", "4h")] == [1, 2, 3]
        assert [result[tf]["invalidation_price"] for tf in ("1w", "1d", "4h")] == ["92", "96", "98"]
        assert [result[tf]["expected_move_pct"] for tf in ("1w", "1d", "4h")] != [None] * 3
        assert len({result[tf]["risk_reward"]["value"] for tf in result}) == 3
        ids.update(item["opportunity_id"] for item in result.values())
    assert len(ids) == 15


def test_4h_short_survives_neutral_daily_and_weekly_long_has_own_plan():
    decisions = build_period_opportunities(
        "hype",
        [
            node("1M", "LONG"),
            node("1w", "LONG"),
            node("1d", "NEUTRAL"),
            node("4h", "SHORT"),
            node("1h", "SHORT"),
        ],
        {
            "1w": bundle("LONG", "100", target_delta="45"),
            "1d": bundle("LONG", "100", target_delta="25"),
            "4h": bundle("SHORT", "90", target_delta="20", stop_delta="5"),
            "1h": bundle("SHORT", "90", target_delta="10", stop_delta="4"),
        },
        [],
    )
    assert decisions["1w"]["side"] == "LONG"
    assert decisions["1w"]["execution_timeframe"] == "1d"
    assert decisions["1d"]["side"] == "NONE"
    assert decisions["4h"]["side"] == "SHORT"
    assert decisions["4h"]["execution_timeframe"] == "1h"
    assert decisions["4h"]["entry_zone"] == ["90", "91"]
    assert decisions["4h"]["invalidation_price"] == "95"
    assert decisions["4h"]["horizon_target"] == "70"


def test_invalid_execution_geometry_cannot_publish_order():
    bad = bundle("SHORT", "90")
    bad["decision"]["short_plan"]["stop_price"] = "85"
    result = build_period_opportunities(
        "hype",
        [node("4h", "SHORT"), node("1h", "SHORT")],
        {"4h": bundle("SHORT", "90", target_delta="20"), "1h": bad},
        [],
    )["4h"]
    assert result["status"] == "WAIT_LEVELS"
    assert result["permission"] == "observe"
    assert result["entry_zone"] == []


def test_aligned_bias_without_execution_trigger_remains_conditional():
    waiting = bundle("SHORT", "90")
    waiting["decision"]["strategy_state"] = "CONTEXT_SHORT"
    waiting["decision"]["short_plan"]["capital_pct"] = 0
    decision = build_period_opportunities(
        "hype",
        [node("4h", "SHORT"), node("1h", "SHORT")],
        {"4h": bundle("SHORT", "90", target_delta="20"), "1h": waiting},
        [],
    )["4h"]
    assert decision["status"] == "WAIT_TRIGGER"
    assert decision["permission"] == "conditional"


def test_matrix_projects_same_decision_as_drawer():
    decision = build_period_opportunities(
        "hype",
        [node("4h", "SHORT"), node("1h", "SHORT")],
        {
            "4h": bundle("SHORT", "90", target_delta="20", stop_delta="5"),
            "1h": bundle("SHORT", "90", target_delta="10", stop_delta="4"),
        },
        [],
    )["4h"]
    payload = {
        "status": "ready",
        "opportunity_decisions": {"4h": decision},
        "timeframe_stack": [
            {"timeframe": "4h", "direction": "SHORT", "freshness": "fresh", "confidence": 92}
        ],
        "trade_decision": {"side": "NONE", "permission": "observe"},
    }
    item = _extract_scan_item(payload, "hype", "HYPE", "4h")
    assert item.direction == decision["side"]
    assert item.entry_zone == [float(value) for value in decision["entry_zone"]]
    assert item.stop_loss == float(decision["invalidation_price"])
    assert item.horizon_target == float(decision["horizon_target"])
    assert item.first_risk_reward == float(decision["first_risk_reward"])
    assert item.expected_move_pct == float(decision["expected_move_pct"])
    payload["opportunity_decisions"]["4h"] = {**decision, "take_profit_1": "110"}
    invalid_target = _extract_scan_item(payload, "hype", "HYPE", "4h")
    assert not invalid_target.qualified
    assert invalid_target.direction == "WAIT"
    assert invalid_target.entry_zone == []


def test_direction_without_execution_bundle_is_not_a_listed_opportunity():
    decision = build_period_opportunities(
        "eth",
        [node("4h", "LONG"), node("1h", "NEUTRAL")],
        {"4h": bundle("LONG", "2700", target_delta="80", atr_pct="2")},
        [],
    )["4h"]
    assert decision["side"] == "LONG"
    assert decision["status"] == "WAIT_LEVELS"
    payload = {
        "status": "ready",
        "opportunity_decisions": {"4h": decision},
        "timeframe_stack": [
            {"timeframe": "4h", "direction": "LONG", "freshness": "fresh", "confidence": 91}
        ],
    }
    item = _extract_scan_item(payload, "eth", "ETH", "4h")
    assert item.qualified is False
    assert item.direction == "WAIT"
    assert item.entry_zone == []
    assert item.leverage_hint == "仅观察"


def test_stale_price_revokes_all_period_levels_and_leverage():
    decision = build_period_opportunities(
        "hype",
        [node(tf, "SHORT") for tf in ("1M", "1w", "1d", "4h", "1h")],
        {
            tf: bundle("SHORT", "90", target_delta=str(delta))
            for tf, delta in (("1w", 50), ("1d", 35), ("4h", 20), ("1h", 10))
        },
        [],
    )
    payload = {"opportunity_decisions": decision, "trade_plans": []}
    blocked = _block_cached_strategy_for_price(
        payload, status="PRICE_UNAVAILABLE", message="价格已过期"
    )
    for item in blocked["opportunity_decisions"].values():
        assert item["permission"] == "observe"
        assert item["entry_zone"] == []
        assert item["horizon_target"] is None
        assert item["risk_reward"] == {"value": None, "passed": False}
        assert item["planned_leverage"] == 0
