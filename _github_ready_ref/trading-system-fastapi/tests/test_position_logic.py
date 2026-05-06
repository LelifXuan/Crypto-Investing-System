from decimal import Decimal

from app.services.positions import PositionService, PositionState


class DummyFill:
    def __init__(self, side: str, qty: str, price: str, fee: str = "0") -> None:
        self.side = side
        self.qty = Decimal(qty)
        self.price = Decimal(price)
        self.fee = Decimal(fee)


def test_avg_cost_rebuild_basic() -> None:
    service = PositionService(repository=None)  # type: ignore[arg-type]
    fills = [
        DummyFill("BUY", "1", "100"),
        DummyFill("BUY", "1", "120"),
        DummyFill("SELL", "1", "150"),
    ]
    state = service._rebuild_bucket(fills, "AVG_COST")
    assert state.signed_qty == Decimal("1")
    assert state.avg_cost_price == Decimal("110")
    assert state.realized_pnl == Decimal("40")


def test_fifo_rebuild_basic() -> None:
    service = PositionService(repository=None)  # type: ignore[arg-type]
    fills = [
        DummyFill("BUY", "1", "100"),
        DummyFill("BUY", "1", "120"),
        DummyFill("SELL", "1", "150"),
    ]
    state = service._rebuild_bucket(fills, "FIFO")
    assert state.signed_qty == Decimal("1")
    assert state.avg_cost_price == Decimal("120")
    assert state.realized_pnl == Decimal("50")
