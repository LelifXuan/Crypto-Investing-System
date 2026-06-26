from __future__ import annotations

from app.services.strategy_signal.confidence_dimensions import build_confidence_report


class MockScores:
    def __init__(self):
        self.data_quality_score = 65.0
        self.conflict_score = 8.0
        self.rr_long = 58.0
        self.rr_short = 42.0
        self.long_score = 0.62
        self.short_score = 0.18
        self.neutral_score = 0.20


REQUIRED_BUCKET_KEYS = [
    "data_integrity",
    "freshness",
    "multi_timeframe",
    "structure",
    "momentum",
    "flow",
    "technical_risk",
    "execution",
    "risk_reward",
    "event_risk",
    "conflict",
    "regime_fit",
]


def test_all_twelve_bucket_keys_present():
    snapshot = {
        "score_map": {
            "freshness": 72.0,
            "mtf_trend_bullish": 55.0,
            "bullish_structure": 60.0,
            "bearish_structure": 40.0,
            "bullish_momentum": 65.0,
            "bearish_momentum": 30.0,
            "volume_confirmation": 55.0,
                "volume_proxy_confirmation": 48.0,
                "funding_score": 50.0,
                "divergence_support_long": 54.0,
                "divergence_support_short": 46.0,
                "execution_quality": 55.0,
            "event_risk": 40.0,
            "regime_fit_long": 60.0,
            "regime_fit_short": 35.0,
        },
        "data_availability": {
            "funding": True,
            "open_interest": True,
        },
    }
    scores = MockScores()
    report = build_confidence_report(snapshot, scores)

    assert "confidence_score" in report
    assert "reliability_label" in report
    assert "confidence_buckets" in report
    assert "summary" in report
    assert isinstance(report["confidence_score"], float)
    assert 0.0 <= report["confidence_score"] <= 100.0

    bucket_keys = [b["key"] for b in report["confidence_buckets"]]
    assert len(bucket_keys) == 12, f"Expected 12 buckets, got {len(bucket_keys)}: {bucket_keys}"
    for key in REQUIRED_BUCKET_KEYS:
        assert key in bucket_keys, f"Missing bucket key: {key}"

    for bucket in report["confidence_buckets"]:
        assert "key" in bucket
        assert "label" in bucket
        assert "score" in bucket
        assert "weight" in bucket
        assert "impact" in bucket
        assert "reason" in bucket
        assert "missing" in bucket
        assert bucket["impact"] in ("support", "drag", "neutral")


def test_technical_risk_bucket_replaces_derivatives_bucket():
    snapshot = {
        "score_map": {},
        "data_availability": {},
    }
    scores = MockScores()
    report = build_confidence_report(snapshot, scores)

    bucket_keys = [b["key"] for b in report["confidence_buckets"]]
    assert "technical_risk" in bucket_keys
    assert "derivatives" not in bucket_keys


def test_data_quality_cap():
    snapshot = {
        "score_map": {},
        "data_availability": {},
    }
    scores = MockScores()
    scores.data_quality_score = 25.0
    report = build_confidence_report(snapshot, scores)
    assert report["confidence_score"] <= 48.0
