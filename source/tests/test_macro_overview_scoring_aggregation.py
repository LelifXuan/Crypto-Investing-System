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

from decimal import Decimal

import pytest

from app.schemas.market import MacroOverviewIndicatorRead, MacroOverviewLayerRead
from app.services.macro.indicator_key_aliases import canonical_macro_key
from app.services.macro.scoring_engine import (
    DEFAULT_MACRO_SCORING_ENGINE,
    DISPLAY_ONLY_REASON,
)
from app.services.macro_overview import (
    LAYER_CONTRIBUTION_WEIGHTS,
    _confidence,
    _data_completeness,
    _layer_contributions,
    _scored_share,
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


# ---------------------------------------------------------------------------
# Data coverage vs scoring eligibility.
#
# Regression (2026-09-22): the macro overview reported "数据置信度 不足" while
# every one of its 48 indicators carried live FRED values and the dashboard
# snapshot was 'ready'. The cause was a denominator, not the data:
# ``_confidence`` and ``_data_completeness`` divided scored indicators by the
# full layer size, so the 11 display-only indicators (Fed balance sheet, M2,
# SPY…) counted as missing data. ``fed_operations`` is 6/11 display-only, so
# its scored share sat at 45.5% < 0.5 forever and pinned the whole overview to
# low confidence no matter how complete the underlying data was.
# ---------------------------------------------------------------------------

def _indicator(key: str, *, scored: bool, reason: str | None) -> MacroOverviewIndicatorRead:
    return MacroOverviewIndicatorRead(
        indicator_key=key,
        label=key,
        tooltip=key,
        insight="",
        is_scored=scored,
        score=60 if scored else None,
        score_reason=reason,
    )


def _layer_with_display_only(
    key: str,
    *,
    scored: int,
    display_only: int,
    unscored_with_data_gap: int = 0,
    score: int = 60,
) -> MacroOverviewLayerRead:
    """A layer whose unscored indicators are a mix of by-design (display_only)
    and genuine gaps (any other reason)."""
    indicators = [
        _indicator(f"{key}-s{i}", scored=True, reason=None) for i in range(scored)
    ]
    indicators += [
        _indicator(f"{key}-d{i}", scored=False, reason=DISPLAY_ONLY_REASON)
        for i in range(display_only)
    ]
    indicators += [
        _indicator(f"{key}-g{i}", scored=False, reason="缺少可用观测")
        for i in range(unscored_with_data_gap)
    ]
    total = len(indicators)
    return MacroOverviewLayerRead(
        layer_key=key,
        label_cn=key,
        score=score,
        bias="中性",
        summary="",
        effective_count=scored,
        total_count=total,
        missing_count=unscored_with_data_gap,
        stale_count=0,
        cached_count=0,
        is_scored=scored > 0,
        not_scored_reason=None,
        contribution=0.0,
        indicators=indicators,
    )


def test_display_only_indicators_are_not_counted_as_a_coverage_gap() -> None:
    """The reported bug: a layer that is fully populated but partly
    display-only must not read as thinly covered."""
    layer = _layer_with_display_only("fed_operations", scored=5, display_only=6)
    assert _scored_share(layer) == 1.0


def test_genuine_gaps_still_lower_the_scored_share() -> None:
    """Guard the guard: excluding display-only from the denominator must not
    blind the metric to indicators that are missing for real."""
    layer = _layer_with_display_only(
        "fed_operations", scored=3, display_only=6, unscored_with_data_gap=2
    )
    assert _scored_share(layer) == pytest.approx(3 / 5)
    thin = _layer_with_display_only(
        "rates_policy", scored=1, display_only=0, unscored_with_data_gap=3
    )
    assert _scored_share(thin) == pytest.approx(0.25)


def test_fed_operations_alone_no_longer_caps_confidence() -> None:
    """The exact live composition that produced 数据置信度 不足 next to a ready
    snapshot: liquidity_credit 2/4 and fed_operations 5/11, both fully
    populated with display-only members."""
    layers = [
        _layer_with_display_only("rates_policy", scored=9, display_only=0),
        _layer_with_display_only("liquidity_credit", scored=2, display_only=2),
        _layer_with_display_only("fed_operations", scored=5, display_only=6),
        _layer_with_display_only("cross_asset_confirmation", scored=4, display_only=3),
    ]
    completeness = _data_completeness(layers)
    assert completeness["percent"] == 100.0
    assert _confidence(completeness, layers) == "high"


def test_confidence_still_capped_when_a_layer_has_real_gaps() -> None:
    layers = [
        _layer_with_display_only("rates_policy", scored=9, display_only=0),
        _layer_with_display_only(
            "liquidity_credit", scored=1, display_only=0, unscored_with_data_gap=3
        ),
    ]
    assert _scored_share(layers[1]) == pytest.approx(0.25)
    assert _confidence(_data_completeness(layers), layers) == "low"


def test_all_display_only_layer_is_skipped_not_treated_as_empty() -> None:
    """A layer with nothing scoreable has no scoring to be short of; it must not
    force low confidence on the rest of the overview."""
    layers = [
        _layer_with_display_only("rates_policy", scored=9, display_only=0),
        _layer_with_display_only("fed_operations", scored=0, display_only=4),
    ]
    assert _confidence(_data_completeness(layers), layers) == "high"


def test_completeness_keeps_the_full_catalogue_total() -> None:
    """``_regime_summary`` still prints "参与评分指标 37/48", so total_count must
    stay the full indicator catalogue while ratio excludes display-only."""
    layer = _layer_with_display_only("fed_operations", scored=5, display_only=6)
    completeness = _data_completeness([layer])
    assert completeness["total_count"] == 11
    assert completeness["scorable_count"] == 5
    assert completeness["effective_count"] == 5
    assert completeness["percent"] == 100.0


def test_scoring_engine_reason_string_is_the_shared_constant() -> None:
    """``_display_only_count`` matches on the reason string, so the engine and
    the coverage maths must agree on one spelling. A rename would otherwise
    silently restore the bug rather than fail.

    Uses a real registry key (fed_balance_sheet carries
    ``scoring_policy: "display_only"``) so this pins the shipped registry, not a
    stand-in.
    """
    item = _indicator("fed_balance_sheet", scored=False, reason=None)
    item.value_num = Decimal("6746548")
    result = DEFAULT_MACRO_SCORING_ENGINE.score(item)
    assert result.reason == DISPLAY_ONLY_REASON
    assert result.is_scored is False
