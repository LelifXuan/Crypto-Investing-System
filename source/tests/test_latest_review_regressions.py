from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.cache.shared_query_cache import shared_query_cache
from app.schemas.market import MacroOverviewIndicatorRead
from app.services.final_decision import FinalDecisionService
from app.services.macro.scoring_engine import MacroScoringEngine
from app.services.strategy_signal.snapshot_builder import (
    StrategySnapshotBuilder,
    _build_structure_score,
    _build_trend_score,
    classify_vwap_cost_channel,
)
from scripts.build_source_handoff import build_source_handoff
from scripts.release_common import scan_secret_like_content


def _macro_item(key: str, value: str | None, *, unit: str = "") -> MacroOverviewIndicatorRead:
    return MacroOverviewIndicatorRead(
        indicator_key=key,
        label=key,
        unit=unit,
        tooltip="test",
        value_num=Decimal(value) if value is not None else None,
        status="live",
        insight="test",
        is_scored=True,
    )


def test_macro_scoring_engine_uses_unit_specific_thresholds() -> None:
    engine = MacroScoringEngine.load_default()

    usd_cny_score = engine.score(_macro_item("usd_cny", "7.10"))
    dxy_score = engine.score(_macro_item("dollar_index", "101"))
    vix_calm = engine.score(_macro_item("vix", "15"))
    vix_stress = engine.score(_macro_item("vix", "35"))
    claims = engine.score(_macro_item("initial_claims", "250000", unit="count"))

    assert 35 <= usd_cny_score.score <= 75
    assert 35 <= dxy_score.score <= 75
    assert vix_calm.score > vix_stress.score
    assert claims.score >= 50
    assert claims.canonical_key == "initial_claims"


def test_macro_scoring_engine_excludes_missing_and_momentum_without_history() -> None:
    engine = MacroScoringEngine.load_default()

    missing = engine.score(_macro_item("us_cpi_yoy", None))
    momentum = engine.score(_macro_item("gold", "2300"))

    assert missing.is_scored is False
    assert missing.score is None
    assert momentum.is_scored is False
    assert momentum.reason == "history_insufficient"


def test_macro_scoring_engine_excludes_unknown_registry_rule() -> None:
    engine = MacroScoringEngine({"indicators": []})

    result = engine.score(_macro_item("unknown_live_numeric", "123"))

    assert result.score is None
    assert result.is_scored is False
    assert result.reason == "registry_rule_missing"


@pytest.mark.asyncio
async def test_final_decision_macro_bridge_uses_macro_overview_fields(monkeypatch) -> None:
    await shared_query_cache.clear()
    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {
            "state": "ready",
            "recommended_action": "breakout_watch",
            "recommended_action_v2": "normal_trade",
            "direction_score": 70.0,
            "direction_label": "strong_long",
            "confidence_score": 80.0,
            "confidence_label": "high",
            "execution_score": 80.0,
            "risk_score": 20.0,
            "conflict_level": 0,
            "risk_gates": [],
            "components": {},
            "explain": [],
        }

    async def fake_build_overview(self):
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "regime_key": "risk_off",
                "operation_bias": "bearish",
                "total_score": 24,
                "confidence": "high",
                "event_window_state": "clear",
                "event_window_status": "清朗",
            }
        )

    monkeypatch.setattr("app.services.final_decision.ChipStructureService.analyze", fake_analyze)
    monkeypatch.setattr(
        "app.services.final_decision.MacroOverviewService.build_overview", fake_build_overview
    )

    payload = await FinalDecisionService(SimpleNamespace()).build("btc-usdt-perp", "4h")

    assert payload["macro_bias"] == "risk_off"
    assert payload["action"] == "observe"
    assert "macro_risk_off_vs_trade_action" in payload["conflicts"]
    assert payload["source"]["macro"]["operation_bias"] == "bearish"


@pytest.mark.asyncio
async def test_final_decision_legacy_chinese_clear_event_is_not_event_wait(monkeypatch) -> None:
    await shared_query_cache.clear()
    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {
            "state": "ready",
            "recommended_action_v2": "observe",
            "direction_score": 0.0,
            "direction_label": "neutral",
            "confidence_score": 50.0,
            "confidence_label": "medium",
            "execution_score": 50.0,
            "risk_score": 30.0,
            "conflict_level": 0,
            "risk_gates": [],
            "components": {},
            "explain": [],
        }

    async def fake_build_overview(self):
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "regime_key": "neutral",
                "operation_bias": "observe",
                "total_score": 50,
                "confidence": "high",
                "event_window_status": "清朗",
            }
        )

    monkeypatch.setattr("app.services.final_decision.ChipStructureService.analyze", fake_analyze)
    monkeypatch.setattr(
        "app.services.final_decision.MacroOverviewService.build_overview", fake_build_overview
    )

    payload = await FinalDecisionService(SimpleNamespace()).build("btc-usdt-perp", "4h")

    assert payload["macro_bias"] == "neutral"
    assert "macro_risk_off_vs_trade_action" not in payload["conflicts"]
    await shared_query_cache.clear()


def test_vwap_cost_channel_filters_trend_without_becoming_trigger() -> None:
    bullish, bearish = _build_trend_score(
        {
            "ema_20": 110,
            "ema_20_prev": 109,
            "ema_50": 105,
            "ema_200": 100,
            "adx_14": 30,
            "close": 112,
            "vwap_short": 108,
            "vwap_long": 103,
            "vwap_slope_short_10": 0.4,
            "vwap_slope_long_10": 0.2,
        }
    )
    neutral_bullish, neutral_bearish = _build_trend_score(
        {
            "ema_20": 110,
            "ema_20_prev": 109,
            "ema_50": 105,
            "ema_200": 100,
            "adx_14": 30,
        }
    )

    assert bullish > neutral_bullish
    assert bearish <= neutral_bearish


def test_vwap_cost_channel_uses_default_one_percent_buffer() -> None:
    weak = classify_vwap_cost_channel(
        {
            "close": 101.002,
            "vwap_short": 100.8,
            "vwap_long": 100.8,
            "vwap_slope_short_10": 0.2,
            "vwap_slope_long_10": 0.2,
        },
        {"price_buffer": 0.01, "spread_buffer": 0.005},
    )
    strong = classify_vwap_cost_channel(
        {
            "close": 103.0,
            "vwap_short": 102.0,
            "vwap_long": 100.0,
            "vwap_slope_short_10": 0.2,
            "vwap_slope_long_10": 0.2,
        },
        {"price_buffer": 0.01, "spread_buffer": 0.005},
    )

    assert weak["vwap_bias"] == "neutral"
    assert weak["vwap_regime"] != "bull_trend"
    assert strong["vwap_bias"] == "bullish"
    assert strong["vwap_regime"] == "bull_trend"


def test_structure_score_handles_overall_and_weak_bias_labels() -> None:
    assert _build_structure_score({"overall_score": 64}) == (64, 36)
    assert _build_structure_score({"score": 42, "overall_bias": "weak_bearish"}) == (42, 58)
    assert _build_structure_score({"overall_bias": "weak_bullish"}) == (60.0, 40.0)
    assert _build_structure_score({"overall_bias": "weak_bearish"}) == (40.0, 60.0)


def test_levels_extract_nested_structure_payload() -> None:
    payload = {
        "snapshot": {
            "geometry": {
                "levels": {
                    "support_price": 98000,
                    "resistance_price": 103000,
                    "structure_invalid_long": 97000,
                }
            },
            "active_items": [{"levels": {"breakout_up": True}}],
            "text_decision": {"levels": {"poc_price": 100500}},
        }
    }

    levels = StrategySnapshotBuilder._levels(payload)

    assert levels["support_price"] == 98000
    assert levels["resistance_price"] == 103000
    assert levels["structure_invalid_long"] == 97000
    assert levels["poc_price"] == 100500
    assert levels["breakout_up"] is True


def test_release_secret_scanner_blocks_non_empty_secret_values(tmp_path: Path) -> None:
    secret_file = tmp_path / ".env"
    secret_file.write_text("JWT_SECRET_KEY=real-secret-value\nEMPTY_SECRET=\n", encoding="utf-8")
    example = tmp_path / ".env.example"
    example.write_text("JWT_SECRET_KEY=\nADMIN_PASSWORD=\n", encoding="utf-8")

    findings = scan_secret_like_content([secret_file, example])

    assert [finding.path.name for finding in findings] == [".env"]
    assert findings[0].key == "JWT_SECRET_KEY"


def test_source_handoff_excludes_secret_and_runtime_residue(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app").mkdir()
    (src / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (src / ".env").write_text("JWT_SECRET_KEY=real-secret\n", encoding="utf-8")
    (src / ".env.example").write_text("JWT_SECRET_KEY=\n", encoding="utf-8")
    (src / "runtime").mkdir()
    (src / "runtime" / "data.db").write_text("db", encoding="utf-8")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "x.pyc").write_bytes(b"pyc")

    out = tmp_path / "handoff.zip"
    report = build_source_handoff(src, out)

    assert out.exists()
    assert ".env" not in report["included_files"]
    assert "runtime/data.db" not in report["included_files"]
    assert "app/main.py" in report["included_files"]
    assert any(item["path"] == ".env" for item in report["blocked_files"])
