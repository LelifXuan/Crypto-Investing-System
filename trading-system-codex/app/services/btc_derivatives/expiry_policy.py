from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable


@dataclass(frozen=True)
class ExpiryClassification:
    expiry: str
    expiry_date: date | None
    dte: int | None
    is_standard: bool
    cycle: str
    exclusion_reason: str | None = None

    def as_dict(self) -> dict[str, object | None]:
        return {
            "expiry": self.expiry,
            "dte": self.dte,
            "is_standard": self.is_standard,
            "cycle": self.cycle,
            "exclusion_reason": self.exclusion_reason,
        }


def parse_expiry(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def last_friday(year: int, month: int) -> date:
    day = date(year, month, monthrange(year, month)[1])
    while day.weekday() != 4:
        day -= timedelta(days=1)
    return day


def classify_expiry(value: object, *, as_of: date) -> ExpiryClassification:
    expiry_text = str(value or "")[:10]
    expiry_date = parse_expiry(value)
    if expiry_date is None:
        return ExpiryClassification(
            expiry_text, None, None, False, "INVALID", "invalid_expiry"
        )
    dte = (expiry_date - as_of).days
    if dte <= 0:
        return ExpiryClassification(
            expiry_text, expiry_date, dte, False, "EXPIRED", "expired"
        )
    is_standard = expiry_date == last_friday(expiry_date.year, expiry_date.month)
    if not is_standard:
        return ExpiryClassification(
            expiry_text,
            expiry_date,
            dte,
            False,
            "NON_STANDARD",
            "not_month_end_friday",
        )
    cycle = "QUARTERLY" if expiry_date.month in {3, 6, 9, 12} else "MONTHLY"
    return ExpiryClassification(expiry_text, expiry_date, dte, True, cycle)


def standard_expiries(values: Iterable[str], *, as_of: date) -> list[str]:
    return sorted(
        {
            value
            for value in values
            if classify_expiry(value, as_of=as_of).is_standard
        }
    )


def nearest_standard_expiry(
    values: Iterable[str], *, as_of: date, target_dte: int
) -> str | None:
    candidates = [
        classification
        for value in values
        if (classification := classify_expiry(value, as_of=as_of)).is_standard
        and classification.dte is not None
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (abs((item.dte or 0) - target_dte), item.dte or 0),
    ).expiry
