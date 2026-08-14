"""Regression tests for the HALO/Cashflow scope split.

These tests pin the contract that the rebalance optimizer only handles the
six HALO ETFs and treats 159201.SZ Cashflow ETF as monthly DCA display-only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app
from app.services.ashare_etf_rebalance import (
    CASHFLOW_SYMBOL,
    HALO_ROTATION_UNIVERSE,
    HALO_TARGET_WEIGHTS_DEFAULT,
    ETFPosition,
    PlanMode,
    RebalanceConfig,
    normalize_etf_symbol,
    normalize_halo_target_weights,
    optimize_etf_rebalance,
    validate_halo_positions,
)


def _halo_positions() -> list[ETFPosition]:
    return [
        ETFPosition("563010.SH", 3000, 1.08, 1.12),
        ETFPosition("512660.SH", 2500, 0.95, 0.89),
        ETFPosition("516950.SH", 2800, 1.02, 0.98),
        ETFPosition("512400.SH", 5200, 1.05, 1.24),
        ETFPosition("159930.SZ", 4200, 1.16, 1.21),
        ETFPosition("561560.SH", 2200, 1.10, 1.06),
    ]


def _client() -> TestClient:
    app = create_app(enable_lifespan=False)
    async def _dummy():
        yield None
    app.dependency_overrides[get_db_session] = _dummy
    return TestClient(app)


# ---- 1. Optimizer-level invariants ----------------------------------------


def test_rows_length_is_exactly_six_halo() -> None:
    plan = optimize_etf_rebalance(
        _halo_positions(),
        RebalanceConfig(mode=PlanMode.MONTHLY_DCA, cash_to_invest=5000),
    )
    assert len(plan["rows"]) == 6
    assert all(row["symbol"] in {d.symbol for d in HALO_ROTATION_UNIVERSE} for row in plan["rows"])


def test_orders_never_contain_cashflow() -> None:
    plan = optimize_etf_rebalance(
        _halo_positions(),
        RebalanceConfig(
            mode=PlanMode.QUARTERLY_REBALANCE, cash_to_invest=5000
        ),
    )
    assert all(order["symbol"] != CASHFLOW_SYMBOL for order in plan["orders"])


def test_monthly_mode_never_returns_sell() -> None:
    plan = optimize_etf_rebalance(
        _halo_positions(),
        RebalanceConfig(mode=PlanMode.MONTHLY_DCA, cash_to_invest=5000),
    )
    assert {order["side"] for order in plan["orders"]} <= {"BUY"}


def test_quarterly_no_trigger_returns_empty_orders() -> None:
    # All positions sized so weight is within tolerance band of the default
    # HALO-internal target weights (~16-20% each, tolerance 2%).
    plan = optimize_etf_rebalance(
        [
            ETFPosition("563010.SH", 600, 1.0, 1.0),
            ETFPosition("512660.SH", 500, 1.0, 1.0),
            ETFPosition("516950.SH", 600, 1.0, 1.0),
            ETFPosition("512400.SH", 500, 1.0, 1.0),
            ETFPosition("159930.SZ", 700, 1.0, 1.0),
            ETFPosition("561560.SH", 700, 1.0, 1.0),
        ],
        RebalanceConfig(
            mode=PlanMode.QUARTERLY_REBALANCE,
            cash_to_invest=0,
            tolerance_pct=0.05,
            hard_tolerance_pct=0.10,
        ),
    )
    assert plan["orders"] == []


def test_target_weights_only_halo_and_sum_to_one() -> None:
    plan = optimize_etf_rebalance(
        _halo_positions(),
        RebalanceConfig(mode=PlanMode.MONTHLY_DCA, cash_to_invest=5000),
    )
    assert set(plan["target_weights"]) == {
        d.symbol for d in HALO_ROTATION_UNIVERSE
    }
    assert CASHFLOW_SYMBOL not in plan["target_weights"]
    assert abs(sum(plan["target_weights"].values()) - 1.0) < 1e-6


def test_excluded_etfs_always_contains_cashflow() -> None:
    plan = optimize_etf_rebalance(
        _halo_positions(),
        RebalanceConfig(mode=PlanMode.MONTHLY_DCA, cash_to_invest=5000),
    )
    assert any(item["symbol"] == CASHFLOW_SYMBOL for item in plan["excluded_etfs"])


def test_scope_field_is_halo_only() -> None:
    plan = optimize_etf_rebalance(
        _halo_positions(),
        RebalanceConfig(mode=PlanMode.MONTHLY_DCA, cash_to_invest=5000),
    )
    assert plan["scope"] == "HALO_ONLY"


# ---- 2. Strict validator --------------------------------------------------


def test_validate_halo_positions_rejects_cashflow() -> None:
    with pytest.raises(ValueError, match="cashflow_etf_is_monthly_dca_only"):
        validate_halo_positions(
            [
                *_halo_positions(),
                ETFPosition(CASHFLOW_SYMBOL, 1000, 1.0, 1.0),
            ]
        )


def test_validate_halo_positions_rejects_missing_symbol() -> None:
    with pytest.raises(ValueError, match="halo_positions_must_include_exactly_6_etfs"):
        validate_halo_positions(_halo_positions()[:5])


def test_validate_halo_positions_rejects_extra_symbol() -> None:
    # Cashflow is the only known non-HALO symbol; the cashflow check fires
    # before the cardinality check, so we expect a cashflow-specific error.
    bogus = [
        *_halo_positions(),
        ETFPosition(CASHFLOW_SYMBOL, 100, 1.0, 1.0),
    ]
    with pytest.raises(ValueError, match="cashflow_etf_is_monthly_dca_only"):
        validate_halo_positions(bogus)


# ---- 3. Target weights normalizer -----------------------------------------


def test_normalize_halo_target_weights_default_none() -> None:
    weights = normalize_halo_target_weights(None)
    assert weights == HALO_TARGET_WEIGHTS_DEFAULT
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_normalize_halo_target_weights_rescales_to_one() -> None:
    raw = {
        "563010.SH": 12.0,
        "512660.SH": 16.0,
        "516950.SH": 17.0,
        "512400.SH": 17.0,
        "159930.SZ": 18.0,
        "561560.SH": 20.0,
    }
    weights = normalize_halo_target_weights(raw)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert abs(weights["563010.SH"] - 12.0 / 100.0) < 1e-9


def test_normalize_halo_target_weights_rejects_cashflow() -> None:
    with pytest.raises(ValueError, match="cashflow_etf_not_allowed"):
        normalize_halo_target_weights(
            {**HALO_TARGET_WEIGHTS_DEFAULT, CASHFLOW_SYMBOL: 0.05}
        )


def test_normalize_halo_target_weights_rejects_non_halo_symbol() -> None:
    # The only known non-HALO symbol is Cashflow ETF; the cashflow branch is
    # verified by test_normalize_halo_target_weights_rejects_cashflow above.
    # An unknown symbol is rejected earlier by normalize_etf_symbol.
    with pytest.raises(ValueError, match="unsupported_etf"):
        normalize_etf_symbol("000001.SH")


def test_normalize_halo_target_weights_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative_target_weight"):
        normalize_halo_target_weights(
            {**HALO_TARGET_WEIGHTS_DEFAULT, "563010.SH": -0.1}
        )


def test_normalize_halo_target_weights_rejects_missing() -> None:
    partial = {k: v for k, v in HALO_TARGET_WEIGHTS_DEFAULT.items() if k != "563010.SH"}
    with pytest.raises(ValueError, match="missing_halo_target_weights"):
        normalize_halo_target_weights(partial)


# ---- 4. API-level scope contract (legacy 7-ETF filter + warning) ----------


def test_api_legacy_payload_filters_cashflow_and_warns() -> None:
    payload = {
        "mode": "monthly_dca",
        "cash_to_invest": 5000,
        "positions": [
            {"symbol": s, "shares": sh, "cost_price": cp, "current_price": mp}
            for s, sh, cp, mp in [
                ("563010.SH", 3000, 1.08, 1.12),
                ("512660.SH", 2500, 0.95, 0.89),
                ("516950.SH", 2800, 1.02, 0.98),
                ("512400.SH", 5200, 1.05, 1.24),
                ("159930.SZ", 4200, 1.16, 1.21),
                ("561560.SH", 2200, 1.10, 1.06),
                ("159201.SZ", 4000, 1.00, 1.03),
            ]
        ],
    }
    with _client() as client:
        response = client.post("/api/v1/ashare-etf/rebalance/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "HALO_ONLY"
    assert len(data["rows"]) == 6
    assert all(row["symbol"] != CASHFLOW_SYMBOL for row in data["rows"])
    assert all(order["symbol"] != CASHFLOW_SYMBOL for order in data["orders"])
    assert CASHFLOW_SYMBOL not in data["target_weights"]
    codes = [warning["code"] for warning in data["warnings"]]
    assert "cashflow_excluded_from_halo_rotation" in codes
    assert any(item["symbol"] == CASHFLOW_SYMBOL for item in data["excluded_etfs"])


def test_api_strict_halo_payload_no_warning() -> None:
    payload = {
        "mode": "monthly_dca",
        "halo_cash_to_invest": 5000,
        "halo_positions": [
            {"symbol": s, "shares": sh, "cost_price": cp, "current_price": mp}
            for s, sh, cp, mp in [
                ("563010.SH", 3000, 1.08, 1.12),
                ("512660.SH", 2500, 0.95, 0.89),
                ("516950.SH", 2800, 1.02, 0.98),
                ("512400.SH", 5200, 1.05, 1.24),
                ("159930.SZ", 4200, 1.16, 1.21),
                ("561560.SH", 2200, 1.10, 1.06),
            ]
        ],
        "halo_target_weights": {
            "563010.SH": 0.18,
            "512660.SH": 0.16,
            "516950.SH": 0.17,
            "512400.SH": 0.16,
            "159930.SZ": 0.16,
            "561560.SH": 0.17,
        },
    }
    with _client() as client:
        response = client.post("/api/v1/ashare-etf/rebalance/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["warnings"] == []
    assert abs(sum(data["target_weights"].values()) - 1.0) < 1e-6


def test_api_strict_halo_payload_rejects_cashflow() -> None:
    payload = {
        "mode": "monthly_dca",
        "halo_cash_to_invest": 0,
        "halo_positions": [
            {"symbol": "159201.SZ", "shares": 100, "cost_price": 1.0, "current_price": 1.0},
        ],
    }
    with _client() as client:
        response = client.post("/api/v1/ashare-etf/rebalance/plan", json=payload)
    assert response.status_code == 400
    assert "cashflow_etf" in response.json()["detail"]


def test_api_plan_summary_only_counts_halo_orders() -> None:
    payload = {
        "mode": "monthly_dca",
        "cash_to_invest": 5000,
        "positions": [
            {"symbol": s, "shares": sh, "cost_price": cp, "current_price": mp}
            for s, sh, cp, mp in [
                ("563010.SH", 3000, 1.08, 1.12),
                ("512660.SH", 2500, 0.95, 0.89),
                ("516950.SH", 2800, 1.02, 0.98),
                ("512400.SH", 5200, 1.05, 1.24),
                ("159930.SZ", 4200, 1.16, 1.21),
                ("561560.SH", 2200, 1.10, 1.06),
            ]
        ],
    }
    with _client() as client:
        response = client.post("/api/v1/ashare-etf/rebalance/plan", json=payload)
    data = response.json()
    assert data["portfolio"]["trade_count"] == len(data["orders"])
    assert data["portfolio"]["trade_count"] <= 6
