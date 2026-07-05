"""Acceptance tests for V1.7.4 regime-aware snapshot scoring.

Task 3 wires :mod:`app.services.strategy_signal.config_loader.detect_mode`
together with the per-mode weight tables added in Task 2 so
:class:`StrategySnapshotBuilder` now applies ``long_weights_by_mode[mode]``
(``trend`` / ``range`` / fallback to flat ``long_weights``) when computing
``long_score`` / ``short_score`` on the snapshot.

The tests focus on the sync helper :meth:`StrategySnapshotBuilder._build_snapshot`
which is the test seam used to exercise mode detection + weight selection
without touching the heavier async dependency fetches.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.strategy_signal import snapshot_builder
from app.services.strategy_signal.config_loader import load_strategy_signal_config
from app.services.strategy_signal.snapshot_builder import StrategySnapshotBuilder

# Sub-score values used across the mode-aware tests. They are picked so that
# the weighted contribution of each key is easy to verify by hand and the
# mode-specific tables produce clearly different totals.
_RANGE_FEATURES = {
    "mtf_trend_bullish": 80,
    "bullish_structure": 80,
    "bullish_momentum": 60,
    "long_risk_reward": 70,
    "regime_fit_long": 40,
    "execution_quality": 70,
    "range_structure": 80,
    "low_directional_spread": 60,
}


def test_snapshot_uses_range_mode_weights_when_detected(monkeypatch) -> None:
    """When ``detect_mode`` returns ``range``, snapshot applies range weights.

    Range-mode ``long_weights_by_mode['range']``::

        mtf_trend_bullish 0.05
        bullish_structure 0.05
        range_structure    0.30
        low_directional_spread 0.20
        long_risk_reward   0.15
        regime_fit_long    0.15
        execution_quality  0.10

    With the values from ``_RANGE_FEATURES`` the expected total is::

        80*0.05 + 80*0.05 + 80*0.30 + 60*0.20
        + 70*0.15 + 40*0.15 + 70*0.10 = 67.5
    """

    monkeypatch.setattr(snapshot_builder, "detect_mode", lambda *a, **kw: "range")
    monkeypatch.setattr(
        snapshot_builder, "detect_asset_class", lambda *a, **kw: "crypto"
    )

    snap = StrategySnapshotBuilder._build_snapshot(
        features=dict(_RANGE_FEATURES),
        regime="unknown",
        adx=15.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
    )

    expected = round(
        80 * 0.05
        + 80 * 0.05
        + 70 * 0.15
        + 40 * 0.15
        + 70 * 0.10
        + 80 * 0.30
        + 60 * 0.20,
        2,
    )
    assert snap["long_score"] == expected
    assert snap["mode"] == "range"
    assert snap["asset_class"] == "crypto"

    # In range mode the mtf_trend_bullish weight is 0.05, so increasing it
    # from 80 -> 100 only nudges the long_score by 1.0 (not the 4.4 a trend
    # table would add with weight 0.22). This pinpoints which weight table
    # was actually applied.
    high_trend = StrategySnapshotBuilder._build_snapshot(
        features={**_RANGE_FEATURES, "mtf_trend_bullish": 100},
        regime="unknown",
        adx=15.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
    )
    delta = high_trend["long_score"] - snap["long_score"]
    assert delta == pytest.approx(1.0, abs=1e-9)
    assert delta < 2.5  # range-mode reduces the impact of trend sub-score


def test_snapshot_uses_trend_mode_weights_when_detected(monkeypatch) -> None:
    """When ``detect_mode`` returns ``trend``, snapshot applies trend weights.

    Trend-mode ``long_weights_by_mode['trend']``::

        mtf_trend_bullish 0.22
        bullish_structure 0.22
        bullish_momentum  0.18
        long_risk_reward  0.13
        regime_fit_long   0.15
        execution_quality 0.10
    """

    monkeypatch.setattr(snapshot_builder, "detect_mode", lambda *a, **kw: "trend")
    monkeypatch.setattr(
        snapshot_builder, "detect_asset_class", lambda *a, **kw: "crypto"
    )

    snap = StrategySnapshotBuilder._build_snapshot(
        features=dict(_RANGE_FEATURES),
        regime="trend",
        adx=30.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
    )

    expected = round(
        80 * 0.22
        + 80 * 0.22
        + 60 * 0.18
        + 70 * 0.13
        + 40 * 0.15
        + 70 * 0.10,
        2,
    )
    assert snap["long_score"] == expected
    assert snap["mode"] == "trend"

    # Increasing mtf_trend_bullish from 80 -> 100 changes the score by
    # 20 * 0.22 = 4.4 in trend mode (vs 1.0 in range mode).
    high_trend = StrategySnapshotBuilder._build_snapshot(
        features={**_RANGE_FEATURES, "mtf_trend_bullish": 100},
        regime="trend",
        adx=30.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
    )
    delta = high_trend["long_score"] - snap["long_score"]
    assert delta == pytest.approx(4.4, abs=1e-9)


def test_snapshot_falls_back_to_flat_weights_for_transition_mode(monkeypatch) -> None:
    """When mode has no per-mode entry, fall back to flat ``long_weights``."""

    monkeypatch.setattr(
        snapshot_builder, "detect_mode", lambda *a, **kw: "transition"
    )
    monkeypatch.setattr(
        snapshot_builder, "detect_asset_class", lambda *a, **kw: "crypto"
    )

    config = load_strategy_signal_config()
    long_weights = config["long_weights"]

    snap = StrategySnapshotBuilder._build_snapshot(
        features=dict(_RANGE_FEATURES),
        regime="transition",
        adx=22.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        config=config,
    )

    expected = round(
        sum(_RANGE_FEATURES.get(k, 0) * w for k, w in long_weights.items()),
        2,
    )
    assert snap["long_score"] == expected
    assert snap["mode"] == "transition"


def test_snapshot_short_score_uses_mode_aware_short_weights(monkeypatch) -> None:
    """Mirror coverage for short side: range-mode shrinks trend bear weight."""

    monkeypatch.setattr(snapshot_builder, "detect_mode", lambda *a, **kw: "range")
    monkeypatch.setattr(
        snapshot_builder, "detect_asset_class", lambda *a, **kw: "crypto"
    )

    short_features = {
        "mtf_trend_bearish": 80,
        "bearish_structure": 80,
        "bearish_momentum": 60,
        "short_risk_reward": 70,
        "regime_fit_short": 40,
        "execution_quality": 70,
        "range_structure": 80,
        "low_directional_spread": 60,
    }
    snap = StrategySnapshotBuilder._build_snapshot(
        features=short_features,
        regime="unknown",
        adx=15.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
    )

    expected = round(
        80 * 0.05
        + 80 * 0.05
        + 70 * 0.15
        + 40 * 0.15
        + 70 * 0.10
        + 80 * 0.30
        + 60 * 0.20,
        2,
    )
    assert snap["short_score"] == expected


def test_snapshot_records_mode_and_weights_for_audit(monkeypatch) -> None:
    """The snapshot also stores the active mode, asset class and weights."""

    monkeypatch.setattr(snapshot_builder, "detect_mode", lambda *a, **kw: "range")
    monkeypatch.setattr(
        snapshot_builder, "detect_asset_class", lambda *a, **kw: "crypto"
    )

    snap = StrategySnapshotBuilder._build_snapshot(
        features=dict(_RANGE_FEATURES),
        regime="unknown",
        adx=15.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
    )

    assert snap["mode"] == "range"
    assert snap["asset_class"] == "crypto"
    assert snap["long_weights"]["mtf_trend_bullish"] == 0.05
    assert snap["short_weights"]  # recorded even when no short features change it
    assert isinstance(snap["long_score"], float)
    assert isinstance(snap["short_score"], float)
    assert isinstance(snap["neutral_score"], float)


def test_snapshot_uses_real_config_weights(monkeypatch) -> None:
    """End-to-end: detect_mode + the on-disk JSON config drive the score."""

    monkeypatch.setattr(snapshot_builder, "detect_mode", lambda *a, **kw: "range")
    monkeypatch.setattr(
        snapshot_builder, "detect_asset_class", lambda *a, **kw: "crypto"
    )

    config = load_strategy_signal_config()
    range_weights = config["long_weights_by_mode"]["range"]

    snap = StrategySnapshotBuilder._build_snapshot(
        features=dict(_RANGE_FEATURES),
        regime="unknown",
        adx=15.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        config=config,
    )

    expected = round(
        sum(_RANGE_FEATURES.get(k, 0) * w for k, w in range_weights.items()),
        2,
    )
    assert snap["long_score"] == expected


# --- V1.7.4 audit fix: feature_components populates range-mode sub-scores ---------
# In V1.7.4 the range-mode weight table reserves 0.20 + 0.15 + 0.15 = 0.50 of
# the long/short score for ``low_directional_spread`` + ``long_risk_reward``
# + ``short_risk_reward``. V1.7.3b's ``_feature_components`` did NOT populate
# these keys, so ``weighted_score`` silently used ``dict.get(key, 0) == 0``,
# zeroing half the range-mode signal in production. These tests pin the new
# behaviour so that regression is caught before reaching the snapshot cache.


def _call_feature_components(**overrides: Any) -> dict[str, Any]:
    """Invoke ``StrategySnapshotBuilder._feature_components`` with sane defaults."""

    kwargs: dict[str, Any] = {
        "indicators": {
            "ema_20": 100.0,
            "ema_50": 95.0,
            "ema_200": 90.0,
            "rsi_14": 55.0,
            "macd_hist": 0.5,
            "macd_hist_prev": 0.2,
            "adx_14": 18.0,
            "natr_14": 2.0,
        },
        "structure_overall": {"regime": "range"},
        "regime": "range",
        "direction_metrics": {
            "bullish": 55.0,
            "bearish": 45.0,
            "range": 90.0,
            "raw": 10.0,
            "scale": "signed",
        },
        "rsi": 55.0,
        "macd": 0.5,
        "macd_prev": 0.2,
        "adx": 18.0,
    }
    kwargs.update(overrides)
    return StrategySnapshotBuilder._feature_components(**kwargs)


def test_feature_components_populates_range_mode_subscores() -> None:
    """`_feature_components` must populate all 3 range-mode keys (V1.7.4 fix)."""

    # Use a perfectly symmetric direction split so low_directional_spread
    # hits the 100 max and risk_reward falls back to the neutral default.
    features = _call_feature_components(
        direction_metrics={
            "bullish": 50.0,
            "bearish": 50.0,
            "range": 100.0,
            "raw": 0.0,
            "scale": "signed",
        },
    )

    assert "low_directional_spread" in features
    assert "long_risk_reward" in features
    assert "short_risk_reward" in features
    # None of the 3 range-mode sub-scores may silently stay at 0 when inputs
    # are missing — that was the V1.7.3b bug (35% of range-mode weight lost).
    assert features["low_directional_spread"] > 0
    assert features["long_risk_reward"] == 50.0
    assert features["short_risk_reward"] == 50.0
    # A gap of 0 (50/50) → spread score of 100 (maximum range-friendliness).
    assert features["low_directional_spread"] == pytest.approx(100.0, abs=1e-9)


def test_feature_components_low_directional_spread_uses_direction_metrics() -> None:
    """``low_directional_spread`` reflects the bullish/bearish gap."""

    # Symmetric bullish/bearish → small gap → high spread score (range-friendly).
    symmetric = _call_feature_components(
        direction_metrics={
            "bullish": 60.0,
            "bearish": 60.0,
            "range": 80.0,
            "raw": 0.0,
            "scale": "signed",
        }
    )
    assert symmetric["low_directional_spread"] == pytest.approx(100.0, abs=1e-9)

    # 80 bullish, 30 bearish → gap = 50 → spread score = 50 (neutral).
    divergent = _call_feature_components(
        direction_metrics={
            "bullish": 80.0,
            "bearish": 30.0,
            "range": 50.0,
            "raw": 50.0,
            "scale": "signed",
        }
    )
    assert divergent["low_directional_spread"] == pytest.approx(50.0, abs=1e-9)


def test_feature_components_risk_reward_computed_from_inputs() -> None:
    """When entry/stop/tp1 are provided, RR score reflects the R-multiple."""

    # RR = (tp - entry) / (entry - stop) = (110 - 100) / (100 - 95) = 2.0
    # → risk_reward_score(2.0) == 80 per risk_reward.py's "< 3" branch.
    features = _call_feature_components(
        long_entry=100.0, long_stop=95.0, long_tp1=110.0,
        short_entry=100.0, short_stop=105.0, short_tp1=90.0,
    )
    assert features["long_risk_reward"] == 80.0
    assert features["short_risk_reward"] == 80.0
    assert features["risk_reward_source"] == "entries+stops+tps"


def test_feature_components_risk_reward_neutral_when_inputs_missing() -> None:
    """Falls back to 50 (neutral) when no entry/stop/tp1 are passed in."""

    features = _call_feature_components()
    assert features["long_risk_reward"] == 50.0
    assert features["short_risk_reward"] == 50.0
    assert features["risk_reward_source"] == "neutral_default"


def test_range_mode_weights_are_not_silently_zeroed(monkeypatch) -> None:
    """Regression: range-mode weighted_score now sees the 3 sub-scores.

    Reproduces the V1.7.3b bug where the helper produced a feature dict
    missing ``low_directional_spread`` / ``long_risk_reward`` /
    ``short_risk_reward``, so ``weighted_score`` fell back to 0 for them.
    With those keys populated, the range-mode score must reflect the
    0.20 + 0.15 + 0.15 weights — not silently default to 0.
    """

    monkeypatch.setattr(snapshot_builder, "detect_mode", lambda *a, **kw: "range")
    monkeypatch.setattr(
        snapshot_builder, "detect_asset_class", lambda *a, **kw: "crypto"
    )

    # Build features the way ``build()`` would after the audit fix:
    # symmetric direction split, no entries → neutral defaults.
    raw_features = _call_feature_components(
        direction_metrics={
            "bullish": 50.0,
            "bearish": 50.0,
            "range": 100.0,
            "raw": 0.0,
            "scale": "signed",
        },
    )
    # Defaults for the new keys (no entries → neutral 50, no spread → 100):
    assert raw_features["low_directional_spread"] == pytest.approx(100.0, abs=1e-9)
    assert raw_features["long_risk_reward"] == 50.0
    assert raw_features["short_risk_reward"] == 50.0

    snap = StrategySnapshotBuilder._build_snapshot(
        features=dict(raw_features),
        regime="range",
        adx=18.0,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
    )

    # Range-mode weight for low_directional_spread is 0.20 — pre-fix this
    # contribution would have been 0 * 0.20 = 0 (silent weight loss).
    long_contrib_low_directional_spread = (
        raw_features["low_directional_spread"] * 0.20
    )
    long_contrib_risk_reward = raw_features["long_risk_reward"] * 0.15
    assert long_contrib_low_directional_spread == pytest.approx(20.0, abs=1e-9)
    assert long_contrib_risk_reward == pytest.approx(7.5, abs=1e-9)

    # Final long_score must be >= the sum of just these two contributions
    # (other sub-scores are > 0 here too) — proves the keys are in the dict
    # rather than falling through to 0.
    assert snap["long_score"] >= (
        long_contrib_low_directional_spread + long_contrib_risk_reward
    )


# --- V1.7.5 volatility compression: multi-period percentile rank ---------


def test_vol_compression_score_multi_period_percentile_rank() -> None:
    """bb_width vs bb_width_ma_90: extreme compression (ratio<0.5) → score 90+.

    The helper is a pure percentile-rank bucketing function. It maps the
    ratio ``bb_width / bb_width_ma_90`` to a 0..100 score so the snapshot
    can use it as a sub-score without recomputing the math at the call
    site. Five valid-ratio buckets plus three missing-data fallbacks.
    """

    # Extreme compression: bb_width is half of MA → score 90+
    score = snapshot_builder._compute_vol_compression(bb_width=0.03, bb_width_ma_90=0.07)
    assert score >= 90

    # Strong compression: ratio < 0.7 → score 75
    score = snapshot_builder._compute_vol_compression(bb_width=0.05, bb_width_ma_90=0.08)
    assert score == 75

    # Neutral: ratio in 0.85-1.15 → score 50
    score = snapshot_builder._compute_vol_compression(bb_width=0.07, bb_width_ma_90=0.07)
    assert score == 50

    # Expansion: ratio > 1.4 → score 25
    score = snapshot_builder._compute_vol_compression(bb_width=0.10, bb_width_ma_90=0.07)
    assert score == 25

    # Missing data → fallback 50
    assert snapshot_builder._compute_vol_compression(None, 0.07) == 50
    assert snapshot_builder._compute_vol_compression(0.03, None) == 50
    assert snapshot_builder._compute_vol_compression(0.0, 0.07) == 50