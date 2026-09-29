from pathlib import Path

from app.services.cache_registry import strategy_scan_cache_key
from app.services.strategy_unified.opportunity_scanner import (
    _extract_scan_item_legacy as _extract_scan_item,
)

ROOT = Path(__file__).resolve().parents[1]


def _payload(*, confidence: float = 92.0, risk_reward: float = 2.0) -> dict:
    return {
        "status": "ready",
        "degraded_components": [],
        "market_decision_snapshot": {"snapshot_id": "scan-gate-test"},
        "trade_decision": {
            "side": "LONG",
            "trade_timeframe": "4h",
            "direction_timeframes": ["1d", "4h"],
            "risk_reward": {"value": risk_reward},
            "position_cap": "standard",
            "permission": "allow",
            "recommended_leverage": 0,
        },
        "horizon_views": {
            "strategic": {"direction": "LONG"},
            "tactical": {"direction": "LONG"},
        },
        "timeframe_stack": [
            {
                "timeframe": "1w",
                "direction": "LONG",
                "confidence": 97.0,
                "long_score": 78.0,
                "short_score": 42.0,
                "freshness": "fresh",
                "verdict_label": "周线多头结构",
                "evidence": ["周线趋势保持向上"],
            },
            {
                "timeframe": "1d",
                "direction": "LONG",
                "confidence": 88.0,
                "long_score": 73.0,
                "short_score": 46.0,
                "freshness": "fresh",
                "verdict_label": "日线多头结构",
                "evidence": ["日线结构已确认"],
            },
            {
                "timeframe": "4h",
                "direction": "LONG",
                "confidence": confidence,
                "long_score": 81.0,
                "short_score": 43.0,
                "freshness": "fresh",
                "current_price": 100.0,
                "key_support": 90.0,
                "key_resistance": 130.0,
                "invalidation": 90.0,
                "verdict_label": "4H 多头结构",
                "evidence": ["4H 结构与战术方向一致"],
            },
        ],
        "signal_coverage": [],
        "direction_resolution": {"conflicts": []},
        "evidence_trace": [],
    }


def test_each_timeframe_uses_its_own_confidence_and_summary() -> None:
    payload = _payload()
    weekly = _extract_scan_item(payload, "btc-usdt-perp", "BTC", "1w")
    daily = _extract_scan_item(payload, "btc-usdt-perp", "BTC", "1d")
    four_hour = _extract_scan_item(payload, "btc-usdt-perp", "BTC", "4h")

    assert [weekly.confidence, daily.confidence, four_hour.confidence] == [
        97.0,
        88.0,
        92.0,
    ]
    assert weekly.summary.startswith("周线多头结构")
    assert daily.summary.startswith("日线多头结构")
    assert four_hour.summary.startswith("4H 多头结构")


def test_matrix_gate_promotes_only_complete_high_certainty_setup() -> None:
    qualified = _extract_scan_item(
        _payload(),
        "btc-usdt-perp",
        "BTC",
        "4h",
    )
    low_confidence = _extract_scan_item(
        _payload(confidence=72.0),
        "btc-usdt-perp",
        "BTC",
        "4h",
    )
    poor_risk_reward = _extract_scan_item(
        _payload(risk_reward=0.8),
        "btc-usdt-perp",
        "BTC",
        "1d",
    )

    assert qualified.qualified is True
    assert qualified.qualification_reasons == []
    assert low_confidence.qualified is False
    assert "confidence_below_gate" in low_confidence.qualification_reasons
    assert poor_risk_reward.qualified is False
    assert "risk_reward_below_gate" in poor_risk_reward.qualification_reasons


def test_matrix_omits_confidence_but_ranking_keeps_it() -> None:
    matrix = (ROOT / "app/static/pages/strategy/renderScanMatrix.js").read_text(encoding="utf-8")
    ranked = (ROOT / "app/static/pages/strategy/renderScanRanked.js").read_text(encoding="utf-8")

    assert "item.confidence" not in matrix
    assert "Math.round(item.confidence)" in ranked
    assert "item.qualified !== true" in matrix
    assert "严格门禁" in matrix


def test_scan_cache_key_invalidates_pre_gate_payloads() -> None:
    assert strategy_scan_cache_key().endswith("v3-opportunity-v3")
