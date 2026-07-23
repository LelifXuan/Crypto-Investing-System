"""Tests for gold V3 API endpoints."""
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


def test_gold_v3_allocation_returns_200() -> None:
    """GET /gold/v3/allocation should return 200 with V3 structure."""
    with _client() as client:
        resp = client.get("/api/v1/gold/v3/allocation")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert len(data["signals"]) == 3
    assert "spot" in data
    assert "contract" in data
    assert "spot_summary" in data
    assert "liquidity_shock_detected" in data


def test_gold_v3_allocation_signals_have_expected_keys() -> None:
    """Each signal light should have key, label, bias, bias_reason."""
    with _client() as client:
        resp = client.get("/api/v1/gold/v3/allocation")
    assert resp.status_code == 200
    data = resp.json()
    for signal in data["signals"]:
        assert "key" in signal
        assert "label" in signal
        assert "bias" in signal
        assert "bias_reason" in signal


def test_gold_v3_allocation_spot_has_dca_fields() -> None:
    """Spot DCA should have base_amount, dip_multiplier, recommended_amount."""
    with _client() as client:
        resp = client.get("/api/v1/gold/v3/allocation")
    assert resp.status_code == 200
    data = resp.json()
    spot = data["spot"]
    assert "base_amount" in spot
    assert "dip_multiplier" in spot
    assert "macro_gate_passed" in spot
    assert "recommended_amount" in spot
    assert "indicator_confirmations" in spot
    assert len(spot["indicator_confirmations"]) == 5


def test_gold_derivatives_endpoint() -> None:
    """GET /gold/derivatives should return OI/funding/COT snapshot."""
    with _client() as client:
        resp = client.get("/api/v1/gold/derivatives")
    assert resp.status_code == 200
    data = resp.json()
    assert "oi_change_4w" in data
    assert "funding_rate" in data
    assert "cot_net_spec_percentile" in data
