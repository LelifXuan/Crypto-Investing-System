from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app
from app.services.ashare_etf_rebalance import (
    ETFPosition,
    PlanMode,
    RebalanceConfig,
    normalize_etf_symbol,
    optimize_etf_rebalance,
)


async def _dummy_db_session():
    yield None


def _client() -> TestClient:
    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    return TestClient(app)


def _positions() -> list[ETFPosition]:
    return [
        ETFPosition("563010.SH", 3000, 1.08, 1.12),
        ETFPosition("512660.SH", 2500, 0.95, 0.89),
        ETFPosition("516950.SH", 2800, 1.02, 0.98),
        ETFPosition("512400.SH", 5200, 1.05, 1.24),
        ETFPosition("159930.SZ", 4200, 1.16, 1.21),
        ETFPosition("561560.SH", 2200, 1.10, 1.06),
    ]


def _payload() -> dict:
    return {
        "mode": "monthly_dca",
        "cash_to_invest": 5000,
        "positions": [
            {
                "symbol": item.symbol,
                "shares": item.shares,
                "cost_price": item.cost_price,
                "current_price": item.current_price,
            }
            for item in _positions()
        ],
    }


def test_monthly_dca_is_buy_only_and_lot_sized() -> None:
    result = optimize_etf_rebalance(
        _positions(),
        RebalanceConfig(mode=PlanMode.MONTHLY_DCA, cash_to_invest=5000),
    )

    assert result["orders"]
    assert {order["side"] for order in result["orders"]} == {"BUY"}
    assert all(order["shares"] % 100 == 0 for order in result["orders"])
    assert all("用本次可投现金补足低配标的" not in order["reason"] for order in result["orders"])
    assert result["portfolio"]["trade_count"] == len(result["orders"])
    assert result["portfolio"]["turnover_amount"] > 0
    assert "target_cash_weight" in result["cash"]


def test_large_cash_uses_batch_candidates_instead_of_one_lot_only() -> None:
    result = optimize_etf_rebalance(
        _positions(),
        RebalanceConfig(mode=PlanMode.MONTHLY_DCA, cash_to_invest=100_000),
    )

    buy_orders = [order for order in result["orders"] if order["side"] == "BUY"]
    assert buy_orders
    assert any(order["shares"] >= 1000 for order in buy_orders)
    assert result["portfolio"]["trade_count"] == len(result["orders"])


def test_quarterly_rebalance_can_sell_profitable_overweight_etf() -> None:
    result = optimize_etf_rebalance(
        _positions(),
        RebalanceConfig(mode=PlanMode.QUARTERLY_REBALANCE, cash_to_invest=5000),
    )

    sells = [order for order in result["orders"] if order["side"] == "SELL"]
    assert sells
    assert any(order["symbol"] == "512400.SH" for order in sells)
    assert all(order["shares"] % 100 == 0 for order in result["orders"])
    assert (
        result["deviation_summary"]["after_total_abs_deviation"]
        < result["deviation_summary"]["before_total_abs_deviation"]
    )


def test_losing_overweight_inside_hard_band_is_not_forced_sell() -> None:
    positions = [
        ETFPosition("563010.SH", 1300, 1.30, 1.00),
        ETFPosition("512660.SH", 1000, 1.00, 1.00),
        ETFPosition("516950.SH", 1000, 1.00, 1.00),
        ETFPosition("512400.SH", 1000, 1.00, 1.00),
        ETFPosition("159930.SZ", 1000, 1.00, 1.00),
        ETFPosition("561560.SH", 1000, 1.00, 1.00),
    ]
    result = optimize_etf_rebalance(
        positions,
        RebalanceConfig(
            mode=PlanMode.QUARTERLY_REBALANCE,
            cash_to_invest=0,
            tolerance_pct=0.02,
            hard_tolerance_pct=0.05,
        ),
    )

    assert not any(
        order["side"] == "SELL" and order["symbol"] == "563010.SH"
        for order in result["orders"]
    )
    row = next(item for item in result["rows"] if item["symbol"] == "563010.SH")
    assert "不强制卖出" in row["explanation"]


def test_min_fee_is_included_in_order_amount_and_cash_left() -> None:
    result = optimize_etf_rebalance(
        _positions(),
        RebalanceConfig(
            mode=PlanMode.MONTHLY_DCA,
            cash_to_invest=5000,
            fee_rate=0,
            min_fee=5,
        ),
    )

    assert result["orders"]
    assert all(order["fee_estimate"] == 5 for order in result["orders"])
    assert all(
        order["estimated_amount"] == round(order["shares"] * order["price"] + 5, 2)
        for order in result["orders"]
    )
    assert result["cash"]["cash_left"] == round(
        5000 - sum(order["estimated_amount"] for order in result["orders"]),
        2,
    )


def test_invalid_universe_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported_etf"):
        normalize_etf_symbol("000001.SH")


def test_rebalance_api_accepts_full_payload() -> None:
    with _client() as client:
        response = client.post("/api/v1/ashare-etf/rebalance/plan", json=_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "monthly_dca"
    assert "rows" in data
    assert "target_weights" in data
    assert "portfolio" in data
    assert "target_cash_weight" in data["cash"]


def test_rebalance_api_rejects_negative_shares() -> None:
    payload = _payload()
    payload["positions"][0]["shares"] = -1

    with _client() as client:
        response = client.post("/api/v1/etf/rebalance/plan", json=payload)

    assert response.status_code == 422


def test_rebalance_api_accepts_min_fee_and_returns_portfolio() -> None:
    payload = _payload()
    payload["min_fee"] = 5

    with _client() as client:
        response = client.post("/api/v1/etf/rebalance/plan", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["execution_constraints"]["min_fee"] == 5
    assert data["portfolio"]["trade_count"] == len(data["orders"])
