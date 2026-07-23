"""Pure-function helpers for macro indicator transforms.

These helpers are intentionally side-effect free. The provider layer is
responsible for fetching the raw history; this module only does arithmetic
on already-fetched points. Failures return None so the caller can fall
back to the original observation without losing the row.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

Point = tuple[datetime, object]
"""A single (timestamp, value) point. Value can be Decimal, float, int, or str."""


def _coerce_value(value: object) -> Optional[Decimal]:
    """Coerce a value into Decimal. Returns None for missing/zero/NaN/inf/garbage.

    ``0`` is intentionally coerced to None because macro percent transforms
    divide by the base value — a zero base would explode. Callers that want
    to preserve literal zero should not route through this helper.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        invalid_strings = {
            "nan",
            "inf",
            "-inf",
            "infinity",
            "-infinity",
            ".",
            "null",
            "none",
        }
        if not text or text.lower() in invalid_strings:
            return None
        try:
            numeric = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
    elif isinstance(value, Decimal):
        numeric = value
    elif isinstance(value, (int, float)):
        try:
            numeric = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    else:
        return None
    if not numeric.is_finite():
        return None
    if numeric == 0:
        return None
    return numeric


def _normalize_points(points: Iterable[Point]) -> list[tuple[datetime, Decimal]]:
    """Sort ascending by timestamp and drop unparseable / zero / NaN values."""
    cleaned: list[tuple[datetime, Decimal]] = []
    for ts, value in points:
        if ts is None:
            continue
        coerced = _coerce_value(value)
        if coerced is None:
            continue
        cleaned.append((ts, coerced))
    cleaned.sort(key=lambda item: item[0])
    return cleaned


def compute_yoy_pct(points: Iterable[Point]) -> Optional[tuple[Decimal, datetime]]:
    """Compute year-over-year percent change.

    Requires at least 13 ascending points. Returns
    ``(percent, latest_ts)`` or ``None`` if the computation cannot be
    performed safely (insufficient points, zero base, unparseable data).

    The base is the point closest to 12 months before the latest point.
    We do not assume points are exactly one month apart; we simply pick
    the point with the largest timestamp that is still <= (latest - 365d)
    with a tolerance, falling back to the 12th-from-last if no point
    falls in the window.
    """
    series = _normalize_points(points)
    if len(series) < 13:
        return None
    latest_ts, latest_value = series[-1]
    base_ts = latest_ts.replace(year=latest_ts.year - 1)
    base_index = None
    for index in range(len(series) - 2, -1, -1):
        candidate_ts, _ = series[index]
        if candidate_ts <= base_ts:
            base_index = index
            break
    if base_index is None:
        base_index = len(series) - 13
    if base_index < 0:
        return None
    base_value = series[base_index][1]
    if base_value == 0:
        return None
    try:
        ratio = latest_value / base_value
    except (InvalidOperation, ZeroDivisionError):
        return None
    return ((ratio - Decimal(1)) * Decimal(100), latest_ts)


def compute_mom_pct(points: Iterable[Point]) -> Optional[tuple[Decimal, datetime]]:
    """Compute month-over-month percent change.

    Requires at least 2 ascending points. Returns
    ``(percent, latest_ts)`` or ``None`` if the computation cannot be
    performed safely.
    """
    series = _normalize_points(points)
    if len(series) < 2:
        return None
    latest_ts, latest_value = series[-1]
    previous_value = series[-2][1]
    if previous_value == 0:
        return None
    try:
        ratio = latest_value / previous_value
    except (InvalidOperation, ZeroDivisionError):
        return None
    return ((ratio - Decimal(1)) * Decimal(100), latest_ts)


def compute_mom_change(points: Iterable[Point]) -> Optional[tuple[Decimal, datetime]]:
    """Compute the absolute month-over-month change.

    This is used for level series whose headline release is a monthly
    difference, such as nonfarm payrolls. Unlike percent transforms, a literal
    zero latest value is valid input for this calculation.
    """
    cleaned: list[tuple[datetime, Decimal]] = []
    for ts, value in points:
        if ts is None or value is None:
            continue
        if isinstance(value, str) and value.strip() in {"", "."}:
            continue
        try:
            numeric = Decimal(str(value).strip()) if isinstance(value, str) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue
        if not numeric.is_finite():
            continue
        cleaned.append((ts, numeric))
    cleaned.sort(key=lambda item: item[0])
    if len(cleaned) < 2:
        return None
    latest_ts, latest_value = cleaned[-1]
    previous_value = cleaned[-2][1]
    return latest_value - previous_value, latest_ts


def compute_weekly_diff_rolling_4w(
    points: Iterable[Point], *, window: int = 4
) -> Optional[tuple[Decimal, datetime]]:
    """Return ``latest - value(window weeks ago)`` over a weekly cadence.

    Used for "TGA NET CHANGE 4W" style indicators that need a 4-week
    rolling diff. Returns ``None`` when there are fewer than ``window + 1``
    valid weekly points.
    """
    if window < 1:
        return None
    cleaned: list[tuple[datetime, Decimal]] = []
    for ts, value in points:
        if ts is None or value is None:
            continue
        if isinstance(value, str) and value.strip() in {"", "."}:
            continue
        try:
            numeric = Decimal(str(value).strip()) if isinstance(value, str) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue
        if not numeric.is_finite():
            continue
        cleaned.append((ts, numeric))
    cleaned.sort(key=lambda item: item[0])
    if len(cleaned) <= window:
        return None
    latest_ts, latest_value = cleaned[-1]
    baseline_value = cleaned[-(window + 1)][1]
    return latest_value - baseline_value, latest_ts
