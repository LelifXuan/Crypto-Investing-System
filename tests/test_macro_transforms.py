"""Unit tests for ``app.services.macro.transforms``.

These tests cover the pure-function helpers used by the macro overview
service to compute year-over-year and month-over-month percent changes.

The transforms are intentionally tolerant: they return ``None`` for any
unparseable or zero-base input rather than raising, so the service layer
can fall back to the original observation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.services.macro.transforms import (
    compute_mom_change,
    compute_mom_pct,
    compute_yoy_pct,
)

UTC = timezone.utc


def _month(year: int, month: int) -> datetime:
    """Construct a UTC month-start datetime. month wraps 1..12."""
    while month < 1:
        year -= 1
        month += 12
    while month > 12:
        year += 1
        month -= 12
    return datetime(year, month, 1, tzinfo=UTC)


def _series(start_year: int, start_month: int, count: int, value):
    """Build a list of ``count`` consecutive monthly points starting at
    ``(start_year, start_month)`` all carrying the same ``value``."""
    return [
        (_month(start_year, start_month + i), value)
        for i in range(count)
    ]


class TestComputeYoyPct:
    def test_empty_list_returns_none(self):
        assert compute_yoy_pct([]) is None

    def test_single_point_returns_none(self):
        assert compute_yoy_pct([(_month(2026, 4), Decimal("100"))]) is None

    def test_twelve_points_returns_none(self):
        points = [(_month(2025, 4 + i if i < 9 else i - 8), Decimal("100")) for i in range(12)]
        # only 12 points, yoy needs 13
        assert compute_yoy_pct(points) is None

    def test_thirteen_flat_points_is_zero(self):
        points = _series(2025, 5, 13, Decimal("100"))
        result = compute_yoy_pct(points)
        assert result is not None
        value, ts = result
        assert value == Decimal("0")
        assert ts == _month(2026, 5)

    def test_three_percent_growth(self):
        # 12 months ago value is 100, latest is 103 → +3%
        points = _series(2025, 5, 12, Decimal("100"))
        points.append((_month(2026, 5), Decimal("103")))
        result = compute_yoy_pct(points)
        assert result is not None
        value, _ = result
        assert value == Decimal("3")

    def test_none_values_are_skipped(self):
        points = _series(2025, 5, 12, Decimal("100"))
        points.append((_month(2026, 5), None))
        # with None latest, only 12 usable points remain → insufficient
        assert compute_yoy_pct(points) is None

    def test_nan_string_is_skipped(self):
        points = _series(2025, 5, 13, "nan")
        assert compute_yoy_pct(points) is None

    def test_zero_base_returns_none(self):
        points = _series(2025, 5, 13, Decimal("0"))
        assert compute_yoy_pct(points) is None

    def test_negative_growth(self):
        # 12 months ago 100, latest 90 → -10%
        points = _series(2025, 5, 12, Decimal("100"))
        points.append((_month(2026, 5), Decimal("90")))
        result = compute_yoy_pct(points)
        assert result is not None
        value, _ = result
        assert value == Decimal("-10")

    def test_string_values_are_coerced(self):
        points = _series(2025, 5, 12, "100")
        points.append((_month(2026, 5), "103"))
        result = compute_yoy_pct(points)
        assert result is not None
        value, _ = result
        assert value == Decimal("3")


class TestComputeMomPct:
    def test_empty_list_returns_none(self):
        assert compute_mom_pct([]) is None

    def test_single_point_returns_none(self):
        assert compute_mom_pct([(_month(2026, 4), Decimal("100"))]) is None

    def test_one_percent_increase(self):
        points = [
            (_month(2026, 3), Decimal("100")),
            (_month(2026, 4), Decimal("101")),
        ]
        result = compute_mom_pct(points)
        assert result is not None
        value, ts = result
        assert value == Decimal("1")
        assert ts == _month(2026, 4)

    def test_zero_base_returns_none(self):
        points = [
            (_month(2026, 3), Decimal("0")),
            (_month(2026, 4), Decimal("101")),
        ]
        assert compute_mom_pct(points) is None

    def test_unordered_points_are_sorted(self):
        # intentionally reverse order
        points = [
            (_month(2026, 4), Decimal("110")),
            (_month(2026, 3), Decimal("100")),
        ]
        result = compute_mom_pct(points)
        assert result is not None
        value, _ = result
        assert value == Decimal("10")

    def test_nan_in_latest_returns_none(self):
        points = [
            (_month(2026, 3), Decimal("100")),
            (_month(2026, 4), float("nan")),
        ]
        assert compute_mom_pct(points) is None

    def test_inf_in_previous_returns_none(self):
        points = [
            (_month(2026, 3), float("inf")),
            (_month(2026, 4), Decimal("101")),
        ]
        assert compute_mom_pct(points) is None

    def test_garbage_string_returns_none(self):
        points = [
            (_month(2026, 3), "not-a-number"),
            (_month(2026, 4), Decimal("101")),
        ]
        assert compute_mom_pct(points) is None

    def test_garbage_string_in_middle_is_skipped(self):
        points = [
            (_month(2026, 2), Decimal("100")),
            (_month(2026, 3), "garbage"),
            (_month(2026, 4), Decimal("110")),
        ]
        # middle point is dropped, leaving 100→110 → +10%
        result = compute_mom_pct(points)
        assert result is not None
        value, _ = result
        assert value == Decimal("10")

    def test_zero_latest_is_treated_as_missing(self):
        # 0 is treated as missing so the function never produces division-by-zero
        points = [
            (_month(2026, 3), Decimal("100")),
            (_month(2026, 4), Decimal("0")),
        ]
        assert compute_mom_pct(points) is None


class TestComputeMomChange:
    def test_monthly_level_change(self):
        points = [
            (_month(2026, 4), Decimal("159500")),
            (_month(2026, 5), Decimal("159650")),
        ]
        result = compute_mom_change(points)
        assert result is not None
        value, ts = result
        assert value == Decimal("150")
        assert ts == _month(2026, 5)

    def test_zero_latest_is_valid(self):
        points = [
            (_month(2026, 4), Decimal("10")),
            (_month(2026, 5), Decimal("0")),
        ]
        result = compute_mom_change(points)
        assert result is not None
        value, _ = result
        assert value == Decimal("-10")

    def test_insufficient_points_returns_none(self):
        assert compute_mom_change([(_month(2026, 5), Decimal("159650"))]) is None
