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


def _payload(**overrides) -> dict:
    payload = {
        "symbol": "XAUT_USDT",
        "daily_dca_amount": 100,
        "dip_add_amount": 500,
        "cooldown_days": 7,
        "quote_max_age_seconds": 900,
        "available_cash": 2000,
        "executed_today": False,
        "quote": {"price": 4400, "updated_at": "2026-06-08T12:00:00+00:00"},
        "now": "2026-06-08T12:05:00+00:00",
        "indicators": {
            "close": 4200,
            "rsi_14": 28,
            "percent_b": -0.05,
            "cci_20": -160,
            "return_7d": -0.04,
            "drawdown_from_30d_high": -0.07,
            "close_vs_ema20_pct": -0.03,
        },
    }
    payload.update(overrides)
    return payload


def test_gold_execution_plan_endpoint_returns_v3_contract() -> None:
    with _client() as client:
        response = client.post("/api/v1/gold/execution-plan", json=_payload())

    assert response.status_code == 200
    data = response.json()
    for key in {"symbol", "as_of", "quote", "daily_dca", "dip_add", "execution", "diagnostics"}:
        assert key in data
    assert data["daily_dca"]["status"] == "execute"
    assert data["dip_add"]["status"] == "triggered"
    assert data["execution"]["action"] == "daily_dca_plus_dip_add"
    assert data["execution"]["total_amount"] == 600


def test_gold_execution_plan_keeps_daily_dca_when_indicators_missing() -> None:
    payload = _payload(indicators=None)
    with _client() as client:
        response = client.post("/api/v1/gold/execution-plan", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["daily_dca"]["status"] == "execute"
    assert data["dip_add"]["status"] == "insufficient_data"
    assert data["execution"]["action"] == "daily_dca_only"


def test_gold_execution_plan_stale_quote_returns_manual_check() -> None:
    payload = _payload(quote={"price": 4400, "updated_at": "2026-06-08T10:00:00+00:00"})
    with _client() as client:
        response = client.post("/api/v1/gold/execution-plan", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["execution"]["action"] == "manual_check"
    assert data["execution"]["total_amount"] == 0


def test_existing_gold_allocation_endpoints_remain_available() -> None:
    with _client() as client:
        allocation = client.get("/api/v1/gold/allocation")
        market = client.get("/api/v1/gold/market-state")

    assert allocation.status_code == 200
    assert market.status_code == 200
