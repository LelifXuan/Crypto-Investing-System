from __future__ import annotations

from app.schemas.btc_derivatives import ChartDataset
from app.services.btc_derivatives.chart_builder import (
    build_consolidated_dashboard_charts,
)
from tests.test_btc_derivatives_chart_consolidation import _inputs


def test_chart_dataset_accepts_style_contract() -> None:
    dataset = ChartDataset(
        label="Max Pain",
        data=[60_000],
        style={"borderDash": [2, 5], "borderWidth": 1.5, "opacity": 0.55},
    )

    assert dataset.style["borderDash"] == [2, 5]
    assert dataset.style["opacity"] == 0.55


def test_option_chart_series_emit_visually_distinct_styles() -> None:
    charts = build_consolidated_dashboard_charts(**_inputs())["charts"]
    levels = {
        item["label"]: item["style"]
        for item in charts["key_levels_history"]["datasets"]
    }
    risk = {
        item["label"]: item["style"]
        for item in charts["options_risk_premium_history"]["datasets"]
    }

    assert levels["Spot"]["borderWidth"] > levels["Max Pain"]["borderWidth"]
    assert levels["Call Wall"]["borderDash"] != levels["Put Wall"]["borderDash"]
    assert levels["Max Pain"]["opacity"] < 1
    assert risk["25D Skew"]["borderDash"] == []
    assert risk["Put/Call OI"]["borderDash"]
    assert risk["Call 保护成本"]["opacity"] < 1


def test_hedge_cost_axis_shows_percent_ticks() -> None:
    charts = build_consolidated_dashboard_charts(**_inputs())["charts"]
    y_cost = charts["options_risk_premium_history"]["axes"]["y_cost"]

    assert y_cost["display_ticks"] is True
    assert y_cost["profile"] == "percent"
    assert y_cost["unit"] == "percent"
