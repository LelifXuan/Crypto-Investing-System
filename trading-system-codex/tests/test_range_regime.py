from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.analysis_bundle import _compute_payload_mode
from app.services.btc_derivatives.market_state_engine import build_market_state
from app.services.range_regime import classify_range, classify_swing_range
from app.services.strategy_unified.contracts import TIMEFRAME_SPECS
from app.services.strategy_unified.mtf_structure import MultiTimeframeStructureEngine


def candle(high: float, low: float, close: float):
    return SimpleNamespace(high=high, low=low, close=close)


def pivot(kind: str, price: float):
    return SimpleNamespace(kind=kind, price=price)


@pytest.mark.parametrize(
    ("gap", "expected"),
    [(5, "UPWARD_RANGE"), (-5, "DOWNWARD_RANGE"), (4.99, "NEUTRAL_RANGE")],
)
def test_score_gap_boundaries(gap: float, expected: str) -> None:
    result = classify_range(regime="range", long_score=50 + gap, short_score=50)
    assert result.range_state == expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [(55, "UPWARD_RANGE"), (45, "DOWNWARD_RANGE"), (50, "NEUTRAL_RANGE")],
)
def test_composite_score_boundaries(score: float, expected: str) -> None:
    result = classify_range(regime="balanced", composite_score=score)
    assert result.range_state == expected


def test_swing_highs_and_lows_must_move_together_beyond_atr_threshold() -> None:
    candles = [candle(11, 9, 10), candle(11, 9, 10)] * 8
    upward = classify_swing_range(
        regime="balance",
        pivots=[pivot("high", 10), pivot("low", 8), pivot("high", 11), pivot("low", 9)],
        candles=candles,
        structure_score=0.08,
    )
    mixed = classify_swing_range(
        regime="balance",
        pivots=[pivot("high", 10), pivot("low", 8), pivot("high", 11), pivot("low", 7)],
        candles=candles,
        structure_score=0.08,
    )
    boundary = classify_swing_range(
        regime="balance",
        pivots=[pivot("high", 10), pivot("low", 8), pivot("high", 10.3), pivot("low", 8.3)],
        candles=candles,
        structure_score=0.08,
    )
    assert upward.range_state == "UPWARD_RANGE"
    assert mixed.range_state == "NEUTRAL_RANGE"
    assert boundary.range_state == "NEUTRAL_RANGE"


def test_structure_and_confirmation_conflict_downgrades_to_neutral() -> None:
    result = classify_range(
        regime="compression",
        structure_direction="UP",
        structure_score=-0.08,
    )
    assert result.range_state == "NEUTRAL_RANGE"
    assert result.range_conflicts


@pytest.mark.parametrize("regime", ["transition", "trend", "missing"])
def test_non_range_regimes_do_not_fall_back_to_neutral(regime: str) -> None:
    assert classify_range(regime=regime, composite_score=50).range_state == "NONE"


@pytest.mark.parametrize("status", ["missing", "stale", "data_insufficient"])
def test_bad_data_never_becomes_neutral_range(status: str) -> None:
    result = classify_range(regime="range", composite_score=50, data_status=status)
    assert result.range_state == "NONE"


def test_analysis_bundle_exposes_shared_range_contract() -> None:
    mode, asset_class, result = _compute_payload_mode(
        {
            "instrument_id": "btc-usdt-perp",
            "timeframe": "4h",
            "final_decision": {
                "direction_score": 8,
                "components": {"structure_overall": {"regime": "balance"}},
            },
        }
    )
    assert (mode, asset_class) == ("range", "crypto")
    assert result.range_state == "UPWARD_RANGE"


def test_derivatives_range_uses_price_positioning_not_single_risk_indicator() -> None:
    common = {
        "iv_state": "iv_neutral",
        "skew_state": "skew_neutral",
        "wall_movement": {"call_wall": "stable", "put_wall": "stable"},
        "max_pain_movement": "stable",
        "data_quality_status": "live",
    }
    upward = build_market_state(
        price_oi_state="price_up_oi_up",
        funding_state="normal",
        **common,
    )
    funding_only = build_market_state(
        price_oi_state="flat",
        funding_state="positive_hot",
        **common,
    )
    assert upward["range_state"] == "UPWARD_RANGE"
    assert funding_only["range_state"] == "NEUTRAL_RANGE"


def test_strategy_timeframe_node_carries_range_contract() -> None:
    spec = next(item for item in TIMEFRAME_SPECS if item.logical == "1h")
    node = MultiTimeframeStructureEngine()._node(
        spec,
        {"structure_features": {"structure_state": "NO_EDGE"}},
        {
            "decision": {
                "strategy_state": "NO_EDGE",
                "long_score": 56,
                "short_score": 50,
                "neutral_score": 50,
            },
            "freshness_state": "fresh",
        },
    )
    assert node.range_state == "UPWARD_RANGE"
    assert node.timeframe_state == "UPWARD_RANGE"
    assert node.range_label == "上行震荡"
