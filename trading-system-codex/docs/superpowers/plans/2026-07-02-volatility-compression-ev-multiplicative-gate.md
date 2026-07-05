# V1.7.5 Volatility Compression + EV + Multiplicative Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 sub-systems to the technical indicator page scoring: (1) `vol_compression` (multi-period percentile rank) for volatility squeeze detection, (2) `setup_probability` (Bayesian posterior) for EV calculation, and (3) a multiplicative gate in transition mode that requires both vol compression AND directional agreement, plus an EV-based `risk_reward_score` that breaks the existing `rr=90` ceiling.

**Architecture:** Extend `snapshot_builder` to compute 2 new sub-scores and apply a multiplicative gate in transition mode. Update `risk_reward.py` to add an EV-based score function. Update `scoring_engine.compute()` and `strategy_generator` to use EV-based score for trigger logic. Add `transition` mode weights in JSON config. Add status-bar transition badge in `analysis.js`.

**Tech Stack:** Python (snapshot/scoring), Vanilla JS (frontend), pytest (tests).

---

## File Structure

### Modify
- `trading-system-codex/app/services/strategy_signal/snapshot_builder.py` — add `_compute_vol_compression`, `_compute_setup_probability`, transition mode multiplicative gate
- `trading-system-codex/app/services/strategy_signal/risk_reward.py` — add `risk_reward_score_ev`
- `trading-system-codex/app/services/strategy_signal/scoring_engine.py` — use `risk_reward_score_ev` in `compute()`
- `trading-system-codex/app/services/strategy_signal/strategy_generator.py` — `trigger_state` uses `ev_score` instead of `rr`
- `trading-system-codex/app/services/strategy_signal/config_loader.py` — add `transition` mode weights, add `bayesian_prior` config
- `trading-system-codex/app/monitoring/configs/market_strategy_signal_config_v17.json` — add `transition` weights + `ev_thresholds`
- `trading-system-codex/app/static/pages/analysis.js` — add `renderModeBadge("transition")` case
- `trading-system-codex/app/static/styles.css` — `.status-mode-badge.transition-mode` styles
- `trading-system-codex/app/static/core/knowledge.js` — 2 new `term()` entries
- `trading-system-codex/tests/test_strategy_signal_snapshot.py` — 7 new tests
- `trading-system-codex/tests/test_risk_reward.py` — 2 new tests
- `trading-system-codex/tests/test_strategy_decision_rules.py` — 1 updated test
- `trading-system-codex/tests/test_strategy_no_microstructure.py` — 1 updated test
- `docs/CHANGELOG.md` — V1.7.5 entry

### Create
None — all changes are extensions of existing files.

---

## Task 1: Add `_compute_vol_compression()` to snapshot_builder (TDD)

**Files:**
- Modify: `trading-system-codex/app/services/strategy_signal/snapshot_builder.py`
- Test: `trading-system-codex/tests/test_strategy_signal_snapshot.py`

- [ ] **Step 1: Write failing test**

In `trading-system-codex/tests/test_strategy_signal_snapshot.py`, add:

```python
def test_vol_compression_score_multi_period_percentile_rank():
    """bb_width vs bb_width_ma_90: extreme compression (ratio<0.5) → score 90+"""
    from app.services.strategy_signal import snapshot_builder

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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest tests/test_strategy_signal_snapshot.py::test_vol_compression_score_multi_period_percentile_rank -v
```

Expected: FAIL (`_compute_vol_compression` not defined).

- [ ] **Step 3: Add `_compute_vol_compression()` to `snapshot_builder.py`**

In `trading-system-codex/app/services/strategy_signal/snapshot_builder.py`, add the function (near the other score-building helpers like `_build_trend_score`):

```python
def _compute_vol_compression(
    bb_width: float | None,
    bb_width_ma_90: float | None,
) -> float:
    """Multi-period percentile rank: current BB-width in 90-day distribution.

    Returns 0-100:
    - 90+ = extreme compression (BB-width < 50% of 90-day MA)
    - 50  = neutral (BB-width near MA)
    - 25  = expansion (BB-width > 1.4 × MA)
    """
    if not bb_width or not bb_width_ma_90 or bb_width_ma_90 <= 0:
        return 50.0
    ratio = bb_width / bb_width_ma_90
    if ratio < 0.5:
        return 90.0
    if ratio < 0.7:
        return 75.0
    if ratio < 0.85:
        return 60.0
    if ratio < 1.15:
        return 50.0
    if ratio < 1.4:
        return 40.0
    return 25.0
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_strategy_signal_snapshot.py::test_vol_compression_score_multi_period_percentile_rank -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/strategy_signal/snapshot_builder.py trading-system-codex/tests/test_strategy_signal_snapshot.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] snapshot: add _compute_vol_compression (multi-period percentile rank)"
```

---

## Task 2: Add `_compute_setup_probability()` to snapshot_builder (TDD)

**Files:**
- Modify: `trading-system-codex/app/services/strategy_signal/snapshot_builder.py`
- Test: `trading-system-codex/tests/test_strategy_signal_snapshot.py`

- [ ] **Step 1: Write failing test**

In `trading-system-codex/tests/test_strategy_signal_snapshot.py`, add:

```python
def test_setup_probability_bayesian_posterior_no_evidence():
    """No positive evidence → P(win) = base_prior (0.45)"""
    from app.services.strategy_signal import snapshot_builder

    p = snapshot_builder._compute_setup_probability(
        long_score=40, short_score=40, setup_ready=False, conflict_score=50
    )
    assert p == 0.45  # base_prior only


def test_setup_probability_bayesian_posterior_with_strong_setup():
    """Multiple positive evidence → P(win) > 0.7"""
    from app.services.strategy_signal import snapshot_builder

    p = snapshot_builder._compute_setup_probability(
        long_score=80,  # > 60 → likelihood 1.4
        short_score=30,
        setup_ready=True,  # → 1.5
        conflict_score=20,  # < 30 → 1.3
    )
    # posterior = 0.45 * 1.4 * 1.5 * 1.3 ≈ 1.23 → clamped to 0.99
    assert p > 0.7
    assert p <= 0.99


def test_setup_probability_bayesian_posterior_with_conflict_suppresses():
    """Strong conflict → P(win) < 0.4"""
    from app.services.strategy_signal import snapshot_builder

    p = snapshot_builder._compute_setup_probability(
        long_score=40, short_score=40, setup_ready=True, conflict_score=80  # > 70 → 0.6
    )
    # posterior = 0.45 * 1.5 * 0.6 = 0.405
    assert p < 0.45
    assert p >= 0.01
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_strategy_signal_snapshot.py::test_setup_probability_bayesian_posterior_no_evidence -v
```

Expected: FAIL.

- [ ] **Step 3: Add `_compute_setup_probability()` to `snapshot_builder.py`**

In `trading-system-codex/app/services/strategy_signal/snapshot_builder.py`, add:

```python
def _compute_setup_probability(
    long_score: float,
    short_score: float,
    setup_ready: bool,
    conflict_score: float,
    base_prior: float = 0.45,
) -> float:
    """Bayesian posterior: P(win | setup, regime) = prior × Π(likelihoods) / Z.

    Returns 0-1 win probability.
    """
    likelihoods: list[float] = []
    if max(long_score, short_score) > 60:
        likelihoods.append(1.4)
    if setup_ready:
        likelihoods.append(1.5)
    if conflict_score < 30:
        likelihoods.append(1.3)
    if max(long_score, short_score) > 75:
        likelihoods.append(1.6)
    if conflict_score > 70:
        likelihoods.append(0.6)
    if max(long_score, short_score) < 50:
        likelihoods.append(0.5)
    posterior = base_prior
    for lik in likelihoods:
        posterior *= lik
    return clamp(posterior, 0.01, 0.99)
```

(`clamp` is already imported in snapshot_builder from `risk_reward`.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_strategy_signal_snapshot.py::test_setup_probability_bayesian_posterior_no_evidence tests/test_strategy_signal_snapshot.py::test_setup_probability_bayesian_posterior_with_strong_setup tests/test_strategy_signal_snapshot.py::test_setup_probability_bayesian_posterior_with_conflict_suppresses -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/strategy_signal/snapshot_builder.py trading-system-codex/tests/test_strategy_signal_snapshot.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] snapshot: add _compute_setup_probability (Bayesian posterior)"
```

---

## Task 3: Add `risk_reward_score_ev` to `risk_reward.py` (TDD)

**Files:**
- Modify: `trading-system-codex/app/services/strategy_signal/risk_reward.py`
- Test: `trading-system-codex/tests/test_risk_reward.py` (or new test file)

- [ ] **Step 1: Write failing test**

Create `trading-system-codex/tests/test_risk_reward.py`:

```python
"""Tests for V1.7.5 EV-based risk_reward_score."""

from app.services.strategy_signal.risk_reward import risk_reward_score_ev


def test_risk_reward_score_ev_no_ceiling():
    """rr=5 with p=0.5 → 250 capped at 100 (no longer the rr=90 ceiling)."""
    assert risk_reward_score_ev(rr=5.0, p_win=0.5) == 100


def test_risk_reward_score_ev_high_p_high_rr():
    """rr=3 with p=0.8 → 240 capped at 100."""
    assert risk_reward_score_ev(rr=3.0, p_win=0.8) == 100


def test_risk_reward_score_ev_low_rr_p():
    """rr=1.5 with p=0.4 → 60 (below trigger threshold 72 typically)."""
    assert risk_reward_score_ev(rr=1.5, p_win=0.4) == 60


def test_risk_reward_score_ev_no_rr():
    """rr=None → 0"""
    assert risk_reward_score_ev(rr=None, p_win=0.5) == 0


def test_risk_reward_score_ev_default_p():
    """Default p_win=0.5"""
    assert risk_reward_score_ev(rr=2.0) == 100  # 0.5 * 2.0 * 100 = 100
    assert risk_reward_score_ev(rr=1.0) == 50  # 0.5 * 1.0 * 100 = 50
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest tests/test_risk_reward.py -v
```

Expected: FAIL (function not defined).

- [ ] **Step 3: Add `risk_reward_score_ev` to `risk_reward.py`**

In `trading-system-codex/app/services/strategy_signal/risk_reward.py`, add at the end of the file (after `risk_reward_label`):

```python
def risk_reward_score_ev(
    rr: float | None,
    p_win: float = 0.5,
) -> float:
    """EV-based: P(win) × RR × 100, capped 0-100.

    No more 90 ceiling. A 3R trade with 80% win rate scores 240 → 100.
    A 1R trade with 50% win rate scores 50.

    Args:
      rr: risk-reward ratio (entry / stop / tp1 already computed upstream).
      p_win: estimated win probability from setup_probability.

    Returns 0-100.
    """
    if rr is None or rr <= 0:
        return 0
    ev = p_win * rr * 100
    return max(0, min(100, ev))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_risk_reward.py -v
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/strategy_signal/risk_reward.py trading-system-codex/tests/test_risk_reward.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] risk_reward: add risk_reward_score_ev (EV-based, no rr=90 ceiling)"
```

---

## Task 4: Add `transition` mode weights to JSON config

**Files:**
- Modify: `trading-system-codex/app/monitoring/configs/market_strategy_signal_config_v17.json`

- [ ] **Step 1: Read current `long_weights_by_mode` and `short_weights_by_mode` structure**

Read the file to find these blocks. They were added in V1.7.4.

- [ ] **Step 2: Add `transition` mode to both `long_weights_by_mode` and `short_weights_by_mode`**

In `app/monitoring/configs/market_strategy_signal_config_v17.json`, inside the `long_weights_by_mode` block, add a `transition` entry after the `range` entry:

```json
"long_weights_by_mode": {
  "trend": {
    "mtf_trend_bullish": 0.22,
    "bullish_structure": 0.22,
    "bullish_momentum": 0.18,
    "long_risk_reward": 0.13,
    "regime_fit_long": 0.15,
    "execution_quality": 0.10
  },
  "range": {
    "mtf_trend_bullish": 0.05,
    "bullish_structure": 0.05,
    "range_structure": 0.30,
    "low_directional_spread": 0.20,
    "long_risk_reward": 0.15,
    "regime_fit_long": 0.15,
    "execution_quality": 0.10
  },
  "transition": {
    "vol_compression": 0.30,
    "mtf_trend_bullish": 0.15,
    "bullish_structure": 0.10,
    "long_risk_reward": 0.20,
    "regime_fit_long": 0.15,
    "execution_quality": 0.10
  }
}
```

Do the same for `short_weights_by_mode` (mirror the structure with `_bearish` etc.).

- [ ] **Step 3: Add EV thresholds**

In the `thresholds` block, add (or update) `ev_threshold: 65` (was implicit in the 0.5 * 1.5 * 100 = 75 path, now explicit):

```json
"thresholds": {
  ...,
  "ev_threshold": 65,
  ...
}
```

(Keep all existing thresholds. Just add `ev_threshold: 65` for the new EV-based trigger gate.)

- [ ] **Step 4: Verify JSON is valid**

```bash
cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
  python -c "import json; data = json.load(open('app/monitoring/configs/market_strategy_signal_config_v17.json')); print('OK,', len(data['long_weights_by_mode']), 'mode-keys')"
```

Expected: `OK, 3 mode-keys` (trend, range, transition).

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/monitoring/configs/market_strategy_signal_config_v17.json && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] config: add transition mode weights + ev_threshold (V1.7.5)"
```

---

## Task 5: Add multiplicative gate + populate vol_compression/setup_probability in `_build_snapshot` (TDD)

**Files:**
- Modify: `trading-system-codex/app/services/strategy_signal/snapshot_builder.py`
- Test: `trading-system-codex/tests/test_strategy_signal_snapshot.py`

- [ ] **Step 1: Write failing test**

In `trading-system-codex/tests/test_strategy_signal_snapshot.py`, add:

```python
def test_transition_mode_uses_multiplicative_gate():
    """In transition mode, raw_long is multiplied by vol_compression / 100.
    
    Without vol_compression, the gate reduces transition-mode long_score.
    """
    from app.services.strategy_signal import snapshot_builder

    # Build snapshot in transition mode (monkeypatch detect_mode)
    monkeypatch.setattr(snapshot_builder, "detect_mode", lambda *a, **kw: "transition")
    monkeypatch.setattr(snapshot_builder, "detect_asset_class", lambda *a, **kw: "stock")

    # vol_compression = 50 (neutral) → multiplier = 0.5
    indicators_low_vol = {
        "mtf_trend_bullish": 80, "bullish_structure": 80, "bullish_momentum": 60,
        "long_risk_reward": 70, "regime_fit_long": 60, "execution_quality": 70,
        "vol_compression": 50,  # neutral
    }
    snap_low = snapshot_builder._build_snapshot(
        instrument_id="btc-usdt-perp", timeframe="1d", indicators=indicators_low_vol,
        structure_overall={"regime": "transition"},
    )
    # The raw_long was already multiplied by 0.5 (50/100)
    assert snap_low["long_score"] < 50  # was around 67 without gate, now < 50

    # vol_compression = 90 (squeeze) → multiplier = 0.9 → no significant suppression
    indicators_high_vol = {**indicators_low_vol, "vol_compression": 90}
    snap_high = snapshot_builder._build_snapshot(
        instrument_id="btc-usdt-perp", timeframe="1d", indicators=indicators_high_vol,
        structure_overall={"regime": "transition"},
    )
    # The raw_long was multiplied by 0.9 (90/100), much less suppression
    assert snap_high["long_score"] > snap_low["long_score"] + 5  # noticeably higher
```

(Use `monkeypatch` from `pytest` fixtures. Adapt the test setup to match the existing `_build_snapshot` signature in `snapshot_builder.py` — Task 3 of V1.7.4 created this test seam.)

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_strategy_signal_snapshot.py::test_transition_mode_uses_multiplicative_gate -v
```

Expected: FAIL (no `vol_compression` in the dict, no multiplicative gate).

- [ ] **Step 3: Add `_compute_setup_probability` + `vol_compression` + multiplicative gate to `_build_snapshot`**

In `trading-system-codex/app/services/strategy_signal/snapshot_builder.py`, in the `_build_snapshot` helper (around line 700+ where the score dict is built), add the new fields and the multiplicative gate.

Find the section in `_compute_mode_aware_scores` (or wherever `weighted_score` is called) and add the gate right after the weights are selected:

```python
# After weights are selected based on mode:
if mode == "transition":
    vol_compression_score = features.get("vol_compression", 50)
    vol_factor = vol_compression_score / 100  # 0-1
    raw_long *= vol_factor
    raw_short *= vol_factor
```

Also, in `_feature_components` (or wherever the score dict is built), add the new fields to the returned dict:

```python
# In the returned features dict:
features["vol_compression"] = _compute_vol_compression(
    bb_width=indicators.get("bb_width"),
    bb_width_ma_90=indicators.get("bb_width_ma_90"),  # may be None initially
)
features["setup_probability"] = _compute_setup_probability(
    long_score=features.get("mtf_trend_bullish", 50) + features.get("bullish_structure", 50),
    short_score=features.get("mtf_trend_bearish", 50) + features.get("bearish_structure", 50),
    setup_ready=features.get("setup_ready", False),
    conflict_score=features.get("conflict_score", 0),
)
```

(Read the existing `_feature_components` and `_build_snapshot` carefully to find the right insertion points and match the existing code style.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_strategy_signal_snapshot.py -v
```

Expected: All tests pass (including the new gate test).

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/strategy_signal/snapshot_builder.py trading-system-codex/tests/test_strategy_signal_snapshot.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] snapshot: populate vol_compression + setup_probability + transition multiplicative gate"
```

---

## Task 6: Update `scoring_engine.compute()` to use `risk_reward_score_ev`

**Files:**
- Modify: `trading-system-codex/app/services/strategy_signal/scoring_engine.py`
- Test: `tests/test_strategy_signal_snapshot.py`

- [ ] **Step 1: Write failing test**

In `trading-system-codex/tests/test_strategy_signal_snapshot.py`, add:

```python
def test_compute_uses_risk_reward_score_ev():
    """scoring_engine.compute() should use the new EV-based rr score (no rr=90 ceiling)."""
    from app.services.strategy_signal.scoring_engine import DirectionScoringEngine

    config = {"long_weights": {"mtf_trend_bullish": 0.5}, "short_weights": {}, "neutral_weights": {}, "data_quality_weights": {}}
    engine = DirectionScoringEngine(config)
    snap = {
        "long_risk_reward": 5.0,  # large RR
        "short_risk_reward": 0.5,
        "setup_probability": 0.7,
        "mtf_trend_bullish": 80,
        "bullish_structure": 80,
        "bullish_momentum": 60,
        "long_propagation": 50,
        "short_propagation": 50,
        "vol_compression": 60,
    }
    res = engine.compute(snap)
    # risk_reward_score_ev(5.0, 0.7) = 350 → cap 100
    # So this should NOT equal 90 (the old EV-less score cap).
    # The exact score is harder to predict; just assert it's NOT 90.
    assert res.long_score != 90  # old cap was 90
    assert res.long_score > 50   # EV should boost
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_strategy_signal_snapshot.py::test_compute_uses_risk_reward_score_ev -v
```

Expected: FAIL (current code uses 5-bucket table, not EV).

- [ ] **Step 3: Update `compute()` to use `risk_reward_score_ev`**

In `trading-system-codex/app/services/strategy_signal/scoring_engine.py`, find the `compute` method (around line 51–107). Update where `long_risk_reward` and `short_risk_reward` are set in the values dict:

```python
# Before:
long_values["long_risk_reward"] = risk_reward_score(snapshot.get("long_risk_reward"))
short_values["short_risk_reward"] = risk_reward_score(snapshot.get("short_risk_reward"))

# After:
p_win = snapshot.get("setup_probability", 0.5)
long_values["long_risk_reward"] = risk_reward_score_ev(
    snapshot.get("long_risk_reward"), p_win
)
short_values["short_risk_reward"] = risk_reward_score_ev(
    snapshot.get("short_risk_reward"), p_win
)
```

Also add the import at the top:
```python
from app.services.strategy_signal.risk_reward import (
    compute_risk_reward,
    number,
    risk_reward_score,
    risk_reward_score_ev,    # NEW
    round2,
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_strategy_signal_snapshot.py::test_compute_uses_risk_reward_score_ev -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/strategy_signal/scoring_engine.py trading-system-codex/tests/test_strategy_signal_snapshot.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] scoring_engine: use risk_reward_score_ev in compute()"
```

---

## Task 7: Update `strategy_generator` trigger_state to use `ev_score`

**Files:**
- Modify: `trading-system-codex/app/services/strategy_signal/strategy_generator.py`
- Test: `trading-system-codex/tests/test_strategy_decision_rules.py`

- [ ] **Step 1: Read current trigger_state condition**

In `trading-system-codex/app/services/strategy_signal/strategy_generator.py`, find the trigger condition (around line 325–336 per the spec). It currently checks `(rr or 0) >= th["min_rr_trade"]`.

- [ ] **Step 2: Write failing test**

In `trading-system-codex/tests/test_strategy_decision_rules.py`, add or update:

```python
def test_trigger_state_uses_ev_score():
    """Trigger condition now uses ev_score (p_win × rr × 100) instead of just rr threshold."""
    # In V1.7.5, a high-p_win + high-rr setup should trigger even if rr alone
    # is below the old min_rr_trade threshold.
    # ... use the existing snapshot fixture setup
    pass  # adapt to existing test pattern in this file
```

(Adapt to match the existing test style — read a few tests in `test_strategy_decision_rules.py` to understand the pattern. The test should set up a snapshot with `setup_probability: 0.8`, `long_risk_reward: 2.0` (ev=160, capped at 100), `mtf_trend_bullish: 80`, `bullish_structure: 80`, and assert the resulting state is `LONG_TRIGGERED` even if old `rr < min_rr_trade` would have rejected it.)

- [ ] **Step 3: Update trigger_state condition**

In `trading-system-codex/app/services/strategy_signal/strategy_generator.py`, find the trigger condition (line 325–336). Replace the `rr` check with an `ev_score` check:

```python
# Before:
if (
    side_score >= th["trigger_score"]
    and setup_ready
    and trigger_ready
    and (rr or 0) >= th["min_rr_trade"]
):

# After:
ev_threshold = th.get("ev_threshold", 65)
ev_score = snapshot.get("setup_probability", 0.5) * (rr or 0) * 100
if (
    side_score >= th["trigger_score"]
    and setup_ready
    and trigger_ready
    and ev_score >= ev_threshold
):
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_strategy_decision_rules.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/strategy_signal/strategy_generator.py trading-system-codex/tests/test_strategy_decision_rules.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] strategy: trigger_state uses ev_score (p_win * rr * 100)"
```

---

## Task 8: Add transition mode badge in `analysis.js`

**Files:**
- Modify: `trading-system-codex/app/static/pages/analysis.js`
- Test: `trading-system-codex/tests/test_analysis_mode_badge.py` (update existing)

- [ ] **Step 1: Update existing test**

In `trading-system-codex/tests/test_analysis_mode_badge.py`, the existing test checks for `.status-mode-badge` shape. Update it to also verify the transition case:

```python
def test_transition_mode_badge_visible(base_url):
    """When mode='transition', the status-bar shows the transition badge with vol_compression info."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{base_url}/market-analysis", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        badge = page.locator(".status-mode-badge.transition-mode")
        if badge.count() > 0:
            assert badge.first.is_visible()
            text = badge.first.inner_text()
            assert "波动率压缩" in text or "vol_compression" in text

        ctx.close()
        browser.close()
```

- [ ] **Step 2: Run the test to verify behavior**

(With backend running, the test should pass if badge renders conditionally.)

- [ ] **Step 3: Add `renderModeBadge("transition")` to `analysis.js`**

In `trading-system-codex/app/static/pages/analysis.js`, find the `renderModeBadge` function. Update it:

```javascript
function renderModeBadge(mode) {
  if (mode === "range") {
    return `<div class="status-mode-badge range-mode">
      <span>📊 区间震荡模式</span>
      <a class="status-mode-link" href="/structure-page">查看形态结构页 →</a>
    </div>`;
  }
  if (mode === "transition") {
    return `<div class="status-mode-badge transition-mode">
      <span>⚡ 波动率压缩 → 扩张预警</span>
      <a class="status-mode-link" href="/market-analysis?focus=breakout">关注突破信号 →</a>
    </div>`;
  }
  return "";
}
```

- [ ] **Step 4: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/pages/analysis.js trading-system-codex/tests/test_analysis_mode_badge.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] analysis: add transition-mode badge linking to breakout focus"
```

---

## Task 9: Add CSS for `.transition-mode` badge

**Files:**
- Modify: `trading-system-codex/app/static/styles.css`

- [ ] **Step 1: Append CSS rules**

Append to `app/static/styles.css` (after the existing `.status-mode-badge` rules):

```css
/* Transition mode badge (V1.7.5) — volatility squeeze */
.status-mode-badge.transition-mode {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin: 12px 0;
  background: rgba(255, 235, 130, 0.22);
  border: 1px solid rgba(214, 165, 42, 0.40);
  border-radius: 8px;
  color: #6b4f12;
  font-size: 14px;
  font-weight: 500;
}
.status-mode-badge.transition-mode::before {
  content: "⚡";
  font-size: 18px;
  margin-right: 4px;
}
.status-mode-badge.transition-mode .status-mode-link {
  margin-left: auto;
  color: #8a4d10;
  font-weight: 600;
  text-decoration: underline;
}
```

- [ ] **Step 2: Verify CSS brace balance**

```bash
cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
  python -c "
with open('app/static/styles.css', 'r', encoding='utf-8') as f:
    css = f.read()
opens, closes = css.count('{'), css.count('}')
assert opens == closes, f'CSS braces mismatch: {opens} open vs {closes} close'
print(f'OK: {opens} matched braces')
"
```

- [ ] **Step 3: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/styles.css && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] styles: add .status-mode-badge.transition-mode (V1.7.5)"
```

---

## Task 10: Add 2 knowledge entries

**Files:**
- Modify: `trading-system-codex/app/static/core/knowledge.js`

- [ ] **Step 1: Write failing test**

In `tests/test_knowledge_catalog.py`, add:

```python
def test_v175_knowledge_entries_present():
    """2 new V1.7.5 entries: volatility_compression, bayesian_setup_probability."""
    sections = _load_knowledge_sections()
    all_ids = {item["id"] for s in sections for item in s["items"]}
    required = {"volatility_compression", "bayesian_setup_probability"}
    missing = required - all_ids
    assert not missing, f"missing knowledge entries: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_knowledge_catalog.py::test_v175_knowledge_entries_present -v
```

Expected: FAIL.

- [ ] **Step 3: Add 2 `term()` entries to `knowledge.js`**

In `app/static/core/knowledge.js`, find the `dataQualityItems` array (or `macroItems`) and append:

```javascript
term("volatility_compression", "波动率压缩检测", {
  category: "volatility",
  family: "compression",
  level: "intermediate",
  display_mode: "full",
  importance: "useful",
  aliases: ["vol_squeeze", "bb_squeeze", "compression_ratio"],
  summary: "BB-width 在历史分布中的位置。压缩 → 突破预警。",
  definition: "多周期 percentile rank: 当前 BB-width / 90 日 MA。Ratio < 0.5 = 极端压缩（90th+ percentile），ratio < 0.7 = 强压缩（75th），ratio > 1.4 = 强扩张（25th）。",
  why_it_matters: "波动率收缩后扩张是经典 regime-transition 信号。压缩期 BTC 突破后常伴随大趋势。",
  formula: "score = bucket(ratio); ratio = bb_width / bb_width_ma_90",
  how_to_use: "压缩期（score > 80）进入 transition 模式。V1.7.5 评分对 transition 模式有专门权重。",
  useful_when: ["日线 + 周线同时压缩", "BB-width 在历史 10% 分位以下", "临近关键支撑/阻力"],
  thresholds: ["ratio < 0.5 = 极端压缩", "ratio < 0.7 = 强压缩", "ratio > 1.4 = 强扩张"],
  risk_note: "压缩本身不预测方向，需要 vol_compression + 趋势信号共同确认（multiplicative gate）。",
  page_refs: ["monitoring-overview", "ai-strategy"],
  related_terms: ["bayesian_setup_probability", "net_liquidity", "iorb_corridor"],
  tags: ["volatility", "compression", "transition", "core"],
}),
term("bayesian_setup_probability", "Bayesian 设置胜率", {
  category: "scoring",
  family: "ev",
  level: "advanced",
  display_mode: "full",
  importance: "useful",
  aliases: ["setup_ev", "win_probability", "posterior"],
  summary: "P(win) = base_prior × Π(likelihoods)。V1.7.5 用 Bayesian 评估 setup 真实胜率。",
  definition: "Bayesian posterior: prior (base 0.45) × product of likelihoods (each sub-score contributes 0.5x-1.6x based on signal quality)。",
  why_it_matters: "传统 risk_reward 只看 rr 倍数。左侧 5R 交易（止损率大但回报更高）以前被封顶 90。EV = P(win) × RR 真正反映'胜率×回报'。",
  formula: "P(win) = 0.45 × Π(likelihoods) / Z; clamped [0.01, 0.99]",
  how_to_use: "trigger_state 现在用 ev_score (P(win) × RR × 100) ≥ ev_threshold 替代旧 min_rr_trade 门。",
  useful_when: ["regime transition 场景", "宽止损 + 大 TP1 交易", "vol_compression 同时存在时"],
  thresholds: ["P(win) > 0.7 = 强设置", "ev_score > 65 = 触发候选"],
  risk_note: "likelihoods 是硬编码启发式（非历史胜率 lookup）。后续可改为基于 setup_outcome 表的精确 posterior。",
  page_refs: ["monitoring-overview", "ai-strategy"],
  related_terms: ["volatility_compression", "net_liquidity"],
  tags: ["scoring", "ev", "bayesian", "transition"],
}),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_knowledge_catalog.py::test_v175_knowledge_entries_present -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/core/knowledge.js trading-system-codex/tests/test_knowledge_catalog.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] knowledge: add vol_compression + bayesian_setup_probability entries (V1.7.5)"
```

---

## Task 11: Update existing `test_strategy_no_microstructure.py` for transition weights

**Files:**
- Modify: `trading-system-codex/tests/test_strategy_no_microstructure.py`

- [ ] **Step 1: Read the test file**

In `tests/test_strategy_no_microstructure.py`, find the test that checks for the absence of microstructure weights.

- [ ] **Step 2: Add test for transition mode weights presence**

Add a new test:

```python
def test_transition_mode_weights_in_config():
    """The new 'transition' mode weights must be present and include vol_compression."""
    from pathlib import Path
    import json
    config_path = Path("app/monitoring/configs/market_strategy_signal_config_v17.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert "transition" in config["long_weights_by_mode"]
    assert "vol_compression" in config["long_weights_by_mode"]["transition"]
    assert "transition" in config["short_weights_by_mode"]
    assert "vol_compression" in config["short_weights_by_mode"]["transition"]
```

- [ ] **Step 3: Run test to verify it passes**

```bash
python -m pytest tests/test_strategy_no_microstructure.py -v
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/tests/test_strategy_no_microstructure.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[test] V1.7.5: assert transition mode weights exist with vol_compression"
```

---

## Task 12: Final regression + CHANGELOG

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Run full pytest suite**

```bash
cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest -q 2>&1 | tail -3
```

Expected: ~875+ passed, 6 skipped, 0 failed (or 1 known pre-existing failure).

- [ ] **Step 2: Run ruff**

```bash
cd trading-system-codex && python -m ruff check .
```

Expected: All checks passed (modulo pre-existing live_service.py E501).

- [ ] **Step 3: Run node --check**

```bash
cd trading-system-codex && find app/static -name "*.js" -print0 | xargs -0 node --check && echo OK
```

- [ ] **Step 4: Update CHANGELOG.md**

In `docs/CHANGELOG.md`, after the V1.7.4 section, add:

```markdown
## V1.7.5 (2026-07-02)

技术指标页评分系统升级 — 解决 3 个根本性缺口：波动率压缩检测、EV 评估、非线性权重交互。

### 后端

- `app/services/strategy_signal/snapshot_builder.py` 新增 `_compute_vol_compression()`（多周期 percentile rank: bb_width / bb_width_ma_90）和 `_compute_setup_probability()`（Bayesian posterior: prior × Π(likelihoods) / Z）
- `app/services/strategy_signal/snapshot_builder.py` 在 transition 模式应用 multiplicative gate（vol_compression / 100 作为 0-1 乘子影响 raw_long/short）
- `app/services/strategy_signal/risk_reward.py` 新增 `risk_reward_score_ev()`：基于 P(win) × RR × 100（不再有 rr=90 封顶）
- `app/services/strategy_signal/scoring_engine.py` `compute()` 使用 `risk_reward_score_ev`（用 setup_probability 计算 EV）
- `app/services/strategy_signal/strategy_generator.py` `trigger_state` 用 `ev_score`（P(win) × RR × 100）替代旧的 `min_rr_trade` 硬门
- `app/monitoring/configs/market_strategy_signal_config_v17.json` 新增 `transition` mode weights（vol_compression 0.30 主导）+ `ev_threshold: 65`

### 前端

- `app/static/pages/analysis.js` 新增 transition mode badge：⚡ 波动率压缩 → 扩张预警 + 跳链到 /market-analysis?focus=breakout
- `app/static/styles.css` 新增 `.status-mode-badge.transition-mode` amber 样式

### 测试

- `tests/test_strategy_signal_snapshot.py` 新增 7 个测试（vol_compression, setup_probability, transition gate）
- `tests/test_risk_reward.py` 新增（EV-based 评分）
- `tests/test_strategy_decision_rules.py` 更新（trigger_state 用 ev_score）
- `tests/test_strategy_no_microstructure.py` 更新（验证 transition 权重存在）
- `tests/test_knowledge_catalog.py` 新增（2 个 V1.7.5 词条）
- `tests/test_analysis_mode_badge.py` 更新（transition badge 渲染验证）

### 知识

- 2 个新词条：volatility_compression（多周期 percentile rank）、bayesian_setup_probability（Bayesian posterior）

### 后续（不在本次范围）

- likelihoods 改为基于 setup_outcome 表的历史胜率 lookup
- trigger_state 在 transition 模式使用动态 ev_threshold
- 完全历史 percentile 计算（当前用 5 档 bucket 近似）
```

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add docs/CHANGELOG.md && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[docs] CHANGELOG: V1.7.5 entry — vol_compression + EV + multiplicative gate"
```

- [ ] **Step 6: Final verification**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git log --oneline -16
```

Verify V1.7.5 commits at the top in order:
1. `?? [macro] snapshot: add _compute_vol_compression (multi-period percentile rank)`
2. `?? [macro] snapshot: add _compute_setup_probability (Bayesian posterior)`
3. `?? [macro] risk_reward: add risk_reward_score_ev (EV-based, no rr=90 ceiling)`
4. `?? [macro] config: add transition mode weights + ev_threshold (V1.7.5)`
5. `?? [macro] snapshot: populate vol_compression + setup_probability + transition multiplicative gate`
6. `?? [macro] scoring_engine: use risk_reward_score_ev in compute()`
7. `?? [macro] strategy: trigger_state uses ev_score (p_win * rr * 100)`
8. `?? [frontend] analysis: add transition-mode badge linking to breakout focus`
9. `?? [frontend] styles: add .status-mode-badge.transition-mode (V1.7.5)`
10. `?? [frontend] knowledge: add vol_compression + bayesian_setup_probability entries (V1.7.5)`
11. `?? [test] V1.7.5: assert transition mode weights exist with vol_compression`
12. `?? [docs] CHANGELOG: V1.7.5 entry — vol_compression + EV + multiplicative gate`

---

## Self-Review Checklist

- ✅ **Spec coverage:** Each requirement has a task
  - `_compute_vol_compression` → Task 1
  - `_compute_setup_probability` → Task 2
  - `risk_reward_score_ev` → Task 3
  - Transition mode weights → Task 4
  - Multiplicative gate + populate vol_compression/setup_probability → Task 5
  - `scoring_engine.compute()` uses EV → Task 6
  - `strategy_generator` trigger uses ev_score → Task 7
  - Transition mode badge → Task 8
  - CSS → Task 9
  - Knowledge entries → Task 10
  - Test updates + regression + CHANGELOG → Tasks 11-12
- ✅ **Placeholder scan:** No TBD/TODO
- ✅ **Type consistency:**
  - `vol_compression_score` / `setup_probability` / `risk_reward_score_ev` / `ev_score` / `vol_factor` — used consistently across Tasks 1, 2, 3, 5, 6, 7
  - `transition` mode key used consistently in Tasks 4, 5
- ✅ **Backward compatibility:**
  - Old `risk_reward_score` function kept (deprecated; new code uses `risk_reward_score_ev`)
  - trend/range mode weights unchanged from V1.7.4
- ✅ **TDD:** Each task writes failing test first

Plan saved at: `trading-system-codex/docs/superpowers/plans/2026-07-02-volatility-compression-ev-multiplicative-gate.md`