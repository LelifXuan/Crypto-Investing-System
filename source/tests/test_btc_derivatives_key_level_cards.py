from __future__ import annotations

import pytest

from app.services.btc_derivatives.market_state_engine import build_key_level_cards


def test_key_level_cards_include_relative_position_movement_and_current_meaning() -> None:
    cards = build_key_level_cards(
        spot_price=61_200,
        call_wall=65_000,
        put_wall=45_000,
        max_pain=60_000,
        maturity_bucket="60D",
        source_expiry="2026-07-31",
        source_dte=37,
        wall_movement={"call_wall": "rising", "put_wall": "stable"},
        max_pain_movement="rising",
    )

    assert [card["id"] for card in cards] == [
        "call_wall",
        "put_wall",
        "max_pain",
        "constant_maturity",
    ]
    assert cards[0]["distance_pct"] == pytest.approx((65_000 - 61_200) / 61_200)
    assert cards[0]["movement"] == "上移"
    assert "空网格" in cards[0]["current_meaning"]
    assert cards[2]["movement"] == "上移"
    assert "持仓分布重心" in cards[2]["current_meaning"]
    assert cards[3]["distance_pct"] is None
    assert "2026-07-31" in cards[3]["current_meaning"]
    assert cards[3]["knowledge_term"] == "Constant Maturity"


def test_key_level_cards_degrade_cleanly_when_chain_data_is_missing() -> None:
    cards = build_key_level_cards(
        spot_price=61_200,
        call_wall=None,
        put_wall=None,
        max_pain=None,
        maturity_bucket="60D",
        source_expiry=None,
        source_dte=None,
        wall_movement={},
        max_pain_movement="data_insufficient",
    )

    assert all(card["current_meaning"] for card in cards)
    assert cards[0]["value"] is None
    assert cards[0]["movement"] == "历史不足"
    assert "当前链数据不足" in cards[0]["current_meaning"]
