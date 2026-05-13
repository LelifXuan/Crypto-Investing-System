from datetime import datetime, timezone
from decimal import Decimal

from app.services.pnl import PnLService


class DummyFX:
    def __init__(self, rate: str) -> None:
        self.rate = Decimal(rate)


class DummyRepo:
    def __init__(self) -> None:
        self.direct = {("USDT", "USD"): DummyFX("1"), ("EUR", "USD"): DummyFX("1.2")}
        self.inverse = {("USD", "JPY"): DummyFX("150")}

    async def latest_fx_rate(self, base_currency: str, quote_currency: str, as_of_ts: datetime | None = None):
        pair = (base_currency, quote_currency)
        return self.direct.get(pair) or self.inverse.get(pair)


def test_normalize_cash_amount() -> None:
    assert PnLService.normalize_cash_amount("DEPOSIT", Decimal("100")) == Decimal("100")
    assert PnLService.normalize_cash_amount("WITHDRAWAL", Decimal("100")) == Decimal("-100")


async def test_convert_amount_direct_and_inverse() -> None:
    service = PnLService(DummyRepo())  # type: ignore[arg-type]
    as_of = datetime.now(timezone.utc)
    direct, _ = await service.convert_amount(Decimal("10"), "EUR", "USD", as_of)
    inverse, _ = await service.convert_amount(Decimal("1500"), "JPY", "USD", as_of)
    assert direct == Decimal("12.0")
    assert inverse == Decimal("10")
