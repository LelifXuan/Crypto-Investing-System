from __future__ import annotations

from app.services.btc_derivatives.chart_builder import (
    REQUIRED_CHART_IDS,
    build_dashboard_charts,
)
from app.services.btc_derivatives.market_state_engine import build_market_state
from app.services.btc_derivatives.wall_tracker import movement_label


def test_wall_tracker_labels_up_down_stable_and_missing() -> None:
    assert movement_label(60_000, 65_000) == "rising"
    assert movement_label(60_000, 55_000) == "falling"
    assert movement_label(60_000, 60_000) == "stable"
    assert movement_label(None, 60_000) == "data_insufficient"


def test_chart_builder_always_returns_all_chart_contracts() -> None:
    charts = build_dashboard_charts(
        price_history=[],
        futures_rows=[],
        basis_points=[],
        atm_iv_points=[],
        iv_smile_points=[],
        skew_history=[],
        strike_rows=[],
        wall_history=[],
        max_pain_history=[],
        hedge_cost_history=[],
    )

    assert set(charts) == REQUIRED_CHART_IDS
    assert all(chart["status"] == "data_insufficient" for chart in charts.values())


def test_upside_squeeze_state_exposes_long_short_evidence_without_trade_command() -> None:
    result = build_market_state(
        price_oi_state="price_up_oi_up",
        funding_state="positive_hot",
        iv_state="iv_neutral",
        skew_state="call_skew_high",
        wall_movement={"call_wall": "rising", "put_wall": "stable"},
        max_pain_movement="rising",
        data_quality_status="partial",
    )

    assert result["market_state"] == "upside_squeeze_risk"
    assert "price_up_oi_up" in result["helps_long"]
    assert "funding_overheated" in result["hurts_long"]
    assert "call_skew_high" in result["hurts_short"]
    assert result["bias_effect"]["short"] == "raises_squeeze_risk"
    assert "buy" not in result["direct_command"].lower()


def test_downside_stress_and_deleveraging_are_distinct_states() -> None:
    stress = build_market_state(
        price_oi_state="price_down_oi_up",
        funding_state="neutral",
        iv_state="iv_high",
        skew_state="put_skew_high",
        wall_movement={"call_wall": "stable", "put_wall": "falling"},
        max_pain_movement="falling",
        data_quality_status="ok",
    )
    deleveraging = build_market_state(
        price_oi_state="price_down_oi_down",
        funding_state="neutral",
        iv_state="iv_neutral",
        skew_state="skew_neutral",
        wall_movement={"call_wall": "stable", "put_wall": "stable"},
        max_pain_movement="stable",
        data_quality_status="ok",
    )

    assert stress["market_state"] == "downside_stress"
    assert "put_skew_high" in stress["hurts_long"]
    assert deleveraging["market_state"] == "deleveraging"
    assert "late_short_risk" in deleveraging["hurts_short"]
