from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

DECIMAL_ZERO = Decimal("0")
DECIMAL_Q18 = Decimal("0.000000000000000001")


def D(value: str | int | float | Decimal | None) -> Decimal:
    if value is None:
        return DECIMAL_ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_18(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_Q18, rounding=ROUND_HALF_UP)
