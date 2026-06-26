from __future__ import annotations

from app.services.btc_derivatives.models import OptionQuote
from app.services.btc_derivatives.options_metrics import (
    chain_rows_for_expiry,
    liquidity_class,
    max_pain,
    option_walls,
    put_call_ratios,
    skew_25d,
)


def _quotes() -> list[OptionQuote]:
    expiry = "2026-09-25"
    return [
        OptionQuote(
            expiry, 90, "call", bid=11, ask=12, iv=0.55, delta=0.70, open_interest=10, volume_24h=5
        ),
        OptionQuote(
            expiry,
            90,
            "put",
            bid=1,
            ask=1.05,
            iv=0.70,
            delta=-0.25,
            open_interest=50,
            volume_24h=20,
        ),
        OptionQuote(
            expiry,
            100,
            "call",
            bid=6,
            ask=6.2,
            iv=0.50,
            delta=0.50,
            open_interest=30,
            volume_24h=10,
        ),
        OptionQuote(
            expiry, 100, "put", bid=5, ask=5.2, iv=0.52, delta=-0.50, open_interest=20, volume_24h=8
        ),
        OptionQuote(
            expiry,
            110,
            "call",
            bid=2,
            ask=2.08,
            iv=0.58,
            delta=0.25,
            open_interest=60,
            volume_24h=30,
        ),
        OptionQuote(
            expiry, 110, "put", bid=10, ask=11, iv=0.60, delta=-0.70, open_interest=10, volume_24h=4
        ),
    ]


def test_option_walls_and_max_pain_use_open_interest_distribution() -> None:
    rows = chain_rows_for_expiry(_quotes(), "2026-09-25")

    walls = option_walls(rows)
    pain = max_pain(rows)

    assert walls["call_wall_strike"] == 110
    assert walls["put_wall_strike"] == 90
    assert pain["strike"] == 100
    assert "不是价格预测" in pain["warning"]
    assert "不是确定支撑或阻力" in walls["warning"]


def test_skew_ratios_and_liquidity_handle_partial_data() -> None:
    quotes = _quotes()
    rows = chain_rows_for_expiry(quotes, "2026-09-25")

    skew = skew_25d(quotes)
    ratios = put_call_ratios(rows)

    assert skew["status"] == "ok"
    assert skew["put_call_skew"] == 0.12
    assert ratios["put_call_oi_ratio"] == 80 / 100
    assert ratios["put_call_volume_ratio"] == 32 / 45
    assert liquidity_class(quotes[4]) == "good"
    assert (
        liquidity_class(OptionQuote("2026-09-25", 120, "call", bid=None, ask=1, open_interest=20))
        == "poor"
    )
    assert (
        skew_25d([OptionQuote("2026-09-25", 100, "call", iv=None, delta=0.25)])["status"]
        == "data_insufficient"
    )
