from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app


async def _dummy_db_session():
    yield None


def _client() -> TestClient:
    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    return TestClient(app)


def _payload() -> dict:
    return {
        "portfolio": {
            "total_portfolio_value": 200000,
            "current_gold_value": 8000,
            "monthly_new_cash": 10000,
            "current_gold_cost": 7600,
            "is_quarterly_rebalance_month": False,
            "crypto_weight": 0.20,
            "halo_etf_weight": 0.25,
            "cashflow_etf_weight": 0.20,
        },
        "options": {
            "base_currency": "元",
            "max_monthly_gold_cash_fraction": 0.6,
            "prefer_staged_execution": True,
        },
        "market": {"xaut_symbol": "XAUT_USDT", "price": 4400, "ret_7d": -0.02},
        "macro": {"real_yield_10y_delta_4w": -0.002, "dxy_change_4w": -0.01},
        "goldhub": {},
    }


def test_gold_plan_endpoint_returns_v2_contract() -> None:
    with _client() as client:
        response = client.post("/api/v1/gold/allocation/plan", json=_payload())

    assert response.status_code == 200
    data = response.json()
    for key in {
        "allocation_state",
        "allocation_score",
        "target_range",
        "current_weight",
        "gap_to_target_min",
        "gap_above_target_max",
        "suggested_this_month",
        "execution_style",
        "primary_instruction",
        "decision_summary",
        "reasoning_steps",
        "module_cards",
        "data_quality",
        "warnings",
    }:
        assert key in data
    assert data["primary_instruction"]
    assert data["decision_summary"]
    assert data["module_cards"]


def test_gold_plan_endpoint_keeps_legacy_payload_compatible() -> None:
    payload = _payload()
    payload["portfolio"]["total_value"] = payload["portfolio"].pop("total_portfolio_value")

    with _client() as client:
        response = client.post("/api/v1/gold/allocation/plan", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "target_weight_min" in data
    assert "gap_to_min_amount" in data
    assert data["target_range"]["min"] == data["target_weight_min"]


def test_gold_plan_endpoint_rejects_invalid_total_value() -> None:
    payload = _payload()
    payload["portfolio"]["total_portfolio_value"] = 0

    with _client() as client:
        response = client.post("/api/v1/gold/allocation/plan", json=payload)

    assert response.status_code in {400, 422}


def test_gold_get_endpoints_return_v2_degraded_payload_without_files() -> None:
    with _client() as client:
        allocation = client.get("/api/v1/gold/allocation")
        fundamentals = client.get("/api/v1/gold/fundamentals")
        market = client.get("/api/v1/gold/market-state")

    assert allocation.status_code == 200
    assert fundamentals.status_code == 200
    assert market.status_code == 200
    data = allocation.json()
    assert data["primary_instruction"]
    assert data["decision_summary"]
    assert data["data_quality"]["uses_xaut_as_proxy"] is True
    assert "missing_categories" in fundamentals.json()["data_quality"]
    assert market.json()["xaut_symbol"] == "XAUT_USDT"
