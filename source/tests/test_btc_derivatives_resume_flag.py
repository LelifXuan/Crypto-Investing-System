"""2026-07-25: pin the contract that the per-instrument price history
merger emits `*_resumed_after_gap` flags on the first non-null row
after a ≥3-day null run, and that the leverage_pressure_timeline
chart builder attaches a '数据接续' vertical-line annotation when any
field hits the threshold."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# 1. _merge_price_history flags resume rows
# ---------------------------------------------------------------------------

def _resolve_price_history_callable():
    """Build a LiveCollector instance with a no-op cache so we can call
    `_merge_price_history(fresh_history)` directly. The cache stub
    returns an empty list so the cache-side merge contributes nothing
    and we exercise only the fresh-history resume-flag branch."""
    from app.services.btc_derivatives.sources.collector import (
        LiveCollector,
    )

    class _StubCache:
        def read_history(self):
            return []

    collector = LiveCollector.__new__(LiveCollector)
    collector.cache = _StubCache()
    return collector._merge_price_history


def test_merge_price_history_flags_oi_resume_after_three_null_days() -> None:
    merge = _resolve_price_history_callable()
    history = [
        {"timestamp": "2026-06-19", "aggregate_oi_usd": 1000.0},
        {"timestamp": "2026-06-20", "aggregate_oi_usd": None},
        {"timestamp": "2026-06-21", "aggregate_oi_usd": None},
        {"timestamp": "2026-06-22", "aggregate_oi_usd": None},
        {"timestamp": "2026-06-23", "aggregate_oi_usd": None},
        # ↑ 4 consecutive null days.
        {"timestamp": "2026-06-24", "aggregate_oi_usd": 6300000000.0},
        {"timestamp": "2026-06-25", "aggregate_oi_usd": 6310000000.0},
    ]
    merged = merge(history)
    by_day = {row["timestamp"]: row for row in merged}
    assert "aggregate_oi_usd_resumed_after_gap" not in by_day["2026-06-19"], (
        "the resume flag must NOT be set on the very first non-null row"
    )
    assert "aggregate_oi_usd_resumed_after_gap" not in by_day["2026-06-20"], (
        "null rows must NOT carry the resume flag"
    )
    assert by_day["2026-06-24"].get("aggregate_oi_usd_resumed_after_gap") is True, (
        "the FIRST non-null row after a ≥3-day null gap must carry the resume flag"
    )
    assert "aggregate_oi_usd_resumed_after_gap" not in by_day["2026-06-25"], (
        "subsequent valid points must not carry the flag repeatedly"
    )


def test_merge_price_history_does_not_flag_short_gaps() -> None:
    merge = _resolve_price_history_callable()
    history = [
        {"timestamp": "2026-06-19", "aggregate_oi_usd": 1000.0},
        {"timestamp": "2026-06-20", "aggregate_oi_usd": None},
        {"timestamp": "2026-06-21", "aggregate_oi_usd": 1200.0},
        {"timestamp": "2026-06-22", "aggregate_oi_usd": None},
        {"timestamp": "2026-06-23", "aggregate_oi_usd": 1500.0},
    ]
    merged = merge(history)
    for row in merged:
        assert "aggregate_oi_usd_resumed_after_gap" not in row, (
            "a 1- or 2-day null gap must NOT trip the resume flag (threshold is 3)"
        )


# ---------------------------------------------------------------------------
# 2. Chart builder turns the flag into a vertical-line annotation
# ---------------------------------------------------------------------------

def test_leverage_pressure_timeline_attaches_resume_annotation() -> None:
    from app.services.btc_derivatives.chart_builder import (
        build_consolidated_dashboard_charts,
    )

    price_history = [
        {"timestamp": "2026-06-19", "spot_price": 65000.0, "aggregate_oi_usd": 6.1e9, "funding_zscore": 0.1},
        {"timestamp": "2026-06-20", "spot_price": None, "aggregate_oi_usd": None, "funding_zscore": None},
        {"timestamp": "2026-06-21", "spot_price": None, "aggregate_oi_usd": None, "funding_zscore": None},
        {"timestamp": "2026-06-22", "spot_price": None, "aggregate_oi_usd": None, "funding_zscore": None},
        {"timestamp": "2026-06-23", "spot_price": 64500.0, "aggregate_oi_usd": 6.3e9, "funding_zscore": 0.2,
         "aggregate_oi_usd_resumed_after_gap": True},
    ]
    result = build_consolidated_dashboard_charts(
        price_history=price_history,
        futures_rows=[],
        basis_points=[],
        atm_iv_points=[],
        strike_rows=[],
        history=[],
        spot_price=64500.0,
        call_wall=None,
        put_wall=None,
        max_pain=None,
    )
    chart = result["charts"]["leverage_pressure_timeline"]
    annotations = chart.get("annotations") or []
    resume_markers = [
        note for note in annotations
        if note.get("label") == "数据接续"
    ]
    assert len(resume_markers) == 1, (
        f"expected exactly one resume marker, got {len(resume_markers)}: {resume_markers!r}"
    )
    assert resume_markers[0]["x"] == "2026-06-23", (
        "the marker x must equal the resume timestamp"
    )


def test_leverage_pressure_timeline_no_annotation_when_no_resume() -> None:
    from app.services.btc_derivatives.chart_builder import (
        build_consolidated_dashboard_charts,
    )

    price_history = [
        {"timestamp": f"2026-06-{d}", "spot_price": 65000.0 + d, "aggregate_oi_usd": 6.1e9 + d, "funding_zscore": 0.1}
        for d in range(15, 25)
    ]
    result = build_consolidated_dashboard_charts(
        price_history=price_history,
        futures_rows=[],
        basis_points=[],
        atm_iv_points=[],
        strike_rows=[],
        history=[],
        spot_price=65000.0,
        call_wall=None,
        put_wall=None,
        max_pain=None,
    )
    chart = result["charts"]["leverage_pressure_timeline"]
    annotations = chart.get("annotations") or []
    resume_markers = [
        note for note in annotations
        if note.get("label") == "数据接续"
    ]
    assert resume_markers == [], (
        "no resume markers should be emitted when all rows are non-null"
    )
