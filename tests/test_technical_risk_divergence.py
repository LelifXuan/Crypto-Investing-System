from __future__ import annotations

from app.services.technical_risk import (
    build_divergence_risk,
    contains_microstructure_terms,
    score_divergence_for_snapshot,
)


def _bullish_divergence() -> dict:
    return {
        "instrument_id": "btc-usdt-perp",
        "timeframe": "4h",
        "overall": {
            "tone": "bullish",
            "title": "多指标底背离偏强",
            "score": 0.62,
            "confidence": 0.58,
            "leaders": ["RSI", "MACD", "CCI"],
            "message": "多个指标提示下行动能衰减。",
        },
        "signals": [
            {
                "indicator": "RSI",
                "direction": "bullish",
                "confirmation": "收回 63730 上方后确认修复",
                "invalidation": "跌破 61320 后背离失效",
            }
        ],
    }


def _bearish_divergence() -> dict:
    return {
        "instrument_id": "btc-usdt-perp",
        "timeframe": "4h",
        "overall": {
            "tone": "bearish",
            "title": "多指标顶背离偏强",
            "score": -0.55,
            "confidence": 0.52,
            "leaders": ["RSI", "MACD", "CCI"],
            "message": "多个指标提示上行动能衰减。",
        },
        "signals": [
            {
                "indicator": "MACD",
                "direction": "bearish",
                "confirmation": "跌回 65000 下方后确认转弱",
                "invalidation": "突破 67200 后背离失效",
            }
        ],
    }


def test_bullish_divergence_blocks_chasing_short_strategy() -> None:
    risk = build_divergence_risk(_bullish_divergence(), strategy_bias="short")

    assert risk["status"] == "active"
    assert risk["direction"] == "bullish"
    assert risk["strategy_effect"] == "opposes_strategy"
    assert risk["recommended_action"] == "block_chasing"
    assert "追空" in risk["summary"]
    assert risk["confirmation"] == "收回 63730 上方后确认修复"
    assert risk["invalidation"] == "跌破 61320 后背离失效"
    assert not contains_microstructure_terms(risk)


def test_bearish_divergence_blocks_chasing_long_strategy() -> None:
    risk = build_divergence_risk(_bearish_divergence(), strategy_bias="long")

    assert risk["direction"] == "bearish"
    assert risk["strategy_effect"] == "opposes_strategy"
    assert risk["recommended_action"] == "block_chasing"
    assert "追多" in risk["summary"]
    assert not contains_microstructure_terms(risk)


def test_same_direction_divergence_supports_strategy_without_entry_signal_language() -> None:
    risk = build_divergence_risk(_bullish_divergence(), strategy_bias="long")

    assert risk["strategy_effect"] == "supports_strategy"
    assert risk["recommended_action"] == "allow"
    assert "不直接作为入场信号" in " ".join(risk["risk_reasons"])


def test_no_divergence_is_observe_only() -> None:
    risk = build_divergence_risk(None, strategy_bias="short")

    assert risk["status"] == "none"
    assert risk["direction"] == "neutral"
    assert risk["recommended_action"] == "observe"
    assert risk["strategy_effect"] == "none"


def test_divergence_snapshot_scores_are_strategy_facing() -> None:
    risk = build_divergence_risk(_bullish_divergence(), strategy_bias="short")
    scores = score_divergence_for_snapshot(risk)

    assert scores["technical_risk_availability"] == 100.0
    assert scores["divergence_support_long"] > 50
    assert scores["divergence_support_short"] == 50.0
    assert scores["opposite_divergence_risk_score"] > 50
