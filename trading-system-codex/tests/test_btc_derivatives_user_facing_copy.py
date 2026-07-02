from __future__ import annotations

from app.services.btc_derivatives.market_state_engine import (
    build_market_state,
    decision_cards,
)


def _analysis(**overrides: object) -> dict:
    inputs = {
        "price_oi_state": "price_up_oi_up",
        "funding_state": "positive_hot",
        "iv_state": "iv_high",
        "skew_state": "put_skew_high",
        "wall_movement": {"call_wall": "rising", "put_wall": "stable"},
        "max_pain_movement": "rising",
        "data_quality_status": "partial",
        "basis_state": "basis_rising",
        "hedge_cost_state": "expensive",
    }
    inputs.update(overrides)
    return build_market_state(**inputs)


def test_market_state_exposes_chinese_display_items_and_four_inference_blocks() -> None:
    analysis = _analysis()

    assert len(analysis["inference_blocks"]) == 4
    assert {item["id"] for item in analysis["inference_blocks"]} == {
        "futures",
        "options",
        "key_levels",
        "hedge_cost",
    }
    assert analysis["evidence_groups"]["futures"]["signals"] == [
        "price_up_oi_up",
        "positive_hot",
        "basis_rising",
    ]
    visible = str(analysis["display_items"]) + str(analysis["inference_blocks"])
    assert "价格上涨且持仓增加" in visible
    assert "资金费率偏热" in visible
    key_block = next(
        item for item in analysis["inference_blocks"] if item["id"] == "key_levels"
    )
    assert "Call Wall 上移" in key_block["basis"]
    assert "Put Wall 稳定" in key_block["basis"]
    assert "Max Pain 上移" in key_block["basis"]
    assert "price_up_oi_up" not in visible
    assert "funding_overheated" not in visible


def test_unknown_signal_never_becomes_visible_snake_case_copy() -> None:
    analysis = _analysis(
        price_oi_state="unmapped_internal_signal",
        funding_state="unmapped_funding_state",
    )

    visible = str(analysis["display_items"]) + str(analysis["inference_blocks"])
    assert "unmapped_internal_signal" not in visible
    assert "unmapped_funding_state" not in visible
    assert "解释暂不可用" in visible


def test_decision_cards_use_chinese_conclusion_basis_and_implication_only() -> None:
    cards = decision_cards(_analysis())

    assert [card["id"] for card in cards] == [
        "market_state",
        "primary_risk",
        "strategy_implication",
    ]
    assert all(card["conclusion"] for card in cards)
    assert all(isinstance(card["basis"], list) for card in cards)
    assert all(card["implication"] for card in cards)
    visible = str(cards)
    assert "price_up_oi_up" not in visible
    assert "upside_squeeze_risk" not in visible
    assert "不输出直接买卖命令" not in visible
    assert "score" not in cards[0]


def test_directionless_and_expensive_hedge_can_be_high_confidence() -> None:
    analysis = _analysis(
        price_oi_state="flat",
        funding_state="neutral",
        iv_state="iv_neutral",
        skew_state="skew_neutral",
        wall_movement={"call_wall": "stable", "put_wall": "stable"},
        max_pain_movement="stable",
        data_quality_status="live",
        basis_state="neutral",
        hedge_cost_state="expensive",
    )
    cards = decision_cards(analysis)

    assert cards[0]["conclusion"] == "杠杆资金暂未形成清晰方向"
    assert cards[0]["confidence"] == "high"
    assert cards[2]["conclusion"] == "保护成本偏高"
    assert cards[2]["confidence"] == "high"
