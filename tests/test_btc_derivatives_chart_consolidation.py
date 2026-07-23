from __future__ import annotations

from app.schemas.btc_derivatives import BtcDerivativesDashboardResponse
from app.services.btc_derivatives.chart_builder import (
    REQUIRED_CHART_IDS,
    build_consolidated_dashboard_charts,
)


def _inputs() -> dict:
    history = [
        {
            "timestamp": "2026-06-01",
            "spot_price": 58_000,
            "call_wall_strike": 60_000,
            "put_wall_strike": 45_000,
            "max_pain_strike": 55_000,
            "skew_25d": -0.02,
            "put_call_oi_ratio": 0.96,
            "put_call_volume_ratio": 1.02,
            "call_protection_cost_pct": 0.021,
            "put_protection_cost_pct": 0.023,
            "debit_spread_cost_pct": 0.013,
            "source_expiry": "2026-07-31",
            "source_dte": 60,
            "maturity_bucket": "60D",
            "rollover": False,
        }
    ]
    return {
        "price_history": [
            {
                "timestamp": "2026-06-01",
                "spot_price": 58_000,
                "aggregate_oi_usd": 13.1e9,
                "funding_zscore": -0.2,
            }
        ],
        "futures_rows": [
            {
                "exchange": "Deribit",
                "open_interest_usd": 4.8e9,
                "oi_change_pct": 0.09,
                "funding_rate": 0.00018,
                "basis_pct": 0.012,
            }
        ],
        "basis_points": [
            {
                "expiry": "2026-07-31",
                "basis_pct": 0.012,
                "annualized_basis_pct": 0.121,
            }
        ],
        "atm_iv_points": [{"expiry": "2026-07-31", "atm_iv": 0.66}],
        "strike_rows": [
            {
                "strike": 60_000,
                "call_oi": 2_300,
                "put_oi": 1_000,
                "call_iv": 0.60,
                "put_iv": 0.61,
            }
        ],
        "history": history,
        "spot_price": 58_000,
        "call_wall": 60_000,
        "put_wall": 45_000,
        "max_pain": 55_000,
    }


def test_consolidated_dashboard_contains_only_six_decision_charts() -> None:
    result = build_consolidated_dashboard_charts(**_inputs())

    assert set(result["charts"]) == REQUIRED_CHART_IDS == {
        "leverage_pressure_timeline",
        "exchange_crowding_snapshot",
        "term_structure",
        "strike_surface",
        "key_levels_history",
        "options_risk_premium_history",
    }
    assert not {
        "walls_history",
        "max_pain_history",
        "iv_smile",
        "oi_by_strike",
    } & set(result["charts"])


def test_merged_charts_keep_key_levels_and_strike_surface_series() -> None:
    charts = build_consolidated_dashboard_charts(**_inputs())["charts"]

    assert [item["label"] for item in charts["key_levels_history"]["datasets"]] == [
        "Spot",
        "Call Wall",
        "Put Wall",
        "Max Pain",
    ]
    assert [item["label"] for item in charts["strike_surface"]["datasets"]] == [
        "Call OI",
        "Put OI",
        "Call IV",
        "Put IV",
    ]
    assert {item["label"] for item in charts["strike_surface"]["annotations"]} == {
        "Spot",
        "Call Wall",
        "Put Wall",
        "Max Pain",
    }


def test_leverage_timeline_contains_one_funding_z_series() -> None:
    chart = build_consolidated_dashboard_charts(**_inputs())["charts"][
        "leverage_pressure_timeline"
    ]

    funding_series = [item for item in chart["datasets"] if item["label"] == "Funding Z"]
    assert len(funding_series) == 1
    assert funding_series[0]["data"] == [-0.2]


def test_dashboard_schema_accepts_axes_layout_and_selection_metadata() -> None:
    result = build_consolidated_dashboard_charts(**_inputs())
    payload = {
        "generated_at": "2026-06-24T00:00:00Z",
        "underlying": "BTC",
        "cards": [],
        "futures": {"rows": [], "metrics": {}, "charts": result["charts"]},
        "options": {
            "selected_expiry": "2026-07-31",
            "expiries": ["2026-07-31"],
            "chain": [],
            "metrics": {},
            "walls": {},
            "max_pain": {},
            "charts": {},
        },
        "chart_layout": result["chart_layout"],
        "selection": {
            "expiry_mode": "constant_maturity",
            "maturity_bucket": "60D",
            "selected_expiry": "2026-07-31",
            "window": None,
            "strike_range_pct": "30",
        },
        "maturity_selection": {
            "expiry": "2026-07-31",
            "dte": 37,
            "target_dte": 60,
            "status": "ok",
        },
        "joint_analysis": {},
        "hedge_context": {},
        "data_quality": {},
    }

    validated = BtcDerivativesDashboardResponse.model_validate(payload)

    assert validated.chart_layout.cards["strike_surface"].span == 12
    assert (
        validated.chart_layout.cards["term_structure"].span
        + validated.chart_layout.cards["exchange_crowding_snapshot"].span
        == 12
    )
    assert (
        validated.chart_layout.cards["key_levels_history"].span
        + validated.chart_layout.cards["options_risk_premium_history"].span
        == 12
    )
    assert validated.futures.charts["leverage_pressure_timeline"].axes["y_price"].profile == "price"
    assert validated.selection.expiry_mode == "constant_maturity"


def test_futures_layout_prioritizes_crowding_chart_width() -> None:
    three_exchanges = _inputs()
    three_exchanges["futures_rows"] = [
        {**three_exchanges["futures_rows"][0], "exchange": exchange}
        for exchange in ("Deribit", "Binance", "OKX")
    ]
    three = build_consolidated_dashboard_charts(**three_exchanges)["chart_layout"]["cards"]
    assert three["exchange_crowding_snapshot"]["span"] == 8
    assert three["term_structure"]["span"] == 4

    four_exchanges = _inputs()
    four_exchanges["futures_rows"] = [
        {**four_exchanges["futures_rows"][0], "exchange": exchange}
        for exchange in ("Deribit", "Binance", "OKX", "Bybit")
    ]
    four = build_consolidated_dashboard_charts(**four_exchanges)["chart_layout"]["cards"]
    assert four["exchange_crowding_snapshot"]["span"] == 12
    assert four["term_structure"]["span"] == 12


def test_term_structure_keeps_basis_curves_when_futures_basis_is_available() -> None:
    charts = build_consolidated_dashboard_charts(**_inputs())["charts"]
    term = charts["term_structure"]
    datasets = {item["label"]: item["data"] for item in term["datasets"]}

    assert term["labels"] == ["2026-07-31"]
    assert datasets["年化 Basis"] == [0.121]
    assert datasets["Basis"] == [0.012]
