from __future__ import annotations

from datetime import date

from app.services.btc_derivatives.constant_maturity import (
    annotate_constant_maturity_history,
    select_constant_maturity_expiry,
)
from app.services.btc_derivatives.time_window_policy import (
    TIME_WINDOW_POLICY,
    filter_history_window,
    resolve_window,
)


def test_time_window_policy_uses_independent_defaults_and_caps_overrides() -> None:
    assert TIME_WINDOW_POLICY["leverage_pressure"].default == "90D"
    assert TIME_WINDOW_POLICY["funding"].maximum == "365D"
    assert TIME_WINDOW_POLICY["wall_max_pain"].default == "180D"
    assert TIME_WINDOW_POLICY["hedge_cost"].default == "180D"
    assert TIME_WINDOW_POLICY["options_chain"].is_cross_section is True

    assert resolve_window("leverage_pressure", None) == "90D"
    assert resolve_window("wall_max_pain", None) == "180D"
    assert resolve_window("perp_oi", "365D") == "180D"
    assert resolve_window("options_chain", "90D") == "current"


def test_filter_history_window_changes_time_series_but_not_cross_sections() -> None:
    history = [
        {"timestamp": f"2026-06-{day:02d}", "value": day}
        for day in range(1, 31)
    ]

    assert len(filter_history_window(history, "7D", as_of=date(2026, 6, 30))) == 7
    assert len(filter_history_window(history, "30D", as_of=date(2026, 6, 30))) == 30


def test_constant_maturity_selects_nearest_future_expiry() -> None:
    selected = select_constant_maturity_expiry(
        ["2026-06-20", "2026-07-31", "2026-09-25"],
        as_of=date(2026, 6, 24),
        maturity_bucket="60D",
    )

    assert selected["expiry"] == "2026-07-31"
    assert selected["dte"] == 37
    assert selected["target_dte"] == 60
    assert selected["status"] == "ok"


def test_constant_maturity_history_marks_rollover_without_smoothing() -> None:
    rows = [
        {"timestamp": "2026-06-01", "source_expiry": "2026-07-31", "spot_price": 58_000},
        {"timestamp": "2026-06-15", "source_expiry": "2026-07-31", "spot_price": 60_000},
        {"timestamp": "2026-07-15", "source_expiry": "2026-09-25", "spot_price": 62_000},
    ]

    output = annotate_constant_maturity_history(rows, maturity_bucket="60D")

    assert [item["rollover"] for item in output] == [False, False, True]
    assert output[-1]["source_expiry"] == "2026-09-25"
    assert output[-1]["spot_price"] == 62_000


def test_constant_maturity_returns_data_insufficient_without_future_expiry() -> None:
    selected = select_constant_maturity_expiry(
        ["2026-05-30", "invalid"],
        as_of=date(2026, 6, 24),
        maturity_bucket="60D",
    )

    assert selected["expiry"] is None
    assert selected["status"] == "data_insufficient"
