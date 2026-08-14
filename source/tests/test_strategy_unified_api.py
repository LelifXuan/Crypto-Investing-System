from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app
from app.schemas.market import PrecomputeHintResponse


async def _dummy_db_session():
    yield object()


@pytest.mark.asyncio
async def test_cached_strategy_fails_closed_when_live_price_unavailable(monkeypatch) -> None:
    from app.api.v1.endpoints.strategy import _guard_cached_strategy

    async def unavailable(self, instrument_id: str, prefer_live: bool = True):  # noqa: ARG001
        raise RuntimeError("price feed down")

    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy.MarketService.get_best_mark", unavailable
    )
    payload, invalidated = await _guard_cached_strategy(
        object(),
        "btc-usdt-perp",
        {
            "unified_state": {"permission": "conditional"},
            "trade_decision": {
                "side": "SHORT",
                "permission": "conditional",
                "order_type": "CONDITIONAL_LIMIT",
            },
        },
    )

    assert invalidated is False
    assert payload["trade_decision"]["status"] == "PRICE_UNAVAILABLE"
    assert payload["trade_decision"]["permission"] == "no_trade"
    assert payload["trade_decision"]["levels_active"] is False
    assert payload["recompute_status"] == "enqueued"


@pytest.mark.asyncio
async def test_cached_strategy_rejects_stale_mark_before_level_reconciliation(monkeypatch) -> None:
    from app.api.v1.endpoints.strategy import _guard_cached_strategy

    async def stale(self, instrument_id: str, prefer_live: bool = True):  # noqa: ARG001
        return SimpleNamespace(
            mark_price=Decimal("66382"),
            source="test",
            ts_event=datetime.now(UTC) - timedelta(seconds=61),
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy.MarketService.get_best_mark", stale
    )
    payload, invalidated = await _guard_cached_strategy(
        object(),
        "btc-usdt-perp",
        {
            "unified_state": {"permission": "conditional"},
            "trade_decision": {
                "side": "SHORT",
                "invalidation": 65_861.23,
                "lifecycle_state": "SETUP_DETECTED",
            },
        },
    )

    assert invalidated is False
    assert payload["trade_decision"]["status"] == "PRICE_STALE"
    assert payload["trade_decision"]["lifecycle_state"] == "SETUP_DETECTED"


def test_strategy_unified_endpoint_returns_unified_payload(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    async def fake_build(self, instrument_id: str = "btc-usdt-perp", *, force: bool = False):
        calls.append((instrument_id, force))
        return {
            "instrument_id": instrument_id,
            "generated_at": "2026-07-01T00:00:00+00:00",
            "status": "ready",
            "refresh_state": "requested",
            "refresh_limitations": ["底层缓存仍可能返回 partial_ready"],
            "snapshot_key": "btc-usdt-perp:abc",
            "payload_hash": "abc",
            "unified_state": {
                "code": "STRATEGIC_LONG_TACTICAL_SHORT",
                "label": "短空长多",
                "instruction": "战略方向看多，战术方向看空。",
                "permission": "conditional",
                "risk_level": "medium",
                "current_price": 61000,
                "primary_symbol": "BTC",
                "next_check_time": "2026-07-01T08:00:00+00:00",
            },
            "horizon_views": {},
            "horizon_governance": {"position_cap": "reduced"},
            "market_operation": {"chain": {}},
            "timeframe_stack": [],
            "trade_plans": [],
            "risk_alerts": [
                {
                    "category": "data",
                    "severity": "warning",
                    "label": "部分周期数据缺失",
                    "message": "部分周期策略缓存缺失。",
                    "action": "等待刷新。",
                    "affected_horizons": ["tactical"],
                    "source_module": "UnifiedDataLoader",
                }
            ],
            "monitoring_focus": [],
            "event_watch": [],
            "evidence_trace": [
                {
                    "conclusion_key": "unified_state.code",
                    "source_modules": ["CrossHorizonSynthesisEngine"],
                    "source_timeframes": ["1d"],
                    "calculation_rule": "strategic_direction + tactical_direction",
                    "input_features": ["horizon_views"],
                    "confidence": 70,
                    "freshness": "mixed",
                }
            ],
            "narrative": {
                "headline": "短空长多: 1M/1w 看多，1d/4h 看空，执行层等待空头触发。",
                "layers": [
                    {
                        "key": "strategic",
                        "label": "战略层",
                        "timeframes": ["1M", "1w"],
                        "direction": "LONG",
                        "basis": "1M/1w 综合分数偏多",
                        "required_signal": "不直接触发短线入场",
                    }
                ],
                "watchlist": [
                    {
                        "timeframe": "1H",
                        "indicator": "触发信号",
                        "condition": "反抽失败 / 跌破确认",
                    }
                ],
                "action": "等待 1H/15M 触发确认。",
            },
        }

    monkeypatch.setattr(
        "app.services.strategy_unified.unified_service.UnifiedStrategyService.build_unified_strategy",
        fake_build,
    )

    async def no_cached_snapshot(self, cache_key: str):  # noqa: ARG001
        return None

    async def fake_upsert_snapshot(self, **kwargs):  # noqa: ARG001
        return object()

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        no_cached_snapshot,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fake_upsert_snapshot,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/strategy/unified",
            params={"instrument_id": "btc-usdt-perp", "force": "true"},
        )
        legacy_response = client.get(
            "/api/v1/strategy/bundle",
            params={"instrument_id": "btc-usdt-perp", "timeframe": "1d"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh_state"] == "requested"
    assert payload["horizon_governance"]["position_cap"] == "reduced"
    assert payload["risk_alerts"][0]["label"]
    assert payload["risk_alerts"][0]["action"]
    assert payload["evidence_trace"][0]["conclusion_key"] == "unified_state.code"
    assert payload["unified_state"]["code"] == "STRATEGIC_LONG_TACTICAL_SHORT"
    assert payload["unified_state"]["label"] == "短空长多"
    assert payload["narrative"]["layers"][0]["key"] == "strategic"
    assert payload["narrative"]["watchlist"][0]["timeframe"] == "1H"
    assert calls == [("btc-usdt-perp", True)]
    assert legacy_response.status_code in {200, 500}


def test_strategy_unified_cold_read_returns_shell_without_build(monkeypatch) -> None:
    async def no_cached_snapshot(self, cache_key: str):  # noqa: ARG001
        return None

    async def fail_upsert_snapshot(self, **kwargs):  # noqa: ARG001
        raise AssertionError("cold read should not write a unified snapshot")

    async def fail_build(self, instrument_id: str = "btc-usdt-perp", *, force: bool = False):
        raise AssertionError("cold read should not synchronously build unified strategy")

    async def fake_enqueue(payload):  # noqa: ANN001
        return PrecomputeHintResponse(status="accepted", accepted=1, queued=1)

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        no_cached_snapshot,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fail_upsert_snapshot,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.unified_service.UnifiedStrategyService.build_unified_strategy",
        fail_build,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy.precompute_service.enqueue_hint",
        fake_enqueue,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/strategy/unified",
            params={"instrument_id": "btc-usdt-perp"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["prewarm_status"] == "enqueued"
    assert payload["refresh_state"] == "missing"
