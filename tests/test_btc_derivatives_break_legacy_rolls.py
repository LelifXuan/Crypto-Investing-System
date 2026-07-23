"""Tests for `_break_legacy_rolls` exception rules.

This module pins down two behaviours:

1. When the dashboard request is in ``expiry_mode == "constant_maturity"``,
   an expiry rollover between adjacent history points must NOT NULL out the
   three protection-cost keys or stamp ``series_break_reason``. The whole point
   of constant-maturity mode is that the service interpolates between the two
   nearest standard expiries, so consecutive cache entries can legitimately
   land on different ``source_expiry`` values without invalidating the series.

2. ``method_change`` (e.g. legacy ``otm_estimate`` → ``constant_delta``)
   continues to break the series in BOTH modes. That transition is a real
   change in calculation policy and is not recoverable by interpolation.
"""

from __future__ import annotations

from typing import Any

from app.services.btc_derivatives.service import _break_legacy_rolls


COST_KEYS = (
    "call_protection_cost_pct",
    "put_protection_cost_pct",
    "debit_spread_cost_pct",
)


def _row(
    *,
    timestamp: str,
    source_expiry: str,
    method: str = "otm_estimate",
    interpolated: bool = False,
    call: float = 0.025,
    put: float = 0.030,
    debit: float = 0.018,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "source_expiry": source_expiry,
        "selection_method": method,
        "constant_maturity_interpolated": interpolated,
        "call_protection_cost_pct": call,
        "put_protection_cost_pct": put,
        "debit_spread_cost_pct": debit,
    }


# ---------------------------------------------------------------------------
# Behaviour 1: constant_maturity mode suppresses expiry_rollover breaks
# ---------------------------------------------------------------------------


def test_constant_maturity_mode_does_not_break_on_expiry_rollover() -> None:
    """Adjacent rows with different source_expiry in constant_maturity mode stay continuous."""

    history = [
        _row(timestamp="2026-07-13T08:23", source_expiry="2026-08-28"),
        # Different source_expiry, no interpolated marker → would normally trigger
        # expiry_rollover, but the user is in constant_maturity mode.
        _row(timestamp="2026-07-14T05:39", source_expiry="2026-09-25"),
        _row(timestamp="2026-07-14T09:46", source_expiry="2026-09-25"),
    ]

    result = _break_legacy_rolls(history, expiry_mode="constant_maturity")

    for index, point in enumerate(result):
        for key in COST_KEYS:
            assert point[key] == history[index][key], (
                f"cost key {key} was unexpectedly NULL-ed at index {index}: {point}"
            )
        assert "series_break_reason" not in point, (
            f"series_break_reason should not be set in constant_maturity mode: {point}"
        )


# ---------------------------------------------------------------------------
# Behaviour 2: fixed mode preserves the original expiry_rollover behaviour
# ---------------------------------------------------------------------------


def test_fixed_mode_still_breaks_on_expiry_rollover() -> None:
    """When expiry_mode == 'fixed', the legacy expiry_rollover NULL-out must still happen."""

    history = [
        _row(timestamp="2026-07-13T08:23", source_expiry="2026-08-28"),
        _row(timestamp="2026-07-14T05:39", source_expiry="2026-09-25"),
    ]

    result = _break_legacy_rolls(history, expiry_mode="fixed")

    second = result[1]
    for key in COST_KEYS:
        assert second[key] is None, f"expected {key} NULL-ed in fixed mode, got {second[key]}"
    assert second["series_break_reason"] == "expiry_rollover"


# ---------------------------------------------------------------------------
# Behaviour 3: method_change continues to break in BOTH modes
# ---------------------------------------------------------------------------


def test_method_change_breaks_in_constant_maturity_mode() -> None:
    """Switching calculation method is a real policy change and must break the series."""

    history = [
        _row(timestamp="2026-07-14T05:39", source_expiry="2026-09-25", method="otm_estimate"),
        _row(
            timestamp="2026-07-14T09:46",
            source_expiry="2026-09-25",
            method="constant_delta",
        ),
    ]

    result = _break_legacy_rolls(history, expiry_mode="constant_maturity")

    second = result[1]
    for key in COST_KEYS:
        assert second[key] is None, f"method_change should still NULL {key}"
    assert second["series_break_reason"] == "method_change"


def test_method_change_breaks_in_fixed_mode() -> None:
    history = [
        _row(timestamp="2026-07-14T05:39", source_expiry="2026-09-25", method="otm_estimate"),
        _row(
            timestamp="2026-07-14T09:46",
            source_expiry="2026-09-25",
            method="constant_delta",
        ),
    ]

    result = _break_legacy_rolls(history, expiry_mode="fixed")

    second = result[1]
    assert second["series_break_reason"] == "method_change"
    for key in COST_KEYS:
        assert second[key] is None


# ---------------------------------------------------------------------------
# Behaviour 4: each break point carries a human-readable detail string so the
# chart_builder can render "到期日切换：08-28 → 09-25" / "方法切换：otm_estimate → constant_delta"
# ---------------------------------------------------------------------------


def test_expiry_rollover_carries_from_to_expiry_detail() -> None:
    history = [
        _row(timestamp="2026-07-13T08:23", source_expiry="2026-08-28"),
        _row(timestamp="2026-07-14T05:39", source_expiry="2026-09-25"),
    ]

    result = _break_legacy_rolls(history, expiry_mode="fixed")

    detail = result[1].get("series_break_detail")
    assert detail == "expiry_rollover:2026-08-28->2026-09-25", (
        f"unexpected detail string: {detail!r}"
    )


def test_method_change_carries_from_to_method_detail() -> None:
    history = [
        _row(timestamp="2026-07-14T05:39", source_expiry="2026-09-25", method="otm_estimate"),
        _row(
            timestamp="2026-07-14T09:46",
            source_expiry="2026-09-25",
            method="constant_delta",
        ),
    ]

    result = _break_legacy_rolls(history, expiry_mode="constant_maturity")

    detail = result[1].get("series_break_detail")
    assert detail == "method_change:otm_estimate->constant_delta", (
        f"unexpected detail string: {detail!r}"
    )


def test_no_break_means_no_detail_field() -> None:
    history = [
        _row(timestamp="2026-07-13T08:23", source_expiry="2026-08-28"),
        _row(timestamp="2026-07-13T16:00", source_expiry="2026-08-28"),
    ]

    result = _break_legacy_rolls(history, expiry_mode="fixed")

    for point in result:
        assert "series_break_detail" not in point, (
            f"detail leaked into a non-break point: {point}"
        )