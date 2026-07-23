from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app
from app.schemas.market import PrecomputeHintResponse


async def _dummy_db_session():
    yield object()


def test_strategy_unified_endpoint_returns_200_when_service_throws(monkeypatch) -> None:
    """Even if UnifiedStrategyService raises, endpoint must return HTTP 200 + degraded payload."""

    async def _raise(self, instrument_id: str = "btc-usdt-perp", *, force: bool = False):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr(
        "app.services.strategy_unified.unified_service.UnifiedStrategyService.build_unified_strategy",
        _raise,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/strategy/unified",
            params={"instrument_id": "btc-usdt-perp", "force": "true"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert "upstream timeout" in str(body.get("degraded_components", []))
    assert body["status"] == "degraded"
    assert body["prewarm_status"] == "idle"
    # Ensure a placeholder unified_state so frontend can render skeleton
    assert body["unified_state"]["code"] == "DATA_DEGRADED"
    assert body["unified_state"]["permission"] in {"observe", "no_trade"}


def test_strategy_prewarm_endpoint_enqueues_hint() -> None:
    """POST /strategy/prewarm enqueues a hint and returns immediately."""
    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with patch(
        "app.api.v1.endpoints.strategy.precompute_service"
    ) as mock_pc, TestClient(app, raise_server_exceptions=False) as client:
        mock_pc.enqueue_hint = AsyncMock(
            return_value=PrecomputeHintResponse(status="accepted", accepted=1, queued=1)
        )
        response = client.post(
            "/api/v1/strategy/prewarm",
            params={"instrument_id": "btc-usdt-perp"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert "eta_seconds" in body

    mock_pc.enqueue_hint.assert_called_once()
    call_arg = mock_pc.enqueue_hint.call_args[0][0]
    assert call_arg.current_page == "strategy"
    assert call_arg.reason == "strategy_cold_start"
    assert "strategy_unified" in call_arg.candidates
    assert "monitoring" in call_arg.candidates
    assert "btc_derivatives" in call_arg.candidates
    assert "macro" in call_arg.candidates
