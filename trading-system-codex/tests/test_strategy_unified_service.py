# ruff: noqa: E501
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _context(timeframe: str, *, event_status: str = "normal") -> SimpleNamespace:
    return SimpleNamespace(
        instrument_id="btc-usdt-perp",
        timeframe=timeframe,
        market_data={"flow_bias": "neutral", "spot_volume_state": "normal"},
        indicator_features={},
        vwap_features={},
        structure_features={"structure_state": f"{timeframe}-structure"},
        derivatives_features={
            "snapshot_state": "live",
            "funding_state": "neutral",
            "oi_state": "stable",
            "key_levels_axis": {"status": "ready", "summary": "衍生品结构可用"},
        },
        macro_features={"regime_key": "risk_on", "operation_bias": "supportive"},
        event_features={
            "event_window_status": event_status,
            "next_check_time": "2026-07-01T08:00:00+00:00",
            "events": [{"name": "FOMC", "impact": "high"}] if event_status != "normal" else [],
        },
        onchain_features={"bias": "neutral"} if timeframe == "1d" else {},
        execution_features={"execution_score": 70},
        chip_structure={"evidence_quality": "structure_snapshot"},
        macro_overview={"confidence": "high", "operation_bias": "supportive"},
        data_quality={"dependencies": {"chip_structure": {"cache_state": "fresh"}}},
        cache_meta={"cache_state": "fresh", "source_age_seconds": 30},
    )


def _bundle(
    timeframe: str,
    *,
    long_score: float,
    short_score: float,
    confidence: float = 75,
    status: str = "ready",
) -> dict:
    side = "long" if long_score >= short_score else "short"
    return {
        "instrument_id": "btc-usdt-perp",
        "timeframe": timeframe,
        "status": status,
        "cache_state": "fresh" if status == "ready" else status,
        "freshness_state": "fresh",
        "current_price": "61000",
        "decision": {
            "strategy_state": "LONG_BIAS" if side == "long" else "SHORT_BIAS",
            "strategy_bias": side,
            "long_score": long_score,
            "short_score": short_score,
            "neutral_score": max(0, 100 - max(long_score, short_score)),
            "direction_confidence": confidence,
            "confidence_score": confidence,
            "primary_strategy": {
                "direction": side,
                "entry_price": 61000,
                "entry_zone": [60600, 61200],
                "stop_price": 62400 if side == "short" else 59200,
                "take_profit_1": 59000 if side == "short" else 63500,
                "take_profit_2": 57500 if side == "short" else 65000,
                "risk_reward_ratio": 1.8,
                "strategy_logic": f"{timeframe} {side} setup",
                "entry_condition": "等待收盘确认",
                "invalidation_criteria": ["收盘越过结构失效位"],
            },
            "long_plan": {
                "direction": "long",
                "entry_zone": [60600, 61200],
                "stop_price": 59200,
                "take_profit_1": 63500,
                "take_profit_2": 65000,
                "entry_condition": "回踩不破",
            },
            "short_plan": {
                "direction": "short",
                "entry_zone": [60600, 61200],
                "stop_price": 62400,
                "take_profit_1": 59000,
                "take_profit_2": 57500,
                "entry_condition": "反抽失败",
            },
            "explain": [f"{timeframe} 方向由旧策略引擎计算"],
        },
        "snapshot": {},
    }


@pytest.mark.asyncio
async def test_unified_loader_computes_missing_strategy_bundles(monkeypatch) -> None:
    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    computed_timeframes: list[str] = []

    class FakeContextBuilder:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_context(self, instrument_id: str, timeframe: str, *, cache_only: bool = True):
            return _context(timeframe)

    class FakeStrategyService:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_bundle(self, instrument_id: str, timeframe: str, *, enqueue_refresh: bool = True):
            return {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "status": "missing",
                "cache_state": "missing",
                "freshness_state": "missing",
                "decision": {},
            }

        async def build_bundle_uncached(self, instrument_id: str, timeframe: str):
            computed_timeframes.append(timeframe)
            scores = {
                "30d": (68, 38),
                "1w": (66, 42),
                "1d": (37, 72),
                "4h": (35, 70),
                "1h": (45, 62),
                "15m": (48, 56),
            }
            long_score, short_score = scores[timeframe]
            return _bundle(timeframe, long_score=long_score, short_score=short_score)

        async def refresh_bundle(self, instrument_id: str, timeframe: str, *, reason: str = "scheduled"):
            computed_timeframes.append(f"refresh:{timeframe}")
            return await self.build_bundle_uncached(instrument_id, timeframe)

    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.MarketContextBuilder",
        FakeContextBuilder,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.StrategySignalService",
        FakeStrategyService,
    )

    payload = await UnifiedStrategyService(SimpleNamespace()).build_unified_strategy(
        "btc-usdt-perp"
    )

    assert computed_timeframes == ["30d", "1w", "1d", "4h", "1h", "15m"]
    assert payload["refresh_state"] == "computed"
    assert payload["unified_state"]["code"] != "DATA_DEGRADED"
    assert {node["raw_status"]["cache_state"] for node in payload["timeframe_stack"]} == {
        "computed"
    }
    assert all(node["long_score"] or node["short_score"] for node in payload["timeframe_stack"])
    assert any(plan["type"] != "NO_TRADE" for plan in payload["trade_plans"])


@pytest.mark.asyncio
async def test_unified_strategy_uses_market_context_when_legacy_bundle_missing(monkeypatch) -> None:
    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    class FakeContextBuilder:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_context(self, instrument_id: str, timeframe: str, *, cache_only: bool = True):
            context = _context(timeframe)
            context.structure_features.update(
                {
                    "direction": "LONG" if timeframe in {"30d", "1w"} else "SHORT",
                    "long_score": 67 if timeframe in {"30d", "1w"} else 36,
                    "short_score": 39 if timeframe in {"30d", "1w"} else 71,
                    "confidence": 62,
                    "key_support": 58000,
                    "key_resistance": 62500,
                }
            )
            context.indicator_features = {
                "direction": context.structure_features["direction"],
                "long_score": context.structure_features["long_score"],
                "short_score": context.structure_features["short_score"],
            }
            return context

    class FakeStrategyService:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_bundle(self, instrument_id: str, timeframe: str, *, enqueue_refresh: bool = True):
            return {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "status": "missing",
                "cache_state": "missing",
                "freshness_state": "missing",
                "decision": {},
            }

        async def build_bundle_uncached(self, instrument_id: str, timeframe: str):
            raise RuntimeError("legacy strategy unavailable")

    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.MarketContextBuilder",
        FakeContextBuilder,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.StrategySignalService",
        FakeStrategyService,
    )

    payload = await UnifiedStrategyService(SimpleNamespace()).build_unified_strategy(
        "btc-usdt-perp"
    )

    assert payload["unified_state"]["code"] == "STRATEGIC_LONG_TACTICAL_SHORT"
    assert payload["unified_state"]["permission"] != "no_trade"
    assert all(
        "MarketContextBuilder" in node["source_modules"]
        for node in payload["timeframe_stack"]
    )
    assert all(
        node["raw_status"]["cache_state"] == "context_fallback"
        for node in payload["timeframe_stack"]
    )


@pytest.mark.asyncio
async def test_force_unified_strategy_preserves_usable_cache_when_recompute_fails(monkeypatch) -> None:
    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    class FakeContextBuilder:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_context(self, instrument_id: str, timeframe: str, *, cache_only: bool = True):
            return _context(timeframe)

    class FakeStrategyService:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_bundle(self, instrument_id: str, timeframe: str, *, enqueue_refresh: bool = True):
            return _bundle(timeframe, long_score=65, short_score=38)

        async def build_bundle_uncached(self, instrument_id: str, timeframe: str):
            raise RuntimeError("upstream recompute failed")

    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.MarketContextBuilder",
        FakeContextBuilder,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.StrategySignalService",
        FakeStrategyService,
    )

    payload = await UnifiedStrategyService(SimpleNamespace()).build_unified_strategy(
        "btc-usdt-perp",
        force=True,
    )

    assert payload["refresh_state"] == "requested"
    assert payload["unified_state"]["code"] != "DATA_DEGRADED"
    assert all(node["raw_status"]["cache_state"] == "fresh" for node in payload["timeframe_stack"])
    assert all(node["long_score"] == 65 for node in payload["timeframe_stack"])


@pytest.mark.asyncio
async def test_unified_strategy_builds_short_term_short_long_term_long(monkeypatch) -> None:
    from app.services.strategy_unified.unified_service import (
        TIMEFRAME_STACK_LIST,
        UnifiedStrategyService,
    )

    loaded_contexts: list[tuple[str, bool]] = []
    loaded_bundles: list[str] = []

    class FakeContextBuilder:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_context(self, instrument_id: str, timeframe: str, *, cache_only: bool = True):
            loaded_contexts.append((timeframe, cache_only))
            return _context(timeframe)

    class FakeStrategyService:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_bundle(self, instrument_id: str, timeframe: str, *, enqueue_refresh: bool = True):
            loaded_bundles.append(timeframe)
            scores = {
                "30d": (72, 35),
                "1w": (76, 32),
                "1d": (35, 74),
                "4h": (32, 78),
                "1h": (42, 62),
                "15m": (48, 56),
            }
            long_score, short_score = scores[timeframe]
            return _bundle(timeframe, long_score=long_score, short_score=short_score)

    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.MarketContextBuilder",
        FakeContextBuilder,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.StrategySignalService",
        FakeStrategyService,
    )

    payload = await UnifiedStrategyService(SimpleNamespace()).build_unified_strategy(
        "btc-usdt-perp",
        force=True,
    )

    assert loaded_contexts == [
        ("30d", False),
        ("1w", False),
        ("1d", False),
        ("4h", False),
        ("1h", False),
        ("15m", False),
    ]
    assert loaded_bundles == ["30d", "1w", "1d", "4h", "1h", "15m"]
    assert TIMEFRAME_STACK_LIST() == ["1M", "1w", "1d", "4h", "1h", "15m"]
    assert payload["refresh_state"] == "requested"
    assert payload["refresh_limitations"]
    assert payload["snapshot_key"]
    assert payload["payload_hash"]
    assert payload["unified_state"]["code"] == "STRATEGIC_LONG_TACTICAL_SHORT"
    assert payload["unified_state"]["label"] == "短空长多"
    assert payload["unified_state"]["risk_level"] in {"low", "medium", "high"}
    assert payload["unified_state"]["next_check_time"]
    assert payload["horizon_views"]["strategic"]["direction"] == "LONG"
    assert payload["horizon_views"]["tactical"]["direction"] == "SHORT"
    assert payload["horizon_views"]["execution"]["direction"] == "WAIT_SHORT_TRIGGER"
    assert payload["horizon_governance"]["position_cap"] == "reduced"
    assert payload["horizon_governance"]["allowed_sides"] == ["LONG", "SHORT"]
    assert payload["horizon_governance"]["upgrade_path"]
    assert payload["horizon_governance"]["invalidation_path"]
    assert len(payload["timeframe_stack"]) == 6
    assert {item["timeframe"] for item in payload["timeframe_stack"]} == {
        "1M",
        "1w",
        "1d",
        "4h",
        "1h",
        "15m",
    }
    for node in payload["timeframe_stack"]:
        assert node["direction"] == node["bias"]
        assert node["structure_state"] == node["state"]
        assert node["cache_timeframe"]
        assert node["freshness"]
        assert node["source_modules"]
    assert len(payload["trade_plans"]) >= 3
    plan_types = {plan["type"] for plan in payload["trade_plans"]}
    assert {"STRATEGIC_ACCUMULATION", "TACTICAL_SHORT", "EXECUTION_TRIGGER"} <= plan_types
    for plan in payload["trade_plans"]:
        assert plan["type"] == plan["plan_type"]
        assert plan["label"] == plan["title"]
        assert plan["entry_logic"]
        assert "take_profit" in plan
        assert "take_profit_text" in plan
        assert plan["invalidation"]
        assert plan["position_rule"]
    assert {item["conclusion_key"] for item in payload["evidence_trace"]} >= {
        "unified_state.code",
        "horizon_views.strategic.direction",
        "horizon_views.tactical.direction",
        "horizon_views.execution.direction",
        "market_operation.macro_regime.bias",
    }
    for trace in payload["evidence_trace"]:
        assert trace["source_modules"]
        assert "calculation_rule" in trace
        assert "input_features" in trace
        assert "freshness" in trace
    assert payload["narrative"]["headline"]
    assert "1M/1w 看多" in payload["narrative"]["headline"]
    assert "1d/4h 看空" in payload["narrative"]["headline"]
    assert "执行层等待空头触发" in payload["narrative"]["headline"]
    assert {layer["key"] for layer in payload["narrative"]["layers"]} == {
        "strategic",
        "tactical",
        "execution",
    }
    narrative_layers = {layer["key"]: layer for layer in payload["narrative"]["layers"]}
    assert narrative_layers["strategic"]["timeframes"] == ["1M", "1w"]
    assert narrative_layers["strategic"]["direction"] == "LONG"
    assert "1M/1w 综合分数" in narrative_layers["strategic"]["basis"]
    assert "Market context fallback" not in narrative_layers["strategic"]["basis"]
    assert "CONTEXT_" not in narrative_layers["strategic"]["basis"]
    assert narrative_layers["tactical"]["timeframes"] == ["1d", "4h"]
    assert narrative_layers["tactical"]["direction"] == "SHORT"
    assert "1d/4h 综合分数" in narrative_layers["tactical"]["basis"]
    assert narrative_layers["execution"]["direction"] == "WAIT_SHORT_TRIGGER"
    assert "1H" in narrative_layers["execution"]["required_signal"]
    assert "15M" in narrative_layers["execution"]["required_signal"]
    assert payload["narrative"]["watchlist"]
    assert any(item["timeframe"] == "1H" and "触发" in item["indicator"] for item in payload["narrative"]["watchlist"])
    assert payload["narrative"]["action"] != payload["unified_state"]["instruction"]
    assert list(payload["market_operation"]["chain"].keys()) == [
        "macro_regime",
        "capital_flow",
        "derivatives_regime",
        "onchain_regime",
        "price_structure",
    ]


@pytest.mark.asyncio
async def test_unified_strategy_marks_data_degraded_when_core_cycles_missing(monkeypatch) -> None:
    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    class FakeContextBuilder:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_context(self, instrument_id: str, timeframe: str, *, cache_only: bool = True):
            context = _context(timeframe)
            context.indicator_features = {}
            context.structure_features = {}
            context.macro_features = {}
            context.execution_features = {}
            return context

    class FakeStrategyService:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_bundle(self, instrument_id: str, timeframe: str, *, enqueue_refresh: bool = True):
            if timeframe in {"30d", "1w", "1d"}:
                return {"status": "missing", "cache_state": "missing", "decision": {}}
            return _bundle(timeframe, long_score=45, short_score=45, status="ready")

    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.MarketContextBuilder",
        FakeContextBuilder,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.StrategySignalService",
        FakeStrategyService,
    )

    payload = await UnifiedStrategyService(SimpleNamespace()).build_unified_strategy(
        "btc-usdt-perp"
    )

    assert payload["unified_state"]["code"] == "DATA_DEGRADED"
    assert payload["unified_state"]["permission"] == "no_trade"
    assert any(
        item["category"] == "data"
        and item["label"]
        and item["action"]
        and item["affected_horizons"]
        for item in payload["risk_alerts"]
    )


@pytest.mark.asyncio
async def test_unified_strategy_event_lock_becomes_first_class_risk(monkeypatch) -> None:
    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    class FakeContextBuilder:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_context(self, instrument_id: str, timeframe: str, *, cache_only: bool = True):
            return _context(timeframe, event_status="event_locked")

    class FakeStrategyService:
        def __init__(self, repository) -> None:  # noqa: ANN001
            self.repository = repository

        async def get_bundle(self, instrument_id: str, timeframe: str, *, enqueue_refresh: bool = True):
            return _bundle(timeframe, long_score=70, short_score=30)

    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.MarketContextBuilder",
        FakeContextBuilder,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.data_loader.StrategySignalService",
        FakeStrategyService,
    )

    payload = await UnifiedStrategyService(SimpleNamespace()).build_unified_strategy(
        "btc-usdt-perp"
    )

    assert payload["unified_state"]["code"] == "EVENT_LOCKED"
    assert payload["unified_state"]["permission"] == "no_trade"
    assert payload["event_watch"]
    assert any(item["category"] == "event" for item in payload["risk_alerts"])


@pytest.mark.asyncio
async def test_build_unified_marks_degraded_when_engine_fails(repository) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    service = UnifiedStrategyService(repository)
    valid_bundle = {"decision": {"direction_confidence": 50}, "status": "ready", "cache_state": "ready"}
    valid_context = {
        "timeframe": "1d",
        "market_data": {},
        "structure_features": {},
        "indicator_features": {},
        "execution_features": {},
        "macro_features": {},
        "cache_meta": {"cache_state": "fresh"},
    }
    mock_loaded = {
        "contexts": {
            "1M": valid_context,
            "1w": valid_context,
            "1d": valid_context,
            "4h": valid_context,
            "1h": valid_context,
            "15m": valid_context,
        },
        "bundles": {
            "1M": valid_bundle,
            "1w": valid_bundle,
            "1d": valid_bundle,
            "4h": valid_bundle,
            "1h": valid_bundle,
            "15m": valid_bundle,
        },
        "refresh_state": "cache_only",
        "refresh_limitations": [],
    }
    with patch.object(service.loader, "load", new=AsyncMock(return_value=mock_loaded)), \
         patch.object(
             service.macro_engine,
             "compute",
             new=MagicMock(side_effect=RuntimeError("macro engine crashed")),
         ):
        payload = await service.build_unified_strategy("btc-usdt-perp")

    assert payload["degraded"] is True
    assert "macro_regime" in payload["degraded_components"]
    assert payload["status"] == "degraded"
    assert "horizon_views" in payload
    assert "timeframe_stack" in payload

    # Verify per-dimension fallback uses correct label (regression for shared fallback bug)
    assert payload["market_operation"]["chain"]["macro_regime"]["label"] == "宏观"
    assert payload["market_operation"]["chain"]["macro_regime"]["key"] == "macro_regime"
