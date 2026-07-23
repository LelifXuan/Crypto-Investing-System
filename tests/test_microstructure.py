from decimal import Decimal

from app.services.microstructure import (
    TradeSample,
    aggregate_cvd_delta,
    summarize_depth_slippage,
    summarize_open_interest,
)


def test_aggregate_cvd_delta() -> None:
    result = aggregate_cvd_delta(
        [
            TradeSample(price=Decimal("100"), size=Decimal("2"), side="buy"),
            TradeSample(price=Decimal("101"), size=Decimal("1"), side="sell"),
        ],
        previous_cvd=Decimal("5"),
    )

    assert result.buy_volume == Decimal("2")
    assert result.sell_volume == Decimal("1")
    assert result.delta == Decimal("1")
    assert result.cvd == Decimal("6")


def test_open_interest_notional_and_change() -> None:
    result = summarize_open_interest(
        Decimal("10"),
        Decimal("100"),
        previous_open_interest=Decimal("8"),
        contract_multiplier=Decimal("0.1"),
    )

    assert result.open_interest_notional == Decimal("100.0")
    assert result.open_interest_change == Decimal("2")
    assert result.open_interest_change_pct == Decimal("0.25")


def test_depth_and_slippage_simulation() -> None:
    result = summarize_depth_slippage(
        [(Decimal("99"), Decimal("10")), (Decimal("98"), Decimal("10"))],
        [(Decimal("101"), Decimal("10")), (Decimal("102"), Decimal("10"))],
        notional=Decimal("1000"),
    )

    assert result.spread_bps == Decimal("200.00")
    assert result.depth_100bps == Decimal("2000")
    assert result.buy_slippage_bps is not None
    assert result.sell_slippage_bps is not None
