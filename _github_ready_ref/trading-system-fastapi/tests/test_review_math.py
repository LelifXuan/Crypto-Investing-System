from datetime import datetime, timezone
from decimal import Decimal

from app.services.reviews import ReviewService


class Snap:
    def __init__(self, equity: str, ts: int) -> None:
        self.equity = Decimal(equity)
        self.as_of_ts = datetime.fromtimestamp(ts, tz=timezone.utc)


def test_max_drawdown() -> None:
    snaps = [Snap("100", 1), Snap("120", 2), Snap("90", 3), Snap("130", 4), Snap("100", 5)]
    dd = ReviewService.compute_max_drawdown(snaps)  # type: ignore[arg-type]
    assert dd == Decimal("0.25")
