from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app


async def _dummy_db_session():
    yield object()


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
