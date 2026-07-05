from __future__ import annotations

import json
from pathlib import Path

from app.services.strategy_signal.scoring_engine import DirectionScoringEngine
from app.services.strategy_signal.strategy_generator import StrategyGenerator

ROOT = Path(__file__).resolve().parents[1]


def test_direction_penalty_uses_opposite_divergence_not_cvd_or_oi() -> None:
    snapshot = {
        "funding_crowding_score": 0,
        "oi_price_divergence_score": 100,
        "cvd_divergence_score": 100,
        "opposite_divergence_risk_score": 80,
        "late_entry_risk_score": 0,
        "event_risk_score": 0,
    }

    assert DirectionScoringEngine._long_penalty(snapshot) == 12.0
    assert DirectionScoringEngine._short_penalty(snapshot) == 12.0


def test_strategy_config_has_no_microstructure_weights() -> None:
    config = json.loads(
        (ROOT / "app/monitoring/configs/market_strategy_signal_config_v17.json").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(config, ensure_ascii=False)

    forbidden = [
        "derivatives_data_availability",
        "orderbook_data_availability",
        "bullish_flow",
        "bearish_flow",
        "derivatives_long_confirmation",
        "derivatives_short_confirmation",
    ]
    for key in forbidden:
        assert key not in serialized
    assert "technical_risk_availability" in config["data_quality_weights"]
    # V1.7.4: range_structure replaces divergence_support_* in long_weights / short_weights
    assert "range_structure" in config["long_weights"]
    assert "range_structure" in config["short_weights"]


def test_transition_mode_weights_in_config() -> None:
    """The new 'transition' mode weights must be present and include vol_compression."""
    config = json.loads(
        (ROOT / "app/monitoring/configs/market_strategy_signal_config_v17.json").read_text(
            encoding="utf-8"
        )
    )
    assert "transition" in config["long_weights_by_mode"]
    assert "vol_compression" in config["long_weights_by_mode"]["transition"]
    assert "transition" in config["short_weights_by_mode"]
    assert "vol_compression" in config["short_weights_by_mode"]["transition"]


def test_strategy_generator_blocks_chasing_when_divergence_opposes_bias() -> None:
    config = json.loads(
        (ROOT / "app/monitoring/configs/market_strategy_signal_config_v17.json").read_text(
            encoding="utf-8"
        )
    )
    generator = StrategyGenerator(config)
    snapshot = {
        "technical_risk": {
            "divergence": {
                "status": "active",
                "direction": "bullish",
                "strategy_effect": "opposes_strategy",
                "recommended_action": "block_chasing",
                "summary": "4h 出现 RSI / MACD 底背离，削弱当前追空质量。",
                "confirmation": "收回 63730 上方后确认修复",
                "invalidation": "跌破 61320 后背离失效",
                "risk_reasons": ["背离方向与当前策略方向相反，禁止直接追单。"],
            }
        }
    }
    state = {
        "state": "SHORT_TRIGGERED",
        "bias": "short",
        "reasons": [],
        "entry_mode": "breakdown_follow",
    }

    adjusted = generator._apply_divergence_risk(snapshot, state)

    assert adjusted["state"] == "WAIT_SHORT_CONFIRMATION"
    assert adjusted["bias"] == "short"
    assert "背离方向与当前策略方向相反" in " ".join(adjusted["reasons"])
    assert "收回 63730" in " ".join(adjusted["blocking_gates"])
