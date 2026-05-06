from __future__ import annotations

from app.models.confidence import ConfidenceEngineInput, StructureConfidenceInput
from app.services.confidence_engine import ConfidenceEngine


def _payload(**overrides) -> ConfidenceEngineInput:
    data = {
        "instrument_id": "btc-usdt-perp",
        "timeframe": "4h",
        "data_quality_status": "good",
        "data_quality_score": 92.0,
        "missing_inputs": [],
        "evidence_quality": "confirmed",
        "conflict_level": 0,
        "state": "ready",
        "direction_score": 78.0,
        "timeframe_biases": {"1w": "bullish", "1d": "bullish", "4h": "bullish", "1h": "bullish"},
        "primary_regime": "bullish_continuation_range",
        "h4_adx": 29.0,
        "h4_bb_width": 0.06,
        "h1_bb_width": 0.05,
        "h4_obv_slope": 0.14,
        "h1_obv_slope": 0.09,
        "funding_rate": 0.001,
        "funding_zscore": 0.6,
        "basis_rate": 0.001,
        "basis_zscore": 0.4,
        "cvd_delta": 3200.0,
        "open_interest_notional": 800000.0,
        "depth_liquidity": 900000.0,
        "spread_bps": 6.0,
        "slippage_bps": 4.0,
        "execution_readiness": "confirmed",
        "structure": StructureConfidenceInput(
            available=True,
            overall_score=0.62,
            overall_confidence=0.84,
            overall_bias="bullish",
            conflict_state=False,
            evidence_density=0.9,
            direction_agreement=1.0,
            top_reasons=["swing and profile align bullish"],
        ),
    }
    data.update(overrides)
    return ConfidenceEngineInput(**data)


def test_confidence_engine_returns_execution_ready_trade() -> None:
    report = ConfidenceEngine().evaluate(_payload())

    assert report.direction_label == "strong_long"
    assert report.confidence_score >= 75
    assert report.execution_score >= 70
    assert report.recommended_action in {"normal_trade", "add_on_confirmation"}
    assert report.position_multiplier >= 0.35
    assert report.confidence_cap == 100


def test_confidence_engine_caps_when_microstructure_missing() -> None:
    report = ConfidenceEngine().evaluate(
        _payload(
            evidence_quality="proxy_only",
            cvd_delta=None,
            open_interest_notional=None,
            depth_liquidity=None,
            spread_bps=None,
            slippage_bps=None,
            missing_inputs=[
                "cvd missing",
                "open_interest missing",
                "depth missing",
                "slippage missing",
            ],
        )
    )

    assert report.confidence_cap <= 60
    assert report.confidence_score <= 60
    assert report.confidence_label in {"watch_only", "usable", "high", "low"}


def test_confidence_engine_blocks_poor_execution() -> None:
    report = ConfidenceEngine().evaluate(
        _payload(
            depth_liquidity=90000.0,
            spread_bps=28.0,
            slippage_bps=42.0,
            execution_readiness="blocked",
        )
    )

    assert report.execution_label == "blocked"
    assert "SLIPPAGE_HARD_LIMIT" in report.risk_gates
    assert report.recommended_action == "no_trade"
    assert report.position_multiplier == 0
