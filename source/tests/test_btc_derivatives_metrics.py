from __future__ import annotations

from app.schemas.btc_derivatives import BtcDerivativesDashboardResponse
from app.services.btc_derivatives.futures_metrics import (
    aggregate_oi_change_pct,
    aggregate_open_interest,
    price_oi_regime,
)
from app.services.btc_derivatives.models import FuturesSnapshot


def test_dashboard_schema_accepts_empty_chart_first_contract() -> None:
    payload = {
        "generated_at": "2026-06-24T00:00:00Z",
        "underlying": "BTC",
        "cards": [],
        "futures": {"rows": [], "metrics": {}, "charts": {}},
        "options": {
            "selected_expiry": None,
            "expiries": [],
            "chain": [],
            "metrics": {},
            "walls": {},
            "max_pain": {},
            "charts": {},
        },
        "joint_analysis": {},
        "hedge_context": {},
        "data_quality": {"status": "data_insufficient", "warnings": []},
    }

    result = BtcDerivativesDashboardResponse.model_validate(payload)

    assert result.underlying == "BTC"
    assert result.options.chain == []


def test_futures_aggregate_and_regime_metrics_are_deterministic() -> None:
    rows = [
        FuturesSnapshot(
            exchange="Deribit",
            instrument="BTC-PERPETUAL",
            timestamp="2026-06-24T00:00:00Z",
            open_interest_usd=600,
            open_interest_usd_prev=500,
        ),
        FuturesSnapshot(
            exchange="Binance",
            instrument="BTCUSDT",
            timestamp="2026-06-24T00:00:00Z",
            open_interest_usd=500,
            open_interest_usd_prev=500,
        ),
    ]

    assert aggregate_open_interest(rows) == 1100
    assert aggregate_oi_change_pct(rows) == 0.1
    assert price_oi_regime(0.03, 0.1)["state"] == "price_up_oi_up"
    assert price_oi_regime(-0.03, -0.1)["state"] == "price_down_oi_down"
    assert price_oi_regime(None, 0.1)["state"] == "data_insufficient"
