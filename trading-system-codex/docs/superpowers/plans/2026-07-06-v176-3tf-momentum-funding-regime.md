# V1.7.6 — 3-TF Momentum + Funding Regime Sub-Score — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-band `bullish_momentum` / `bearish_momentum` sub-score with three independent time-frame momentum sub-scores (5/20/60 bars), and add `funding_pressure_long` / `funding_pressure_short` sub-scores derived from V2 `derivatives_regime.funding_state`, while restoring the dead `funding_crowding_score` to a real value.

**Architecture:** Three-layer refactor inside `StrategySnapshotBuilder._feature_components` + downstream weighted-score pipeline.
- **Layer A**: 3-frame momentum (`_compute_momentum_at_scale` × 3 + `_percentile_rank` helper). Each frame has its own inputs and percentile rank; old `bullish_momentum`/`bearish_momentum` keys deleted.
- **Layer B**: Funding regime sub-score (`_compute_funding_pressure`) reads V2 `derivatives_regime.funding_state` and emits `funding_pressure_long`/`funding_pressure_short` + `funding_degraded` flag. When V2 unavailable: skip + renormalize (per spec decision B1).
- **Layer C**: Reconnect `funding_crowding_score` (replace hardcoded `0` at `snapshot_builder.py:710`) using the same V2 funding_state mapping, so existing `scoring_engine._long_penalty` actually fires.

**Tech Stack:** Python 3.x, pytest, FastAPI existing pipeline, JSON5 config (`market_strategy_signal_config_v17.json`), V2 unified strategy engine.

**Reference Spec:** `docs/superpowers/specs/2026-07-06-v176-3tf-momentum-funding-regime-design.md` (already committed).

---

## File Structure / Decomposition

**Files to modify:**

| File | Responsibility change |
|---|---|
| `app/services/strategy_signal/risk_reward.py` | Add `_percentile_rank(history, current)` helper |
| `app/services/strategy_signal/snapshot_builder.py` | Add `_compute_momentum_at_scale`, `_compute_funding_pressure`, `_remap_funding_crowding`; update `_feature_components` signature; wire 3-frame RSI/MACD + V2 funding_state in `build()` |
| `app/services/strategy_signal/scoring_engine.py` | Add `weighted_score_skip` (skip + renormalize); keep existing `weighted_score` |
| `app/services/strategy_signal/config_loader.py` | Remove `bullish_momentum`/`bearish_momentum` from `DEFAULT_STRATEGY_SIGNAL_CONFIG`; add comment for transition to JSON-loaded weights |
| `app/services/strategy_signal/confidence_dimensions.py` | Replace `bullish_momentum`/`bearish_momentum` read with new 6-key max |
| `app/services/strategy_signal/setup_lifecycle.py` | Same replacement if used |
| `app/services/strategy_signal/strategy_generator.py` | Same replacement if used |
| `app/monitoring/configs/market_strategy_signal_config_v17.json` | New per-mode weight tables; add `momentum_scale_definitions` + `funding_regime_mapping` |

**Files to create:**

| File | Responsibility |
|---|---|
| `tests/test_v176_3timeframe_momentum.py` | 8 unit tests for Layer A |
| `tests/test_v176_funding_regime.py` | 7 unit tests for Layer B + Layer C |

**Files to modify (test fixtures + 1 cascade test):**

| File | Change |
|---|---|
| `tests/test_strategy_decision_rules.py` | Replace `bullish_momentum: ...` fixtures with new keys |
| `tests/test_strategy_no_microstructure.py` | Same |
| `tests/test_strategy_signal_snapshot.py` | Same + new weight-sum tests |
| `tests/test_strategy_setup_lifecycle_v17.py` | Same if applicable |
| `tests/test_snapshot_feature_sources.py` | Add `test_old_momentum_keys_deleted` + augment independence test |
| `tests/test_confidence_dimensions.py` | Same fixture migration |

---

## Task 1: Add `_percentile_rank` helper to `risk_reward.py`

**Files:**
- Modify: `app/services/strategy_signal/risk_reward.py:1-23`
- Create: `tests/test_v176_3timeframe_momentum.py`

- [ ] **Step 1.1: Write the failing test for `_percentile_rank`**

Add to a new file `tests/test_v176_3timeframe_momentum.py`:

```python
"""Unit tests for V1.7.6 — Layer A: 3-timeframe momentum."""

from __future__ import annotations

import math

from app.services.strategy_signal.risk_reward import _percentile_rank


def test_percentile_rank_empty_history_returns_50():
    """No history → neutral 50."""
    assert _percentile_rank([], 70.0) == 50.0


def test_percentile_rank_none_current_returns_50():
    """NaN/None current → neutral 50."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile_rank(history, None) == 50.0
    assert _percentile_rank(history, math.nan) == 50.0


def test_percentile_rank_median_value_returns_50():
    """Current value at exact median → 50."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]  # 5 values, median = 30
    # 30 (current) is at position 2 of 5 → 2/5 = 40% → but values ≤30 are 30,20,10 = 3, so 3/5 = 60%
    result = _percentile_rank(history, 30.0)
    assert 50.0 <= result <= 70.0  # allow minor band given ≤ vs < strictness


def test_percentile_rank_extreme_high_value():
    """Highest value in history → ~100."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile_rank(history, 50.0) == 100.0


def test_percentile_rank_extreme_low_value():
    """Lowest value in history → 0 (if none below) else <20."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]
    # 5 is below all 5 values → 0/5 = 0
    assert _percentile_rank(history, 5.0) == 0.0


def test_percentile_rank_clamps_to_0_100():
    """Output never escapes [0, 100]."""
    history = [10.0] * 90  # all same value
    result = _percentile_rank(history, 10.0)
    assert 0.0 <= result <= 100.0
    # current=10.0, all 90 are ≤10.0 → 90/90 = 100
    assert result == 100.0
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py -v`
Expected: `ImportError: cannot import name '_percentile_rank' from 'app.services.strategy_signal.risk_reward'`

- [ ] **Step 1.3: Implement `_percentile_rank` in `risk_reward.py`**

Add the following at end of `app/services/strategy_signal/risk_reward.py` (after `compute_risk_reward`):

```python
def _percentile_rank(history: list[float] | None, current: float | None) -> float:
    """Return percentile rank of `current` against `history` as 0..100.

    Returns 50.0 for empty history, None current, or NaN current.
    """
    if not history:
        return 50.0
    if current is None:
        return 50.0
    if current != current:  # NaN check
        return 50.0
    try:
        current_f = float(current)
    except (TypeError, ValueError):
        return 50.0
    below_or_equal = sum(1 for x in history if x is not None and x <= current_f)
    pct = below_or_equal / len(history) * 100
    return clamp(pct, 0.0, 100.0)
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py -v`
Expected: 6 tests pass

- [ ] **Step 1.5: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/risk_reward.py tests/test_v176_3timeframe_momentum.py
git commit -m "[v1.7.6] feat(risk_reward): add _percentile_rank helper for momentum percentile"
```

---

## Task 2: Add `_compute_momentum_at_scale` to `snapshot_builder.py`

**Files:**
- Modify: `app/services/strategy_signal/snapshot_builder.py` (top-level helpers section, near `_compute_vol_compression` at line 161-186)
- Modify: `tests/test_v176_3timeframe_momentum.py`

- [ ] **Step 2.1: Write the failing test for `_compute_momentum_at_scale`**

Append to `tests/test_v176_3timeframe_momentum.py`:

```python
from app.services.strategy_signal.snapshot_builder import _compute_momentum_at_scale


def test_compute_momentum_at_scale_neutral_when_all_inputs_missing():
    """No RSI / MACD / history → (50, 50)."""
    bullish, bearish = _compute_momentum_at_scale(
        rsi=None,
        macd_hist=None,
        macd_prev=None,
        rsi_history=None,
    )
    assert bullish == 50.0
    assert bearish == 50.0


def test_compute_momentum_at_scale_high_rsi_high_percentile_bullish():
    """RSI=80 with all-history=50 → ~100 percentile → bullish very high."""
    history = [50.0] * 90
    bullish, bearish = _compute_momentum_at_scale(
        rsi=80.0,
        macd_hist=1.0,
        macd_prev=0.5,
        rsi_history=history,
    )
    assert bullish > 80.0
    assert bearish < 50.0


def test_compute_momentum_at_scale_negative_macd_delta_dampens_bullish():
    """MACD delta negative → bullish lower than baseline 50."""
    history = [50.0] * 90
    bullish_pos, _ = _compute_momentum_at_scale(
        rsi=50.0,
        macd_hist=0.5,
        macd_prev=0.0,
        rsi_history=history,
    )
    bullish_neg, _ = _compute_momentum_at_scale(
        rsi=50.0,
        macd_hist=-0.5,
        macd_prev=0.0,
        rsi_history=history,
    )
    # positive MACD delta should lift bullish; negative should leave it at 50 (no bullish contribution)
    assert bullish_pos > bullish_neg


def test_compute_momentum_at_scale_clamped_to_0_100():
    """Output always in [0, 100]."""
    history = [10.0] * 90
    bullish, bearish = _compute_momentum_at_scale(
        rsi=200.0,  # extreme
        macd_hist=100.0,
        macd_prev=-100.0,
        rsi_history=history,
    )
    assert 0.0 <= bullish <= 100.0
    assert 0.0 <= bearish <= 100.0
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py::test_compute_momentum_at_scale_neutral_when_all_inputs_missing -v`
Expected: `ImportError: cannot import name '_compute_momentum_at_scale'`

- [ ] **Step 2.3: Implement `_compute_momentum_at_scale` in `snapshot_builder.py`**

In `app/services/strategy_signal/snapshot_builder.py`, after `_compute_vol_compression` (around line 186), add:

```python
def _compute_momentum_at_scale(
    *,
    rsi: float | None,
    macd_hist: float | None,
    macd_prev: float | None,
    rsi_history: list[float] | None,
) -> tuple[float, float]:
    """Compute momentum sub-score at a single time scale.

    Returns (bullish, bearish) each in [0, 100]. RSI percentile rank over
    ``rsi_history`` (default 90-bar window) replaces absolute RSI value.
    MACD histogram delta adds direction-aware bias. Falls back to (50, 50)
    when inputs are missing.
    """
    from app.services.strategy_signal.risk_reward import _percentile_rank

    if rsi is None or macd_hist is None or macd_prev is None:
        return 50.0, 50.0

    rsi_pct = _percentile_rank(rsi_history, rsi)
    macd_delta_bull = max(0.0, float(macd_hist) - float(macd_prev)) * 3.0
    macd_delta_bear = max(0.0, float(macd_prev) - float(macd_hist)) * 3.0

    raw_bullish = 50.0 + (rsi_pct - 50.0) * 0.85 + macd_delta_bull
    raw_bearish = 50.0 + (100.0 - rsi_pct) * 0.85 + macd_delta_bear

    return clamp(raw_bullish), clamp(raw_bearish)
```

- [ ] **Step 2.4: Run test to verify all 4 new tests pass**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py -v`
Expected: 10 tests pass (6 percentile + 4 momentum)

- [ ] **Step 2.5: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/snapshot_builder.py tests/test_v176_3timeframe_momentum.py
git commit -m "[v1.7.6] feat(snapshot_builder): add _compute_momentum_at_scale for 3-TF momentum"
```

---

## Task 3: Update `_feature_components` to emit 6 new keys (no consumer change yet)

**Files:**
- Modify: `app/services/strategy_signal/snapshot_builder.py:780-878`
- Modify: `tests/test_v176_3timeframe_momentum.py`

- [ ] **Step 3.1: Write the failing test for new keys emission**

Append to `tests/test_v176_3timeframe_momentum.py`:

```python
from app.services.strategy_signal.snapshot_builder import StrategySnapshotBuilder


def test_feature_components_emits_six_momentum_keys():
    """All 6 new momentum keys present in features dict."""
    features = StrategySnapshotBuilder._feature_components(
        indicators={"ema_20": 100, "adx_14": 25},
        structure_overall={"bias": "neutral"},
        regime="transition",
        direction_metrics={"bullish": 60.0, "bearish": 40.0},
        rsi=58.0,
        macd=1.0,
        macd_prev=0.5,
        adx=25.0,
    )
    for key in (
        "momentum_short",
        "momentum_short_bearish",
        "momentum_mid",
        "momentum_mid_bearish",
        "momentum_long",
        "momentum_long_bearish",
    ):
        assert key in features, f"missing key {key}"


def test_feature_components_does_not_emit_old_momentum_keys():
    """Old bullish_momentum / bearish_momentum / momentum_source deleted."""
    features = StrategySnapshotBuilder._feature_components(
        indicators={"ema_20": 100, "adx_14": 25},
        structure_overall={"bias": "neutral"},
        regime="trend",
        direction_metrics={"bullish": 60.0, "bearish": 40.0},
        rsi=58.0,
        macd=1.0,
        macd_prev=0.5,
        adx=25.0,
    )
    for key in ("bullish_momentum", "bearish_momentum", "momentum_source"):
        assert key not in features, f"old key {key} should be removed"


def test_feature_components_three_frame_momentum_independent_from_direction_metrics():
    """Changing direction_metrics does not affect any momentum sub-score."""
    base_kwargs = dict(
        indicators={"ema_20": 100, "ema_20_prev": 99, "ema_50": 98, "ema_200": 95, "adx_14": 25},
        structure_overall={"bias": "neutral"},
        regime="trend",
        rsi=62.0,
        macd=1.0,
        macd_prev=0.5,
        adx=25.0,
    )
    bullish = StrategySnapshotBuilder._feature_components(
        **base_kwargs,
        direction_metrics={"bullish": 90.0, "bearish": 10.0},
    )
    bearish = StrategySnapshotBuilder._feature_components(
        **base_kwargs,
        direction_metrics={"bullish": 10.0, "bearish": 90.0},
    )
    for key in (
        "momentum_short",
        "momentum_short_bearish",
        "momentum_mid",
        "momentum_mid_bearish",
        "momentum_long",
        "momentum_long_bearish",
    ):
        assert bullish[key] == bearish[key], f"{key} depends on direction_metrics"
```

- [ ] **Step 3.2: Run tests to verify they fail (old code path)**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py::test_feature_components_emits_six_momentum_keys tests/test_v176_3timeframe_momentum.py::test_feature_components_does_not_emit_old_momentum_keys -v`
Expected: 2 failures (`KeyError` for missing new keys; assertion error for old keys still present)

- [ ] **Step 3.3: Add new emit while keeping old keys temporarily (transitional)**

In `app/services/strategy_signal/snapshot_builder.py` `_feature_components` (around line 800-844), ADD these lines AFTER existing momentum emission (after line 811):

```python
    # V1.7.6: 3-timeframe momentum (Layer A) — replaces single bullish/bearish_momentum.
    # Each scale computes its own percentile rank from a 90-bar RSI history.
    # Transitional: emit BOTH old (single) and new (3-frame) keys until consumers migrate.
    short_bullish, short_bearish = _compute_momentum_at_scale(
        rsi=rsi,
        macd_hist=macd,
        macd_prev=macd_prev,
        rsi_history=None,  # could not derive 90-bar history from signature; fall back to None → neutral
    )
    # Mid and long scaled: rely on the only RSI we receive — apply length-aware dampening
    # to differentiate (mid: dampen to 0.85x; long: 0.70x). No new upstream signal yet.
    mid_bullish = clamp(50.0 + (short_bullish - 50.0) * 0.85)
    mid_bearish = clamp(50.0 + (short_bearish - 50.0) * 0.85)
    long_bullish = clamp(50.0 + (short_bullish - 50.0) * 0.70)
    long_bearish = clamp(50.0 + (short_bearish - 50.0) * 0.70)
```

**Important**: We're keeping `bullish_momentum` / `bearish_momentum` / `momentum_source` in the dict YET because Task 8 (consumer migration) hasn't happened. The above `short_bullish` derivation is a placeholder until Task 9 wires real history.

- [ ] **Step 3.4: Add new keys to `features` dict (keep old keys alongside for now)**

In the same `features: dict[str, Any] = { ... }` block (around line 831-853), ADD new entries AFTER existing `bullish_momentum`:

```python
        # V1.7.6 transitional: new 3-frame keys; old keys retained until consumer migration (Task 8).
        "momentum_short": short_bullish,
        "momentum_short_bearish": short_bearish,
        "momentum_mid": mid_bullish,
        "momentum_mid_bearish": mid_bearish,
        "momentum_long": long_bullish,
        "momentum_long_bearish": long_bearish,
```

- [ ] **Step 3.5: Run tests — expect transient state: new keys present, old keys also present**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py::test_feature_components_emits_six_momentum_keys -v`
Expected: PASS

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py::test_feature_components_does_not_emit_old_momentum_keys -v`
Expected: FAIL (old keys still present). This is expected at this step.

- [ ] **Step 3.6: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/snapshot_builder.py tests/test_v176_3timeframe_momentum.py
git commit -m "[v1.7.6] feat(snapshot_builder): transitional emit 6 momentum keys (old keys retained)"
```

---

## Task 4: Add `_compute_funding_pressure` and `_remap_funding_crowding` (Layer B + Layer C)

**Files:**
- Modify: `app/services/strategy_signal/snapshot_builder.py` (helpers section near `_compute_setup_probability`)
- Create: `tests/test_v176_funding_regime.py`

- [ ] **Step 4.1: Write the failing tests for funding helpers**

Create `tests/test_v176_funding_regime.py`:

```python
"""Unit tests for V1.7.6 — Layer B + Layer C: Funding regime sub-score."""

from __future__ import annotations

from app.services.strategy_signal.snapshot_builder import (
    _compute_funding_pressure,
    _remap_funding_crowding,
)


def test_funding_pressure_positive_hot_suppresses_long_rewards_short():
    long, short, degraded = _compute_funding_pressure("positive_hot")
    assert long == 15.0
    assert short == 85.0
    assert degraded is False


def test_funding_pressure_negative_hot_suppresses_short_rewards_long():
    long, short, degraded = _compute_funding_pressure("negative_hot")
    assert long == 85.0
    assert short == 15.0
    assert degraded is False


def test_funding_pressure_neutral_is_50_50():
    long, short, degraded = _compute_funding_pressure("neutral")
    assert long == 50.0
    assert short == 50.0
    assert degraded is False


def test_funding_pressure_missing_returns_none_with_degraded_flag():
    for value in (None, "", "DATA_MISSING", "missing", "degraded", "unexpected_state"):
        long, short, degraded = _compute_funding_pressure(value)
        assert long is None, f"expected None for {value!r}, got {long}"
        assert short is None, f"expected None for {value!r}, got {short}"
        assert degraded is True, f"expected degraded=True for {value!r}"


def test_remap_funding_crowding_positive_hot_returns_80():
    assert _remap_funding_crowding("positive_hot") == 80.0


def test_remap_funding_crowding_negative_hot_returns_80():
    assert _remap_funding_crowding("negative_hot") == 80.0


def test_remap_funding_crowding_neutral_returns_20():
    assert _remap_funding_crowding("neutral") == 20.0


def test_remap_funding_crowding_missing_returns_0():
    for value in (None, "DATA_MISSING", "missing", "degraded", "extreme_positive_hot"):
        assert _remap_funding_crowding(value) == 0.0, f"expected 0 for {value!r}"
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py -v`
Expected: `ImportError: cannot import name '_compute_funding_pressure'`

- [ ] **Step 4.3: Implement `_compute_funding_pressure` and `_remap_funding_crowding`**

In `app/services/strategy_signal/snapshot_builder.py`, after `_compute_setup_probability` definition (around line 213), add:

```python
# V1.7.6 funding regime mapping per derivatives_regime.derive funding_state.
_FUNDING_PRESSURE_MAP: dict[str, tuple[float, float]] = {
    "positive_hot": (15.0, 85.0),   # (long, short)
    "negative_hot": (85.0, 15.0),
    "neutral": (50.0, 50.0),
}
_FUNDING_CROWDING_MAP: dict[str, float] = {
    "positive_hot": 80.0,
    "negative_hot": 80.0,
    "neutral": 20.0,
}


def _compute_funding_pressure(
    funding_state: str | None,
) -> tuple[float | None, float | None, bool]:
    """Map V2 derivatives_regime.funding_state to (long, short, degraded).

    Returns (None, None, True) when state is missing or unrecognized. Per
    decision B1 in the V1.7.6 spec, callers should skip weighted-score slots
    and renormalize when degraded.
    """
    if funding_state is None or not isinstance(funding_state, str):
        return None, None, True
    normalized = funding_state.strip().lower()
    if normalized in _FUNDING_PRESSURE_MAP:
        long_v, short_v = _FUNDING_PRESSURE_MAP[normalized]
        return long_v, short_v, False
    return None, None, True


def _remap_funding_crowding(funding_state: str | None) -> float:
    """Map V2 funding_state to funding_crowding_score for the existing penalty.

    Missing or unrecognized states → 0 (preserves dead-zero behavior so legacy
    penalty terms remain no-op when V2 is unavailable).
    """
    if funding_state is None or not isinstance(funding_state, str):
        return 0.0
    normalized = funding_state.strip().lower()
    return _FUNDING_CROWDING_MAP.get(normalized, 0.0)
```

- [ ] **Step 4.4: Run tests to verify all 8 pass**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py -v`
Expected: 8 tests pass

- [ ] **Step 4.5: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/snapshot_builder.py tests/test_v176_funding_regime.py
git commit -m "[v1.7.6] feat(snapshot_builder): add funding pressure + remap funding_crowding"
```

---

## Task 5: Add `weighted_score_skip` to `scoring_engine.py`

**Files:**
- Modify: `app/services/strategy_signal/scoring_engine.py:43-44`
- Create: `tests/test_v176_funding_regime.py` (extend it)

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/test_v176_funding_regime.py`:

```python
from app.services.strategy_signal.scoring_engine import weighted_score_skip


def test_weighted_score_skip_all_slots_present_normal_behavior():
    """When no slots are None, output equals old weighted_score."""
    values = {"a": 80.0, "b": 40.0}
    weights = {"a": 0.5, "b": 0.5}
    result = weighted_score_skip(values, weights)
    assert result == 60.0


def test_weighted_score_skip_none_slot_renormalizes():
    """Skip None, renormalize the remaining slots to original total weight."""
    # Without skip: (80 * 0.5 + 40 * 0.5) = 60
    # With skip and funding_pressure_long=None:
    #   used_pairs = [(80, 0.4), (40, 0.5)]  (a weights 0.5, b 0.5)
    #   sum_weights = 0.4 + 0.5 = 0.9
    #   score = (80*0.4 + 40*0.5) / 0.9 * (0.5 + 0.5) = (32 + 20)/0.9 = 57.78
    values = {"a": 80.0, "b": 40.0, "funding_pressure_long": None}
    weights = {"a": 0.4, "b": 0.5, "funding_pressure_long": 0.1}
    result = weighted_score_skip(values, weights)
    # Expected renormalization: (80*0.4 + 40*0.5) / 0.9 * 1.0 = 32+20=52/0.9 = 57.778
    assert abs(result - (52.0 / 0.9)) < 0.01


def test_weighted_score_skip_all_slots_none_returns_50():
    """All degraded → neutral 50."""
    values = {"a": None, "b": None}
    weights = {"a": 0.5, "b": 0.5}
    result = weighted_score_skip(values, weights)
    assert result == 50.0


def test_weighted_score_skip_clamps_to_0_100():
    """Output always in [0, 100]."""
    values = {"a": 200.0}  # out-of-band
    weights = {"a": 1.0}
    result = weighted_score_skip(values, weights)
    assert 0.0 <= result <= 100.0
```

- [ ] **Step 5.2: Run tests to verify they fail**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py::test_weighted_score_skip_all_slots_present_normal_behavior -v`
Expected: `ImportError: cannot import name 'weighted_score_skip'`

- [ ] **Step 5.3: Implement `weighted_score_skip`**

In `app/services/strategy_signal/scoring_engine.py`, after `weighted_score` (line 43-44), add:

```python
def weighted_score_skip(
    values: dict[str, Any], weights: dict[str, float]
) -> float:
    """Variant of weighted_score that skips slots with None values.

    Used by V1.7.6 funding_pressure slots when V2 derivatives_regime is
    degraded. The remaining slots are renormalized so the total weight
    contribution equals sum(weights.values()), avoiding score inflation.

    Returns 50.0 if all slots are None (degraded fallback).
    """
    used_pairs: list[tuple[float, float]] = []
    target_weight_sum = sum(weights.values())
    for key, weight in weights.items():
        value = values.get(key)
        if value is None:
            continue
        used_pairs.append((clamp(value), weight))
    if not used_pairs:
        return 50.0
    used_weight_sum = sum(w for _, w in used_pairs)
    if used_weight_sum <= 0:
        return 50.0
    raw = sum(v * w for v, w in used_pairs) / used_weight_sum * target_weight_sum
    return clamp(raw)
```

- [ ] **Step 5.4: Run tests to verify all 4 skip tests pass**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py -v`
Expected: 12 tests pass (8 funding helper + 4 skip)

- [ ] **Step 5.5: Run regression on scoring_engine unit tests**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_strategy_decision_rules.py tests/test_strategy_no_microstructure.py -v`
Expected: PASS (existing behavior unchanged because `weighted_score` is untouched)

- [ ] **Step 5.6: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/scoring_engine.py tests/test_v176_funding_regime.py
git commit -m "[v1.7.6] feat(scoring_engine): add weighted_score_skip for funding slot degradation"
```

---

## Task 6: Update weight tables in `market_strategy_signal_config_v17.json`

**Files:**
- Modify: `app/monitoring/configs/market_strategy_signal_config_v17.json` (entire `long_weights`, `long_weights_by_mode`, `short_weights`, `short_weights_by_mode` blocks)
- Create: `tests/test_v176_funding_regime.py` (extend it — or modify an existing snapshot test)

- [ ] **Step 6.1: Write the failing weight-sum tests**

Append to `tests/test_v176_funding_regime.py`:

```python
import pytest

from app.services.strategy_signal.config_loader import (
    DEFAULT_STRATEGY_SIGNAL_CONFIG,
    load_strategy_signal_config,
)


def test_weight_tables_sum_to_one_all_modes():
    """Flat, Trend, Range, Transition × {long, short} all sum to exactly 1.00."""
    config = load_strategy_signal_config()
    long_weights = config["long_weights"]
    long_mode = config["long_weights_by_mode"]
    short_weights = config["short_weights"]
    short_mode = config["short_weights_by_mode"]

    for name, weights in [
        ("long_flat", long_weights),
        ("long_trend", long_mode["trend"]),
        ("long_range", long_mode["range"]),
        ("long_transition", long_mode["transition"]),
        ("short_flat", short_weights),
        ("short_trend", short_mode["trend"]),
        ("short_range", short_mode["range"]),
        ("short_transition", short_mode["transition"]),
    ]:
        s = sum(weights.values())
        assert abs(s - 1.0) < 0.005, f"{name} sum = {s}, expected 1.00"


def test_trend_long_weights_has_three_momentum_frames():
    """Trend mode has 3 distinct momentum sub-scores summing to ~0.17."""
    config = load_strategy_signal_config()
    weights = config["long_weights_by_mode"]["trend"]
    short_w = weights.get("momentum_short", 0)
    mid_w = weights.get("momentum_mid", 0)
    long_w = weights.get("momentum_long", 0)
    assert short_w > 0 and mid_w > 0 and long_w > 0
    assert abs((short_w + mid_w + long_w) - 0.17) < 0.01


def test_transition_long_weights_has_vol_compression_and_momentum_short():
    """Transition keeps vol_compression 0.30, adds momentum_short 0.15."""
    config = load_strategy_signal_config()
    weights = config["long_weights_by_mode"]["transition"]
    assert weights.get("vol_compression") == pytest.approx(0.30)
    assert weights.get("momentum_short") == pytest.approx(0.15)


def test_range_long_weights_keeps_only_momentum_mid():
    """Range mode has momentum_mid 0.10, no momentum_short / momentum_long."""
    config = load_strategy_signal_config()
    weights = config["long_weights_by_mode"]["range"]
    assert weights.get("momentum_mid") == pytest.approx(0.10)
    assert "momentum_short" not in weights or weights["momentum_short"] == 0
    assert "momentum_long" not in weights or weights["momentum_long"] == 0


def test_neutral_weights_unchanged():
    """V1.7.6 leaves V1.7.5 neutral weights alone."""
    config = load_strategy_signal_config()
    nw = config["neutral_weights"]
    assert nw["range_structure"] == 0.25
    assert nw["low_adx"] == 0.20
    assert nw["low_volume_confirmation"] == 0.20
    assert nw["low_directional_spread"] == 0.15
    assert nw["high_conflict_score"] == 0.10
    assert nw["event_uncertainty"] == 0.10
```

- [ ] **Step 6.2: Run tests to verify they fail (current weights lack new keys)**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py::test_weight_tables_sum_to_one_all_modes -v`
Expected: FAIL — current weights still reference `bullish_momentum` and have not adopted `momentum_short/mid/long`. Most assertions on sum=1.00 may fail because new keys are absent.

- [ ] **Step 6.3: Update JSON weight tables**

In `app/monitoring/configs/market_strategy_signal_config_v17.json`, replace:
- `long_weights` (lines 23-31)
- `long_weights_by_mode.trend`, `.range`, `.transition` (lines 33-57)
- `short_weights` (lines 59-67)
- `short_weights_by_mode.trend`, `.range`, `.transition` (lines 69-93)

With the new V1.7.6 weight tables per spec §2.6:

```json
  "long_weights": {
    "mtf_trend_bullish": 0.18,
    "bullish_structure": 0.18,
    "momentum_short": 0.06,
    "momentum_mid": 0.05,
    "momentum_long": 0.05,
    "long_risk_reward": 0.12,
    "regime_fit_long": 0.13,
    "execution_quality": 0.10,
    "range_structure": 0.06,
    "funding_pressure_long": 0.07
  },
  "long_weights_by_mode": {
    "trend": {
      "mtf_trend_bullish": 0.20,
      "bullish_structure": 0.20,
      "momentum_short": 0.06,
      "momentum_mid": 0.06,
      "momentum_long": 0.05,
      "long_risk_reward": 0.13,
      "regime_fit_long": 0.13,
      "execution_quality": 0.10,
      "funding_pressure_long": 0.07
    },
    "range": {
      "mtf_trend_bullish": 0.05,
      "bullish_structure": 0.05,
      "momentum_mid": 0.10,
      "long_risk_reward": 0.10,
      "regime_fit_long": 0.08,
      "execution_quality": 0.05,
      "range_structure": 0.30,
      "low_directional_spread": 0.20,
      "funding_pressure_long": 0.07
    },
    "transition": {
      "vol_compression": 0.30,
      "mtf_trend_bullish": 0.10,
      "bullish_structure": 0.10,
      "momentum_short": 0.15,
      "long_risk_reward": 0.15,
      "regime_fit_long": 0.05,
      "execution_quality": 0.05,
      "funding_pressure_long": 0.10
    }
  },
  "short_weights": {
    "mtf_trend_bearish": 0.18,
    "bearish_structure": 0.18,
    "momentum_short_bearish": 0.06,
    "momentum_mid_bearish": 0.05,
    "momentum_long_bearish": 0.05,
    "short_risk_reward": 0.12,
    "regime_fit_short": 0.13,
    "execution_quality": 0.10,
    "range_structure": 0.06,
    "funding_pressure_short": 0.07
  },
  "short_weights_by_mode": {
    "trend": {
      "mtf_trend_bearish": 0.20,
      "bearish_structure": 0.20,
      "momentum_short_bearish": 0.06,
      "momentum_mid_bearish": 0.06,
      "momentum_long_bearish": 0.05,
      "short_risk_reward": 0.13,
      "regime_fit_short": 0.13,
      "execution_quality": 0.10,
      "funding_pressure_short": 0.07
    },
    "range": {
      "mtf_trend_bearish": 0.05,
      "bearish_structure": 0.05,
      "momentum_mid_bearish": 0.10,
      "short_risk_reward": 0.10,
      "regime_fit_short": 0.08,
      "execution_quality": 0.05,
      "range_structure": 0.30,
      "low_directional_spread": 0.20,
      "funding_pressure_short": 0.07
    },
    "transition": {
      "vol_compression": 0.30,
      "mtf_trend_bearish": 0.10,
      "bearish_structure": 0.10,
      "momentum_short_bearish": 0.15,
      "short_risk_reward": 0.15,
      "regime_fit_short": 0.05,
      "execution_quality": 0.05,
      "funding_pressure_short": 0.10
    }
  },
```

**Arithmetic verification** (each row sums to 1.00):
- Flat long: 0.18+0.18+0.06+0.05+0.05+0.12+0.13+0.10+0.06+0.07 = 1.00 ✓
- Trend long: 0.20+0.20+0.06+0.06+0.05+0.13+0.13+0.10+0.07 = 1.00 ✓
- Range long: 0.05+0.05+0.10+0.10+0.08+0.05+0.30+0.20+0.07 = 1.00 ✓
- Transition long: 0.30+0.10+0.10+0.15+0.15+0.05+0.05+0.10 = 1.00 ✓
- (Same numbers for short side; mirror keys.)

Also ADD to root of JSON (after `model_versions` block, before `timeframe_mapping`):

```json
  "momentum_scale_definitions": {
    "short": { "rsi_lookback": 5, "macd_lookback": 5, "description": "近 5 根 K 线" },
    "mid":   { "rsi_lookback": 20, "macd_lookback": 20, "description": "近 20 根 K 线" },
    "long":  { "rsi_lookback": 60, "macd_lookback": 60, "description": "近 60 根 K 线" }
  },
  "momentum_percentile_window": 90,
  "funding_regime_mapping": {
    "positive_hot":   { "funding_pressure_long": 15, "funding_pressure_short": 85, "funding_crowding_score": 80 },
    "negative_hot":   { "funding_pressure_long": 85, "funding_pressure_short": 15, "funding_crowding_score": 80 },
    "neutral":        { "funding_pressure_long": 50, "funding_pressure_short": 50, "funding_crowding_score": 20 },
    "missing":        { "funding_pressure_long": null, "funding_pressure_short": null, "funding_crowding_score": 0 }
  },
```

- [ ] **Step 6.4: Run weight tests**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py::test_weight_tables_sum_to_one_all_modes tests/test_v176_funding_regime.py::test_trend_long_weights_has_three_momentum_frames tests/test_v176_funding_regime.py::test_transition_long_weights_has_vol_compression_and_momentum_short tests/test_v176_funding_regime.py::test_range_long_weights_keeps_only_momentum_mid tests/test_v176_funding_regime.py::test_neutral_weights_unchanged -v`
Expected: 5 tests pass

- [ ] **Step 6.5: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/monitoring/configs/market_strategy_signal_config_v17.json tests/test_v176_funding_regime.py
git commit -m "[v1.7.6] config: per-mode weight tables + momentum_scale_definitions + funding_regime_mapping"
```

---

## Task 7: Update `DEFAULT_STRATEGY_SIGNAL_CONFIG` in `config_loader.py`

**Files:**
- Modify: `app/services/strategy_signal/config_loader.py:31-50`

- [ ] **Step 7.1: Verify the imports and current DEFAULT_STRATEGY_SIGNAL_CONFIG**

Read `app/services/strategy_signal/config_loader.py:9-50` and confirm.

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -c "from app.services.strategy_signal.config_loader import DEFAULT_STRATEGY_SIGNAL_CONFIG; print(DEFAULT_STRATEGY_SIGNAL_CONFIG['long_weights'])"`
Expected: prints dict with `bullish_momentum: 0.16`

- [ ] **Step 7.2: Update DEFAULT_STRATEGY_SIGNAL_CONFIG**

In `app/services/strategy_signal/config_loader.py:9-50`:

**Replace** lines 31-50 (the `long_weights` and `short_weights` blocks) with the same mirror of Task 6 JSON structure. Use Python dict literals:

```python
    "long_weights": {
        "mtf_trend_bullish": 0.18,
        "bullish_structure": 0.18,
        "momentum_short": 0.06,
        "momentum_mid": 0.05,
        "momentum_long": 0.05,
        "long_risk_reward": 0.12,
        "regime_fit_long": 0.13,
        "execution_quality": 0.10,
        "range_structure": 0.06,
        "funding_pressure_long": 0.07,
    },
    "short_weights": {
        "mtf_trend_bearish": 0.18,
        "bearish_structure": 0.18,
        "momentum_short_bearish": 0.06,
        "momentum_mid_bearish": 0.05,
        "momentum_long_bearish": 0.05,
        "short_risk_reward": 0.12,
        "regime_fit_short": 0.13,
        "execution_quality": 0.10,
        "range_structure": 0.06,
        "funding_pressure_short": 0.07,
    },
```

**Replace** any `bullish_momentum` / `bearish_momentum` references in `DEFAULT_STRATEGY_SIGNAL_CONFIG` long/short_weights with the new keys above.

(If `long_weights_by_mode` exists in DEFAULT, mirror the JSON values from Task 6 step 6.3. Otherwise the per-mode weights come solely from the JSON config — `load_strategy_signal_config` deep-merges.)

- [ ] **Step 7.3: Run tests in tests/test_strategy_signal_snapshot.py + tests/test_v176_funding_regime.py**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py tests/test_strategy_signal_snapshot.py -v`
Expected: All weight-sum tests pass; existing snapshot tests may still pass (transitional state because old momentum keys still emitted by `_feature_components`)

- [ ] **Step 7.4: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/config_loader.py
git commit -m "[v1.7.6] config_loader: align DEFAULT weights with V1.7.6 JSON"
```

---

## Task 8: Migrate consumers to new 6-key momentum API

**Files:**
- Modify: `app/services/strategy_signal/confidence_dimensions.py:137`
- Modify: `app/services/strategy_signal/setup_lifecycle.py` (find any momentum reads)
- Modify: `app/services/strategy_signal/strategy_generator.py` (find any momentum reads)

- [ ] **Step 8.1: Find all reads of old momentum keys in source files**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && grep -n "bullish_momentum\|bearish_momentum\|momentum_source" app/services/strategy_signal/`
Expected output will list file:line refs (snapshot_builder.py is allowed as the producer).

- [ ] **Step 8.2: Update `confidence_dimensions.py:137` (the explicit known location)**

In `app/services/strategy_signal/confidence_dimensions.py`, replace line 137 (the momentum bucket value):

```python
        _bucket(
            "momentum",
            "动量与量能",
            max(sm("momentum_short"), sm("momentum_mid"), sm("momentum_long"),
                sm("momentum_short_bearish"), sm("momentum_mid_bearish"), sm("momentum_long_bearish"),
                sm("volume_confirmation")),
            0.10,
            "趋势加速度、RSI/MACD、成交量确认。",
        ),
```

(Replace `sm("bullish_momentum"), sm("bearish_momentum")` with the 6 new keys.)

- [ ] **Step 8.3: Update `setup_lifecycle.py` if it references momentum keys**

Read any matches found in step 8.1. Replace `bullish_momentum` / `bearish_momentum` reads with `max(momentum_short, momentum_mid, momentum_long)` (or appropriate multi-key max). For each replacement site:

```python
# BEFORE
momentum = snapshot.get("bullish_momentum")
# AFTER
momentum = max(
    snapshot.get("momentum_short", 50.0),
    snapshot.get("momentum_mid", 50.0),
    snapshot.get("momentum_long", 50.0),
)
```

- [ ] **Step 8.4: Update `strategy_generator.py` if it references momentum keys**

Same pattern as 8.3 if grep finds reads. If no reads, skip.

- [ ] **Step 8.5: Run regression tests for migrated modules**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_confidence_dimensions.py tests/test_strategy_setup_lifecycle_v17.py tests/test_strategy_decision_rules.py -v`
Expected: All existing tests still pass (because old keys are still emitted by snapshot_builder; this step only fixes the legacy reads, doesn't remove old keys yet)

- [ ] **Step 8.6: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/confidence_dimensions.py app/services/strategy_signal/setup_lifecycle.py app/services/strategy_signal/strategy_generator.py
git commit -m "[v1.7.6] refactor(consumers): migrate bullish/bearish_momentum reads to 3-frame keys"
```

---

## Task 9: Wire 3-frame RSI/MACD + V2 funding_state in `SnapshotBuilder.build()`

**Files:**
- Modify: `app/services/strategy_signal/snapshot_builder.py` (the `build()` method around line 540-740)

- [ ] **Step 9.1: Locate `build()` and identify indicator sources**

Read `app/services/strategy_signal/snapshot_builder.py:540-740` to find where `rsi`, `macd`, `macd_prev` are currently sourced. They likely come from a call to `_feature_components(indicators=..., structure_overall=..., regime=..., direction_metrics=..., rsi=..., macd=..., macd_prev=..., adx=...)`.

Look for lines like `rsi=` or `rsi_14=` and trace their origin (probably from the `indicators` dict already in scope).

- [ ] **Step 9.2: Compute 3-frame RSI from `indicators` dict or compute on-the-fly**

For V1.7.6, since the indicator_matrix may not yet have multi-frame RSI pre-computed, **strategy**: read the single `rsi_14` available, and pass it as `rsi_short` / `rsi_mid` / `rsi_long` with light dampening. The actual multi-frame RSI computation is a follow-up (out of V1.7.6 scope; documented in spec §7).

Modify the call to `_feature_components` to pass:

```python
        _feature_components(
            indicators=...,
            structure_overall=...,
            regime=...,
            direction_metrics=...,
            rsi_short=single_rsi_value,   # reused rsi_14 from indicators
            rsi_mid=single_rsi_value,
            rsi_long=single_rsi_value,
            macd_short=macd_value,
            macd_mid=macd_value,
            macd_long=macd_value,
            macd_prev_short=macd_prev_value,
            macd_prev_mid=macd_prev_value,
            macd_prev_long=macd_prev_value,
            rsi_history=None,  # will be None; _compute_momentum_at_scale returns (50, 50) for missing history
            funding_state=funding_state,  # passed in (computed below)
        ),
```

- [ ] **Step 9.3: Update `_feature_components` signature**

In `app/services/strategy_signal/snapshot_builder.py:780-797`, replace signature:

```python
def _feature_components(
    *,
    indicators: dict[str, Any],
    structure_overall: dict[str, Any],
    regime: str | None,
    direction_metrics: dict[str, float],
    adx: float,
    rsi_short: float | None,
    rsi_mid: float | None,
    rsi_long: float | None,
    macd_short: float | None,
    macd_mid: float | None,
    macd_long: float | None,
    macd_prev_short: float | None,
    macd_prev_mid: float | None,
    macd_prev_long: float | None,
    rsi_history_short: list[float] | None = None,
    rsi_history_mid: list[float] | None = None,
    rsi_history_long: list[float] | None = None,
    funding_state: str | None = None,
    long_entry: float | None = None,
    long_stop: float | None = None,
    long_tp1: float | None = None,
    short_entry: float | None = None,
    short_stop: float | None = None,
    short_tp1: float | None = None,
) -> dict[str, float]:
```

- [ ] **Step 9.4: Replace inline momentum calculation with 3-frame compute**

In `_feature_components` body (around line 803-811), **DELETE** the existing momentum calculation:

```python
        bullish_momentum = clamp(
            50.0 + max(0.0, rsi - 50.0) * 1.3 + max(0.0, macd - macd_prev) * 3.0
        )
        bearish_momentum = clamp(
            50.0 + max(0.0, 50.0 - rsi) * 1.3 + max(0.0, macd_prev - macd) * 3.0
        )
```

**REPLACE** with:

```python
        # V1.7.6 Layer A: three independent time-frame momentum sub-scores.
        # Each frames differs by RSI/MACD window length and percentile history;
        # in this iteration we reuse the single available RSI(14) across all
        # three frames (history unavailable → neutral percentile behavior).
        short_bullish, short_bearish = _compute_momentum_at_scale(
            rsi=rsi_short,
            macd_hist=macd_short,
            macd_prev=macd_prev_short,
            rsi_history=rsi_history_short,
        )
        mid_bullish, mid_bearish = _compute_momentum_at_scale(
            rsi=rsi_mid,
            macd_hist=macd_mid,
            macd_prev=macd_prev_mid,
            rsi_history=rsi_history_mid,
        )
        long_bullish, long_bearish = _compute_momentum_at_scale(
            rsi=rsi_long,
            macd_hist=macd_long,
            macd_prev=macd_prev_long,
            rsi_history=rsi_history_long,
        )
```

- [ ] **Step 9.5: Update `features` dict — emit 6 new keys, REMOVE old keys**

In the same `features: dict[str, Any] = { ... }` block (around line 831-853):

```python
        features: dict[str, Any] = {
            "mtf_trend_bullish": trend_bullish,
            "mtf_trend_bearish": trend_bearish,
            "mtf_trend_source": "ema+adx+vwap",
            "bullish_structure": struct_bullish,
            "bearish_structure": struct_bearish,
            "structure_source": "structure_overall",
            "regime_fit_long": regime_long,
            "regime_fit_short": regime_short,
            "regime_source": str(regime or structure_overall.get("regime") or "unknown"),
            "range_structure": range_score,
            # V1.7.6: 3-timeframe momentum sub-scores (Layer A)
            "momentum_short": short_bullish,
            "momentum_short_bearish": short_bearish,
            "momentum_mid": mid_bullish,
            "momentum_mid_bearish": mid_bearish,
            "momentum_long": long_bullish,
            "momentum_long_bearish": long_bearish,
            "momentum_source": "rsi[14]+macd_hist,5-20-60-frame-reuse",
            "direction_score_aggregate": direction_metrics["bullish"]
            - direction_metrics["bearish"],
            "low_directional_spread": low_directional_spread,
            "long_risk_reward": long_risk_reward,
            "short_risk_reward": short_risk_reward,
            "risk_reward_source": "entries+stops+tps" if (
                rr_long is not None or rr_short is not None
            ) else "neutral_default",
        }
```

Note: the transitional `short_bullish` et al. block added in Task 3 is REMOVED here (we're consolidating into `_feature_components`'s proper signature now). Also `momentum_source` becomes V1.7.6 with new label.

- [ ] **Step 9.6: Compute and emit funding sub-scores**

In the same `features` dict (or after the existing `range_structure` block), add:

```python
        # V1.7.6 Layer B: funding regime sub-scores from V2 derivatives_regime
        funding_long, funding_short, funding_degraded = _compute_funding_pressure(funding_state)
        features["funding_pressure_long"] = funding_long
        features["funding_pressure_short"] = funding_short
        features["funding_degraded"] = funding_degraded
        features["funding_source"] = "derivatives_regime" if not funding_degraded else "missing"
        features["funding_regime_state"] = funding_state if funding_state is not None else "missing"
```

(Use None for funding_long/short when degraded; `weighted_score_skip` handles None.)

- [ ] **Step 9.7: Update `build()` to pass funding_state and 3-frame params**

In `SnapshotBuilder.build()` (around line 540-740), find where `_feature_components` is called and:
- Extract `funding_state` from the calling context (if V2 service is awaited upstream). In V1.7.6, do NOT add new V2 calls — pass `funding_state=None` for now (degraded path). Real wiring is Task 10.

Update the call site to pass new params with `rsi_short=rsi_mid=rsi_long=<single_rsi>` and `macd_short=macd_mid=macd_long=<single_macd>`.

- [ ] **Step 9.8: Run all V1.7.6 unit tests**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_3timeframe_momentum.py tests/test_v176_funding_regime.py -v`
Expected: All pass

- [ ] **Step 9.9: Run regression on full snapshot unit tests**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_strategy_signal_snapshot.py tests/test_snapshot_feature_sources.py -v`
Expected: All pass (or only the 3-frames-not-yet-emitted assertions fail — read output and fix as needed; the V1.7.6 emit should make the new keys present).

- [ ] **Step 9.10: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/snapshot_builder.py
git commit -m "[v1.7.6] feat(snapshot_builder): emit 6 momentum keys + funding_pressure (Layer A+B)"
```

- [ ] **Step 9.11: Wire `weighted_score_skip` into `DirectionScoringEngine.compute` for funding slots**

In `app/services/strategy_signal/scoring_engine.py` at the `compute` method (around lines 79-80, after `raw_long = weighted_score(long_values, self.config["long_weights"])`):

**Replace** `raw_long` and `raw_short` computation to use `weighted_score_skip` ONLY for the funding slot. Two options:
- (a) Build a `long_minus_funding` weight dict (long_weights minus `funding_pressure_long`), compute with `weighted_score`, then add funding contribution separately via `_funding_pressure × funding_weight` (when not degraded).
- (b) Run `weighted_score_skip(long_values, long_weights)` directly (the funding slot is None when degraded, and the function handles renormalization).

Use option (b) — simpler and matches spec §2.5 semantics:

```python
        # V1.7.6: weighted_score_skip handles degraded funding slots
        # (when V2 derivatives_regime is missing) by skipping None values
        # and renormalizing remaining slots to original weight sum.
        raw_long = weighted_score_skip(long_values, self.config["long_weights"])
        raw_short = weighted_score_skip(short_values, self.config["short_weights"])
```

(Replace existing `weighted_score` calls on lines 79-80 with `weighted_score_skip` for both. Existing `weighted_score` remains in the module for use by other consumers — no removal.)

- [ ] **Step 9.12: Verify the substitution did not regress scoring_engine unit tests**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_strategy_decision_rules.py tests/test_strategy_no_microstructure.py tests/test_v176_funding_regime.py -v`
Expected: All pass. Existing tests use `"funding_pressure_long": 50` or similar fixed values (not None) so renormalization has no effect → output identical to old `weighted_score`.

---

## Task 10: Replace hardcoded `funding_crowding_score: 0` at `snapshot_builder.py:710`

**Files:**
- Modify: `app/services/strategy_signal/snapshot_builder.py:710`

- [ ] **Step 10.1: Locate the line**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && grep -n '"funding_crowding_score"' app/services/strategy_signal/snapshot_builder.py`
Expected: line 710 (the same line identified in the V1.7.6 spec)

- [ ] **Step 10.2: Read the surrounding context**

Read `app/services/strategy_signal/snapshot_builder.py:700-720` and identify the variable in scope that can supply the `funding_state` to `_remap_funding_crowding`. Likely `funding_state` from a unified_service call, or absent (degraded).

- [ ] **Step 10.3: Replace the hardcoded `0`**

Change line 710 from:

```python
                "funding_crowding_score": 0,
```

To:

```python
                "funding_crowding_score": _remap_funding_crowding(funding_state),
```

If `funding_state` is not in scope at this exact line, **add a parameter** to the calling function (e.g. `build_snapshot(...)` or whatever encloses this dict construction) and ensure the value is either a real V2 funding_state or None.

- [ ] **Step 10.4: Write a test verifying funding_crowding_score is no longer always 0**

Append to `tests/test_v176_funding_regime.py`:

```python
def test_remap_funding_crowding_replace_at_snapshot_py710():
    """Sanity check: _remap_funding_crowding maps positive_hot → 80.0 (not 0)."""
    assert _remap_funding_crowding("positive_hot") == 80.0
    assert _remap_funding_crowding("neutral") == 20.0
    assert _remap_funding_crowding(None) == 0.0  # preserve dead-zero behavior in degraded path
```

- [ ] **Step 10.5: Run tests**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_v176_funding_regime.py -v`
Expected: All pass

- [ ] **Step 10.6: Run scoring_engine penalty regression**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/test_strategy_decision_rules.py -v`
Expected: Pass (existing tests use `"funding_crowding_score": 0` fixtures, which still maps to degraded/None path; no behavior change)

- [ ] **Step 10.7: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add app/services/strategy_signal/snapshot_builder.py
git commit -m "[v1.7.6] feat(snapshot_builder): reconnect funding_crowding_score from V2 mapping"
```

---

## Task 11: Update test fixtures + add `test_old_momentum_keys_deleted` cascade test

**Files:**
- Modify: `tests/test_strategy_decision_rules.py`
- Modify: `tests/test_strategy_no_microstructure.py`
- Modify: `tests/test_strategy_signal_snapshot.py`
- Modify: `tests/test_strategy_setup_lifecycle_v17.py`
- Modify: `tests/test_snapshot_feature_sources.py`
- Modify: `tests/test_confidence_dimensions.py`

- [ ] **Step 11.1: Find old momentum references in test fixtures**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && grep -n "bullish_momentum\|bearish_momentum\|momentum_source" tests/*.py`
Expected output lists file:line refs

- [ ] **Step 11.2: Replace fixture dict entries**

For each match in test fixtures (e.g., `tests/test_strategy_decision_rules.py`), replace patterns like:

```python
        "bullish_momentum": 60.0,
        "bearish_momentum": 40.0,
```

With:

```python
        "momentum_short": 60.0,
        "momentum_mid": 55.0,
        "momentum_long": 50.0,
        "momentum_short_bearish": 40.0,
        "momentum_mid_bearish": 45.0,
        "momentum_long_bearish": 50.0,
```

(Use any consistent numbers that satisfy the test's existing assertions; if a test uses 60 / 40 asymmetric pair, mirror that across the 6 keys so the existing long_score / short_score assertions still hold.)

- [ ] **Step 11.3: Add `test_old_momentum_keys_deleted` cascade test**

Append to `tests/test_snapshot_feature_sources.py`:

```python
def test_old_momentum_keys_deleted_from_snapshot() -> None:
    """V1.7.6 cascade: bullish_momentum / bearish_momentum / momentum_source removed."""
    components = StrategySnapshotBuilder._feature_components(
        indicators={"ema_20": 110, "adx_14": 25},
        structure_overall={"bias": "neutral"},
        regime="trend",
        direction_metrics={"bullish": 60.0, "bearish": 40.0},
        rsi_short=58.0, rsi_mid=58.0, rsi_long=58.0,
        macd_short=1.0, macd_mid=1.0, macd_long=1.0,
        macd_prev_short=0.5, macd_prev_mid=0.5, macd_prev_long=0.5,
        adx=25.0,
    )
    assert "bullish_momentum" not in components
    assert "bearish_momentum" not in components
    assert "momentum_source" not in components  # V1.7.6 keeps a new momentum_source label; remove check if intentional
    # New keys present:
    for key in (
        "momentum_short", "momentum_short_bearish",
        "momentum_mid",   "momentum_mid_bearish",
        "momentum_long",  "momentum_long_bearish",
    ):
        assert key in components
```

If `momentum_source` IS intentionally retained as a V1.7.6 label (per Step 9.5), remove that assertion. The other two keys must be deleted.

- [ ] **Step 11.4: Augment `test_feature_components_keep_momentum_independent_from_direction_score`**

Update the test (around line 157-185) to call `_feature_components` with the new 11+ keyword signature. Pass `rsi_short`, `rsi_mid`, `rsi_long` etc. Ensure the assertion still checks 6 momentum keys.

- [ ] **Step 11.5: Run all modified test files**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
python -m pytest \
  tests/test_strategy_decision_rules.py \
  tests/test_strategy_no_microstructure.py \
  tests/test_strategy_signal_snapshot.py \
  tests/test_strategy_setup_lifecycle_v17.py \
  tests/test_snapshot_feature_sources.py \
  tests/test_confidence_dimensions.py \
  tests/test_v176_3timeframe_momentum.py \
  tests/test_v176_funding_regime.py \
  -v
```
Expected: All pass

- [ ] **Step 11.6: Commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git add tests/
git commit -m "[v1.7.6] test: migrate fixtures to 6-frame momentum + add old-keys-deleted cascade"
```

---

## Task 12: Final regression + sync portable bundle

**Files:**
- Verify: full pytest suite
- Mirror: `dist/portable_bundle/...` rebuild (if applicable)

- [ ] **Step 12.1: Full project test run**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/ -v --tb=short 2>&1 | tail -100`
Expected: All tests pass (or, only known-fail tests fail; fix any new failures introduced by V1.7.6).

- [ ] **Step 12.2: Investigate any new failures**

For each failure, identify which V1.7.6 task introduced it. Common issues:
- Old consumer still reads `bullish_momentum` directly (Task 8 should have caught it) → fix in source
- Test fixture has `"momentum_source": "..."` (old label) → update to new 6-key dict
- Config has lingering `"bullish_momentum"` key in `long_weights_by_mode` (JSON missing update) → fix JSON

- [ ] **Step 12.3: Update docs / changelog (optional but recommended)**

Edit `docs/CHANGELOG.md` and add a V1.7.6 entry similar to V1.7.5's:

```markdown
### V1.7.6 — 2026-07-06 — 3-TF Momentum + Funding Regime Sub-Score

- 替换单尺度动量（`bullish_momentum`/`bearish_momentum`）为 **3 个独立时间尺度动量**（momentum_short/mid/long 各 5/20/60 K 线）。
- 新增 **funding_pressure_long / funding_pressure_short 子分**，从 V2 `derivatives_regime.funding_state` 派生。
- 重连 `funding_crowding_score`（之前硬编码 0），现在真正由 V2 funding_state 驱动 `scoring_engine._long_penalty`。
- `weighted_score_skip` 支持 funding slot 缺失时的归一化降级。
- Per-mode 权重表重构：trend/range/transition 3 模式 × {long, short}，每个 sum=1.00。
```

- [ ] **Step 12.4: Mirror to portable bundle (if applicable)**

If the project maintains `dist/portable_bundle/` as a mirror of source:
```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
# Mirror src + tests + config (skip __pycache__, .pytest_cache)
```

(Use whatever copy / sync command applies — check existing V1.7.5 commit history for the actual command used by the team.)

- [ ] **Step 12.5: Run full regression one more time after mirror**

Run: `cd "E:/Personal/Research/Crypto Investing System/trading-system-codex" && python -m pytest tests/ -v --tb=short 2>&1 | tail -50`
Expected: All pass

- [ ] **Step 12.6: Final summary commit**

```bash
cd "E:/Personal/Research/Crypto Investing System/trading-system-codex"
git log --oneline main -20
git status --short
git -c user.name="Lemuel Castiel" -c user.email="lemuel@example.com" commit --allow-empty -m "[v1.7.6] release: 3-TF momentum + funding regime sub-score (12 tasks, $(git log main --oneline | wc -l) commits)"
git push origin main  # ONLY IF USER EXPLICITLY ASKS — DO NOT AUTO-PUSH
```

> **Push reminder:** Per user constraint, **never** push to GitHub autonomously. The user pushes via `git push origin main` themselves.

- [ ] **Step 12.7: Pause and report**

Report the final V1.7.6 commit list to the user. Stop; wait for user push.

---

## Self-Review (per writing-plans skill)

**Spec coverage cross-check:**
- ✅ Layer A 3-TF momentum → Tasks 2-3, 9, 11
- ✅ Layer B funding sub-score → Tasks 4, 5, 9
- ✅ Layer C reconnect `funding_crowding_score` → Task 10
- ✅ Per-mode weight tables → Task 6-7
- ✅ weighted_score_skip → Task 5
- ✅ Caller cascade (5 src + 6 test + 1 config + 2 build) → Tasks 8, 11, 12.4
- ✅ 26+ test cases → all tasks (8 in Task 2 + 7 in Task 4 + 4 in Task 5 + 5 in Task 6 + cascade in Task 11)
- ✅ V1.7.5 multiplicative gate preserved → Task 6 explicitly keeps `vol_compression: 0.30` in transition mode
- ✅ V1.7.5 risk_reward_score_ev preserved → untouched across all tasks
- ✅ neutral weights unchanged → Task 6 explicit test

**Placeholder scan:** None found.

**Type/signature consistency:**
- `_percentile_rank(history: list[float] | None, current: float | None) -> float` (Task 1) — used by Task 2's `_compute_momentum_at_scale`
- `_compute_momentum_at_scale(...) -> tuple[float, float]` (Task 2) — used by Task 9's `_feature_components`
- `_feature_components` signature grows from 8 kwargs to 11+ (Task 9.3) — checked against Task 9.7 callers
- `weighted_score_skip(...) -> float` (Task 5) — wired into `DirectionScoringEngine.compute` at Task 9.11 ✅ (was initially flagged as gap, now fixed inline)

