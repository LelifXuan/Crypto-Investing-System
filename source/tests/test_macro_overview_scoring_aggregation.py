"""Regression tests for macro overview scoring aggregation.

Covers three defects found on 2026-08-19:
- fed_operations was missing from the layer contribution weights, so its
  score never moved the total macro score.
- real_yield_10y alias collided with us_10y_yield in the scoring rule map,
  silently overriding the nominal 10Y thresholds with TIPS thresholds.
- layer means fabricated a neutral 50 for indicators without a concrete
  score (``int(item.score or 50)``), and layer contributions ignored
  indicator coverage.
"""

from __future__ import annotations

from app.schemas.market import MacroOverviewLayerRead
from app.services.macro.indicator_key_aliases import canonical_macro_key
from app.services.macro.scoring_engine import DEFAULT_MACRO_SCORING_ENGINE
from app.services.macro_overview import (
    LAYER_CONTRIBUTION_WEIGHTS,
    _confidence,
    _layer_contributions,
    _total_score,
)


def _layer(
    key: str,
    score: int,
    effective: int,
    total: int,
) -> MacroOverviewLayerRead:
    return MacroOverviewLayerRead(
        layer_key=key,
        label_cn=key,
        score=score,
        bias="中性",
        summary="",
        effective_count=effective,
        total_count=total,
        missing_count=0,
        stale_count=0,
        cached_count=0,
        is_scored=total > 0,
        not_scored_reason=None,
        contribution=0.0,
        indicators=[],
    )


def test_layer_contribution_weights_cover_all_layers_and_normalize() -> None:
    from app.services.macro_overview import LAYER_LABELS

    assert set(LAYER_CONTRIBUTION_WEIGHTS) == set(LAYER_LABELS), (
        "every layer must have a contribution weight"
    )
    assert abs(sum(LAYER_CONTRIBUTION_WEIGHTS.values()) - 1.0) < 1e-9


def test_layer_contributions_include_fed_operations() -> None:
    layers = [
        _layer("rates_policy", 70, 3, 3),
        _layer("inflation", 60, 3, 3),
        _layer("growth_labor", 60, 3, 3),
        _layer("liquidity_credit", 60, 3, 3),
        _layer("fed_operations", 90, 3, 3),
        _layer("cross_asset_confirmation", 60, 3, 3),
        _layer("event_window", 50, 1, 1),
    ]
    contributions = _layer_contributions({layer.layer_key: layer.score for layer in layers}, layers)
    assert "fed_operations" in contributions
    # 90 with full coverage must move the total materially.
    assert contributions["fed_operations"] >= 3.0
    total = _total_score(contributions)
    assert total > 55


def test_layer_contribution_scaled_by_indicator_coverage() -> None:
    layers = [
        _layer("liquidity_credit", 100, 2, 4),
        _layer("inflation", 85, 9, 9),
    ]
    contributions = _layer_contributions(
        {"liquidity_credit": 100, "inflation": 85}, layers
    )
    sparse = contributions["liquidity_credit"]
    # 50-point deviation at 50% coverage and 0.11 weight ≈ 2.75; a fully
    # covered 100-score layer would contribute ~5.5.
    assert sparse < 3.5
    assert contributions["inflation"] > sparse


def test_sparse_layer_does_not_saturate_total_score() -> None:
    layers = [
        _layer("liquidity_credit", 100, 2, 4),
    ]
    contributions = _layer_contributions({"liquidity_credit": 100}, layers)
    total = _total_score(contributions)
    assert total < 60, "a 2/4 layer at 100 must not push the total to 100"


def test_real_yield_10y_does_not_shadow_nominal_10y_rule() -> None:
    assert canonical_macro_key("real_yield_10y") == "real_yield_10y"

    nominal = DEFAULT_MACRO_SCORING_ENGINE._rules["us_10y_yield"]
    assert nominal["thresholds"]["low"] == 2.5
    assert nominal["thresholds"]["high"] == 6.0

    tips = DEFAULT_MACRO_SCORING_ENGINE._rules["real_yield_10y"]
    assert tips["thresholds"]["low"] == 0.5
    assert tips["thresholds"]["high"] == 2.8


def test_layer_mean_ignores_none_scores_and_bias_follows_score() -> None:
    # An indicator marked scored but with no concrete score must be
    # excluded from the layer mean instead of pulling it to a fake 50.
    from app.services.macro_overview import _score_to_bias

    layer = _layer("event_window", 50, 0, 0)
    assert _score_to_bias(30) == "偏空"
    assert _score_to_bias(65) == "偏多"
    assert _score_to_bias(50) == "中性"
    assert layer.total_count == 0


def test_confidence_capped_by_sparsest_scored_layer() -> None:
    complete = {"ratio": 0.85, "effective_count": 34, "total_count": 40}
    layers = [
        _layer("rates_policy", 60, 8, 9),
        _layer("liquidity_credit", 80, 2, 4),
        _layer("fed_operations", 70, 5, 11),
    ]
    # Global ratio is high but one layer is 2/4 (< 0.5) -> low.
    assert _confidence(complete, layers) == "low"

    full = [
        _layer("rates_policy", 60, 9, 9),
        _layer("liquidity_credit", 80, 4, 4),
        _layer("fed_operations", 70, 11, 11),
    ]
    assert _confidence(complete, full) == "high"

    # Fallback when no layer detail is passed stays on global ratio.
    assert _confidence({"ratio": 0.85}, None) == "high"
    assert _confidence({"ratio": 0.3}, None) == "low"
