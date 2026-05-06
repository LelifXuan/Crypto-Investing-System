from __future__ import annotations

from app.services.chip_structure_decision_policy import (
    decide_chip_structure_action,
    suppress_futures_allocation,
)


def _decision(**overrides):
    values = {
        "direction_score": 60.0,
        "confidence_score": 82.0,
        "execution_score": 78.0,
        "risk_score": 20.0,
        "risk_label": "normal",
        "primary_state": "accumulation_confirmed",
        "secondary_scenario": "bullish_continuation_range",
        "recommended_action": "normal_trade",
        "execution_readiness": "confirmed",
        "higher_timeframe_conflict": False,
        "data_state": "available",
        "evidence_quality": "confirmed",
    }
    values.update(overrides)
    return decide_chip_structure_action(**values)


def test_screenshot_like_state_blocks_futures_even_with_good_execution() -> None:
    decision = _decision(
        direction_score=60,
        confidence_score=82,
        execution_score=78,
        primary_state="balanced_auction",
        secondary_scenario="liquidity_drought",
        recommended_action="wait_confirmation",
        execution_readiness="waiting_confirmation",
    )
    capital = suppress_futures_allocation(
        {
            "total_max_pct": 10.0,
            "spot_max_pct": 10.0,
            "futures_min_pct": 5.0,
            "futures_max_pct": 5.0,
            "futures_label": "5%",
            "reason": "old",
            "allocation_reason": "old",
        },
        decision,
    )

    assert decision.allow_futures_long is False
    assert capital["futures_min_pct"] == 0
    assert capital["futures_max_pct"] == 0
    assert capital["futures_label"] == "0%"
    assert "不建议开合约" in capital["allocation_reason"]


def test_all_gates_pass_allows_futures_long() -> None:
    decision = _decision(direction_score=78)

    assert decision.allow_futures_long is True
    assert not decision.failed_gate_reasons
    assert all(item.passed for item in decision.gate_checks)


def test_unavailable_data_blocks_futures() -> None:
    decision = _decision(data_state="missing", evidence_quality="proxy_only")

    assert decision.allow_futures_long is False
    failed = {item.key for item in decision.gate_checks if not item.passed}
    assert {"data_state", "evidence_quality"} <= failed
    assert "当前不建议开多合约" in decision.why_no_futures_long
