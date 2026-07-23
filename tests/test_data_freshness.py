from __future__ import annotations

from datetime import datetime, timezone

from app.services.data_freshness import bar_close_freshness, expected_closed_bar_ts


def test_4h_returns_due_after_new_closed_bar() -> None:
    now = datetime(2026, 7, 1, 8, 10, tzinfo=timezone.utc)

    state = bar_close_freshness(
        "4h",
        "2026-07-01T00:00:00+00:00",
        now=now,
        grace_seconds=60,
    )

    assert state.freshness_state == "due"
    assert state.expected_closed_bar_ts == datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
    assert state.refresh_reason == "new_closed_bar_available"


def test_1d_returns_due_after_new_utc_daily_close() -> None:
    now = datetime(2026, 7, 1, 0, 5, tzinfo=timezone.utc)

    state = bar_close_freshness(
        "1d",
        "2026-06-29T00:00:00+00:00",
        now=now,
        grace_seconds=60,
    )

    assert state.freshness_state == "due"
    assert state.expected_closed_bar_ts == datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)


def test_grace_period_keeps_previous_bar_expected() -> None:
    now = datetime(2026, 7, 1, 8, 0, 30, tzinfo=timezone.utc)

    expected = expected_closed_bar_ts("4h", now=now, grace_seconds=90)

    assert expected == datetime(2026, 7, 1, 4, 0, tzinfo=timezone.utc)


def test_missing_cached_bar_is_missing_not_due() -> None:
    state = bar_close_freshness(
        "1h",
        None,
        now=datetime(2026, 7, 1, 10, 10, tzinfo=timezone.utc),
    )

    assert state.freshness_state == "missing"
    assert state.refresh_reason == "missing_cached_bar"


def test_monthly_alias_uses_month_boundary() -> None:
    state = bar_close_freshness(
        "1M",
        "2026-06-01T00:00:00+00:00",
        now=datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc),
    )

    assert state.freshness_state == "due"
    assert state.expected_closed_bar_ts == datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
