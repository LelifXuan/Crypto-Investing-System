from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app


async def _dummy_db_session():
    yield object()


def test_market_context_snapshot_endpoint_returns_stable_shape(monkeypatch) -> None:
    async def fake_context(self, instrument_id: str, timeframe: str, *, cache_only: bool = True):
        assert cache_only is True
        return SimpleNamespace(
            instrument_id=instrument_id,
            timeframe=timeframe,
            market_data={"mark_price": 61000},
            indicator_features={"rsi_14": 52},
            vwap_features={},
            structure_features={"overall_bias": "bullish"},
            derivatives_features={"key_levels_axis": {"status": "ready"}},
            macro_features={"regime_key": "risk_on"},
            event_features={"event_window_status": "normal"},
            onchain_features={},
            execution_features={"execution_score": 70},
            chip_structure={"confidence_score": 68},
            macro_overview={"confidence": "high"},
            data_quality={"dependencies": {"analysis": {"cache_state": "fresh"}}},
            cache_meta={
                "source": "market_context_builder",
                "cache_state": "fresh",
                "freshness_state": "fresh",
                "source_age_seconds": 12,
                "sources": ["analysis", "structure"],
            },
        )

    monkeypatch.setattr(
        "app.services.market_context.MarketContextBuilder.get_context",
        fake_context,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/market-context/snapshot",
            params={"instrument_id": "btc-usdt-perp", "timeframe": "1M"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["instrument_id"] == "btc-usdt-perp"
    assert payload["timeframe"] == "30d"
    assert payload["cache_meta"]["cache_state"] == "fresh"
    assert set(payload) >= {
        "market_data",
        "indicator_features",
        "vwap_features",
        "structure_features",
        "derivatives_features",
        "macro_features",
        "event_features",
        "onchain_features",
        "execution_features",
        "data_quality",
        "cache_meta",
    }
