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