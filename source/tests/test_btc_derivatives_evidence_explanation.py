from __future__ import annotations

from app.services.btc_derivatives.market_state_engine import build_market_state


def test_evidence_layer_is_grouped_by_market_function_and_explains_conflicts() -> None:
    result = build_market_state(
        price_oi_state="price_up_oi_up",
        funding_state="positive_hot",
        iv_state="iv_high",
        skew_state="call_skew_high",
        wall_movement={"call_wall": "rising", "put_wall": "stable"},
        max_pain_movement="rising",
        data_quality_status="partial",
        basis_state="basis_rising",
        hedge_cost_state="expensive",
        technical_bias="bearish",
    )

    assert set(result["evidence_groups"]) == {
        "futures",
        "options",
        "key_levels",
        "hedge_cost",
    }
    assert result["supports_long"]
    assert result["weakens_short"]
    assert result["conflicts"]
    assert any("技术面偏空" in item for item in result["conflicts"])
    assert result["direct_command"].startswith("none")
    assert "价格预测" in " ".join(result["warnings"])
