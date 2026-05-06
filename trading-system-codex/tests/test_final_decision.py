from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.final_decision import FinalDecisionService


@pytest.mark.asyncio
async def test_final_decision_exposes_confidence_engine_fields(monkeypatch) -> None:
    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {
            "state": "ready",
            "primary_regime": "bullish_continuation_range",
            "evidence_quality": "confirmed",
            "recommended_action": "breakout_watch",
            "recommended_action_v2": "normal_trade",
            "direction_score": 72.0,
            "direction_label": "strong_long",
            "confidence_score": 81.0,
            "confidence_label": "high",
            "execution_score": 74.0,
            "execution_label": "good",
            "risk_score": 24.0,
            "risk_label": "normal",
            "confidence_cap": 100.0,
            "position_multiplier": 0.35,
            "capital_ceiling_pct": 20.0,
            "conflict_level": 0,
            "risk_gates": [],
            "components": {"data_quality_score": {"raw": 0.9, "weighted": 0.216}},
            "explain": ["confidence is backed by strong alignment"],
        }

    async def fake_build_overview(self):
        return SimpleNamespace(
            model_dump=lambda mode="json": {"status": "normal", "risk_level": "neutral"}
        )

    monkeypatch.setattr(
        "app.services.final_decision.ChipStructureService.analyze",
        fake_analyze,
    )
    monkeypatch.setattr(
        "app.services.final_decision.MacroOverviewService.build_overview",
        fake_build_overview,
    )

    payload = await FinalDecisionService(SimpleNamespace()).build("btc-usdt-perp", "4h")

    assert payload["direction"] == "long_preferred"
    assert payload["recommended_action"] == "normal_trade"
    assert payload["confidence_label"] == "high"
    assert payload["components"]["data_quality_score"]["weighted"] == 0.216
    assert payload["legacy_recommended_action"] == "breakout_watch"
