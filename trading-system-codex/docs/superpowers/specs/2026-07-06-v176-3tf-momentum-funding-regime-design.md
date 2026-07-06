# V1.7.6 — 3-Timeframe Momentum + Funding Regime Sub-Score — Design Spec

- **Date**: 2026-07-06
- **Branch**: `main` (V1.7.5 already shipped; this is the next iteration)
- **Status**: Design approved by user ("按照你的判断执行"). Awaiting plan.

## 1. Problem Statement

### 1.1 Why this iteration

V1.7.5 (volatility compression + EV + multiplicative gate, shipped earlier) fixed three scoring gaps but left two structurally weak spots:

1. **Single-band momentum cannot distinguish time scales** — the current `bullish_momentum / bearish_momentum` uses RSI(14) deviation + MACD histogram delta over 1 bar. It cannot differentiate a 20-hour rebound (5 bars on 4h) from a 10-day breakout (60 bars on 4h). In range / transition mode the single sub-score is dropped to weight=0 entirely, losing all momentum signal even when short-horizon mean-reversion or pre-breakout rebound is informative.
2. **`funding_crowding_score` is dead code** — `snapshot_builder.py:710` hardcodes it to `0`, so the `0.18 × funding_crowding_score` term in `DirectionScoringEngine._long_penalty` (scoring_engine.py:117) and the equivalent short term on line 128 are never applied. Meanwhile V2 `derivatives_regime.py:14-18` already classifies funding into `positive_hot / negative_hot / neutral` and emits a (bias, score, evidence) triple that is otherwise discarded.
3. **No `funding` sub-score in weighted sum** — the model treats funding only as a penalty (when wired up). But funding is a **direction signal**, not just a risk flag. A `positive_hot` regime with funding-trend reversal can predict short-side reversals 12-72h ahead — and the current model has no place to express that.

### 1.2 Two design questions, locked-in answers

| # | Question | Decision |
|---|---|---|
| Q1 | Release strategy | V1.7.6 — single release, one spec / one plan / one PR |
| Q2 | Funding data source | Reuse V2 `derivatives_regime.funding_state` (no fresh fetcher) |
| Q3 | Backwards compat for old momentum keys | **Delete** `bullish_momentum` / `bearish_momentum` / `momentum_source` — full chain update |
| Q4 | Funding regime granularity | Reuse V2 3-classification (`positive_hot` / `negative_hot` / `neutral`) — no new V2 states |
| Q5 | 3-frame momentum aggregation | **A3** layered weights 0.45/0.35/0.20 (short/mid/long), expressed via per-mode weight tables |
| Q6 | Funding fallback when V2 degraded | **B1**: skip sub-scores (None) + renormalize remaining weights; flag `funding_degraded` |

### 1.3 Design goals

1. **Replace single-band momentum with 3 independent time frames** (5 / 20 / 60 bars on the snapshot's TF) — each with its own percentile rank over a 90-bar window. The independence invariant from `test_snapshot_feature_sources.py` (cross-source contamination check) must hold.
2. **Restore `funding_crowding_score` to a real value derived from V2**, so the existing penalty formula in `scoring_engine._long_penalty` / `_short_penalty` actually fires.
3. **Add `funding_pressure_long` / `funding_pressure_short` sub-scores** to the weighted sum, mapped from V2 `funding_state`. They reward funding-aligned direction **and** punish funding-crowded direction (current behavior only punishes, asymmetrically).
4. **Update per-mode weight tables** so each mode makes sense with the new sub-scores: trend has 3 distinct momentum frames, range keeps `momentum_mid` only (mean-reversion signal), transition gains `momentum_short` for pre-breakout rebound detection alongside the existing `vol_compression` dominant slot.
5. **Preserve the V1.7.5 multiplicative gate intact** — `vol_compression / 100` as 0-1 gate on `raw_long` / `raw_short` in transition mode.
6. **Preserve the EV-based `risk_reward_score` formula** from V1.7.5 — `P(win) × RR × 100` capped at 100 (no 90 ceiling). Untouched by this iteration.

## 2. Architecture

### 2.1 Component diagram

```
                          StrategySnapshotBuilder.build()
                                      │
        ┌─────────────────────────────┼───────────────────────────────┐
        ▼                             ▼                               ▼
  Layer A — 3-TF Momentum      Layer B — Funding Regime      Layer C — Reconnect
  (REPLACE old)                (NEW)                       funding_crowding_score
        │                             │                               │
   inputs:                         inputs:                       inputs:
   • rsi_5 / rsi_20 / rsi_60       • V2 funding_state            • V2 funding_state
   • macd_hist at 5/20/60          • (positive_hot /             • (positive_hot →
   • macd_prev at 5/20/60            negative_hot / neutral)        funding=80,
   • 90-bar close history          • None / DATA_MISSING            negative_hot=80,
                                       ↓                             neutral=20,
                                   funding_pressure_long             missing=0)
                                   funding_pressure_short
                                                                        
        │                             │                               │
   outputs:                        outputs:                       outputs:
   • momentum_short (×2)           • funding_pressure_long       • funding_crowding_score
   • momentum_mid   (×2)           • funding_pressure_short         (real value, not 0)
   • momentum_long  (×2)           • funding_degraded flag
   (each is bullish+ bearish)
        │                             │                               │
        ▼                             ▼                               ▼
                            weighted_score(snapshot, mode_weights)
                                      │
                                      ▼
                          DirectionScoringEngine.compute
                          (existing; long/short/neutral scores)
                                      │
                                      ▼
                            funding_crowding_score → _long_penalty /
                                                     _short_penalty
                            (existing; now real, not zero)
```

### 2.2 Layer A — 3-Timeframe Momentum

**Replacement scope** (`snapshot_builder.py:803-844`):

The function `_feature_components` previously emitted three keys: `bullish_momentum`, `bearish_momentum`, `momentum_source`. V1.7.6 replaces them with six:

```
momentum_short (bullish + mirror bearish key exposed as momentum_short_bearish)
momentum_mid   (bullish + mirror bearish key as momentum_mid_bearish)
momentum_long  (bullish + mirror bearish key as momentum_long_bearish)
```

The mirror keys exist because per-mode weight tables reference `_bearish` variants for `short_weights_by_mode` symmetric handling.

**Per-frame formula** (new helper `_compute_momentum_at_scale`):

```
inputs: rsi (0..100), macd_hist (delta-based), macd_prev, close_history (≥90 bars)

rsi_pct = percentile_rank(close_history_for_rsi_window_90, rsi)
macd_delta = max(0, macd_hist - macd_prev) * 3.0   # bullish contribution
raw_bullish = 50 + (rsi_pct - 50) * 0.85 + macd_delta
macd_delta_short = max(0, macd_prev - macd_hist) * 3.0   # bearish contribution
raw_bearish = 50 + (100 - rsi_pct) * 0.85 + macd_delta_short
return clamp(raw_bullish), clamp(raw_bearish)
```

`percentile_rank` is a new private helper in `risk_reward.py`:

```
def _percentile_rank(history: list[float], current: float) -> float:
    """0..100. Returns 50 if history is empty or current is None/NaN."""
    if not history or current is None or current != current:
        return 50.0
    below_or_equal = sum(1 for x in history if x <= current)
    return clamp(below_or_equal / len(history) * 100)
```

**Independent-source invariants** (must continue to hold):

- Changes to RSI at one scale (rsi_5) do NOT change `momentum_mid` or `momentum_long` outputs
- Changes to `direction_metrics` (bullish/bearish) do NOT change any momentum sub-score (existing test at `test_snapshot_feature_sources.py:157-185` augmented; new assertion ensures no `bullish_momentum` / `bearish_momentum` keys present)

### 2.3 Layer B — Funding Regime Sub-Score

**Data source** (`strategy_unified/derivatives_regime.py:14-18` already emits):

`funding_state` ∈ {`positive_hot`, `negative_hot`, `neutral`} (string)

V1.7.6 reads this from the `MarketDimension.details.funding_state` field after `DerivativesRegimeEngine.compute()` is invoked. If V2 has not been invoked yet (legacy calling paths), or `funding_state` is not in the 3 valid values, treat as **degraded** (`funding_degraded=True`).

**Mapping table** (new helper `_compute_funding_pressure`):

| V2 `funding_state` | `funding_pressure_long` | `funding_pressure_short` | `funding_crowding_score` |
|---|---|---|---|
| `positive_hot` | 15 (long crowded → suppress) | 85 (short reversal opportunity) | 80 |
| `negative_hot` | 85 (short crowded → long reversal) | 15 | 80 |
| `neutral` | 50 (neutral) | 50 | 20 |
| None / invalid / missing / DATA_MISSING | **None** (skip slot) | **None** (skip slot) | 0 (preserves current dead-zero behavior in penalty path) |

The 15/85/50 mid-band was chosen because the existing baseline "long penalty" weight is 0.18 (of `funding_crowding_score`), and we want the new sub-score (which has its own weight ~0.08-0.12 per mode) to provide a stronger signal than the linear penalty alone. 15/85 gives the sub-score a meaningful ~70-point spread vs neutral.

### 2.4 Layer C — Reconnect `funding_crowding_score`

**Change at `snapshot_builder.py:710`**:

```diff
-                "funding_crowding_score": 0,
+                "funding_crowding_score": _remap_funding_crowding(
+                    funding_state=funding_state,  # from V2 derivatives_regime
+                ),
```

`_remap_funding_crowding` implements the 80/80/20/0 mapping above. After this change, `scoring_engine._long_penalty` (line 117) and `_short_penalty` (line 128) will actually fire when funding is hot, instead of always multiplying by zero.

### 2.5 Weighted-score skip / renormalize semantics

Existing `weighted_score` (scoring_engine.py:43-44):

```python
def weighted_score(values: dict[str, Any], weights: dict[str, float]) -> float:
    return clamp(sum(clamp(values.get(key, 0)) * weight for key, weight in weights.items()))
```

`values.get(key, 0)` — defaults to 0 when key absent. **But** `0` is a valid sub-score value, so we cannot distinguish "missing" from "intentionally 0". V1.7.6 changes the missing default to `None` for the funding slots specifically, and `_compute_funding_pressure` returns `None` when degraded.

To handle the `None` case, **a new variant** is added:

```python
def weighted_score_skip(values: dict[str, Any], weights: dict[str, float]) -> float:
    """Skip slots where value is None; renormalize remaining weights to original sum."""
    used_pairs = [(clamp(values[key]) if values.get(key) is not None else None, w)
                  for key, w in weights.items()]
    used_pairs = [(v, w) for v, w in used_pairs if v is not None]
    if not used_pairs:
        return 50.0  # all slots degraded → neutral
    sum_weights = sum(w for _, w in used_pairs)
    return clamp(sum(v * w for v, w in used_pairs) / sum_weights * sum(weights.values()))
```

Used only for funding slots. Existing `weighted_score` retained for all other modes (no behavior change for those).

### 2.6 Per-mode weight tables

**Long side** — sum must equal 1.00 in each row:

| Component | Flat | Trend | Range | Transition |
|---|---|---|---|---|
| mtf_trend_bullish | 0.18 | 0.20 | 0.05 | 0.10 |
| bullish_structure | 0.18 | 0.20 | 0.05 | 0.10 |
| **momentum_short** | **0.06** | **0.06** | 0.00 | **0.15** |
| **momentum_mid** | **0.05** | **0.06** | **0.10** | 0.00 |
| **momentum_long** | **0.05** | **0.05** | 0.00 | 0.00 |
| long_risk_reward | 0.12 | 0.13 | 0.10 | 0.15 |
| regime_fit_long | 0.13 | 0.13 | 0.08 | 0.05 |
| execution_quality | 0.10 | 0.10 | 0.05 | 0.05 |
| range_structure | 0.06 | 0.00 | 0.30 | 0.00 |
| low_directional_spread | 0.00 | 0.00 | 0.20 | 0.00 |
| **funding_pressure_long** | **0.07** | **0.07** | **0.07** | **0.10** |
| **vol_compression** | 0.00 | 0.00 | 0.00 | **0.30** (existing) |
| **Sum** | **1.00** | **1.00** | **1.00** | **1.00** |

Arithmetic verification (each row sums to exactly 1.00):
- Flat: 0.18+0.18+0.06+0.05+0.05+0.12+0.13+0.10+0.06+0+0.07+0 = **1.00** ✓
- Trend: 0.20+0.20+0.06+0.06+0.05+0.13+0.13+0.10+0+0+0.07+0 = **1.00** ✓
- Range: 0.05+0.05+0+0.10+0+0.10+0.08+0.05+0.30+0.20+0.07+0 = **1.00** ✓
- Transition: 0.10+0.10+0.15+0+0+0.15+0.05+0.05+0+0+0.10+0.30 = **1.00** ✓

**Short side mirrors** with `mtf_trend_bearish`, `bearish_structure`, `momentum_short_bearish` (0.06), `momentum_mid_bearish` (0.05), `momentum_long_bearish` (0.05), `short_risk_reward`, `regime_fit_short`, `funding_pressure_short` at the same weights; `range_structure`, `low_directional_spread`, `vol_compression` shared (no bullish/bearish variants).

**Why these numbers** (continuity with V1.7.4/V1.7.5 semantics):
- **Flat**: 3 momentum frames sum 0.16 (continuity with V1.7.5 `bullish_momentum: 0.16`); trend/structure dropped slightly from 0.20 to 0.18 (1.00 - 0.16 momentum - 0.12 RR - 0.13 regime - 0.10 exec - 0.06 range - 0.07 funding = 0.36 → split 0.18/0.18). `funding_pressure_long: 0.07` reflects "in flat regime, funding is one signal among many, not dominant".
- **Trend**: trend/structure dominate (0.20 each = 0.40 of 1.00); momentum frames keep 0.17; funding 0.07 (lower than in transition where 0.10 makes sense).
- **Range**: only `momentum_mid 0.10` retained (weekly mean-reversion). funding 0.07 (lower than initially proposed; we keep RR/regime credits meaningful at 0.10/0.08). Trend/structure drop to 0.05 as in V1.7.4.
- **Transition**: `vol_compression 0.30` dominant anchor (V1.7.5). `momentum_short 0.15` is the V1.7.6 addition — captures pre-breakout rebound. funding 0.10 (sanity check for crowded squeeze). Total non-vol non-momentum slots (trend+structure+RR+regime+exec) = 0.45.

**Neutral weights unchanged** (V1.7.5): `range_structure 0.25`, `low_adx 0.20`, `low_volume_confirmation 0.20`, `low_directional_spread 0.15`, `high_conflict_score 0.10`, `event_uncertainty 0.10`.

### 2.7 Config schema additions

`market_strategy_signal_config_v17.json` adds the following (does not remove existing fields):

```json
{
  "momentum_scale_definitions": {
    "short": { "rsi_lookback": 5, "macd_lookback": 5, "description": "近 5 根 K 线: ~20h on 4h TF, ~5h on 1h TF" },
    "mid":   { "rsi_lookback": 20, "macd_lookback": 20, "description": "近 20 根 K 线: ~3.3 天 on 4h TF, ~20h on 1h TF" },
    "long":  { "rsi_lookback": 60, "macd_lookback": 60, "description": "近 60 根 K 线: ~10 天 on 4h TF, ~2.5 天 on 1h TF" }
  },
  "momentum_percentile_window": 90,
  "funding_regime_mapping": {
    "positive_hot":   { "funding_pressure_long": 15, "funding_pressure_short": 85, "funding_crowding_score": 80 },
    "negative_hot":   { "funding_pressure_long": 85, "funding_pressure_short": 15, "funding_crowding_score": 80 },
    "neutral":        { "funding_pressure_long": 50, "funding_pressure_short": 50, "funding_crowding_score": 20 },
    "missing":        { "funding_pressure_long": null, "funding_pressure_short": null, "funding_crowding_score": 0 }
  }
}
```

No schema validator changes needed (additive).

### 2.8 Caller chain update (Deletion Cascade)

Deleting `bullish_momentum` / `bearish_momentum` / `momentum_source` requires updating **9 source files** + **2 build artifacts**:

| File | Update required |
|---|---|
| `app/services/strategy_signal/snapshot_builder.py` | Remove emission + update `_feature_components` signature to accept 3-frame RSI/MACD inputs |
| `app/services/strategy_signal/scoring_engine.py` | No direct read; reads via `weighted_score(snapshot, weights)` so behavior cascades naturally |
| `app/services/strategy_signal/confidence_dimensions.py` | Likely reads `bullish_momentum` / `bearish_momentum` — replace with max-of-3 frame variant |
| `app/services/strategy_signal/setup_lifecycle.py` | Likely reads momentum keys — replace with mapped values from new keys |
| `app/services/strategy_signal/strategy_generator.py` | If reads momentum keys — replace |
| `tests/test_snapshot_feature_sources.py` | Add `not in {bullish_momentum, bearish_momentum, momentum_source}` assertion; update independence test inputs |
| `tests/test_strategy_decision_rules.py` | Update fixture: replace `bullish_momentum: 60` etc. with `momentum_short: 60` `momentum_mid: 60` `momentum_long: 60` |
| `tests/test_strategy_no_microstructure.py` | Same fixture update |
| `tests/test_strategy_signal_snapshot.py` | Same fixture update |
| `tests/test_strategy_setup_lifecycle_v17.py` | Same fixture update (if applicable) |
| `tests/test_confidence_dimensions.py` | Same fixture update |
| `dist/portable_bundle/...` (mirror copies after each release) | Mechanical rebuild post-merge |

A test (`test_old_momentum_keys_deleted`) asserts these keys are no longer in any snapshot dict — this will fail loudly if any consumer is missed.

### 2.9 UI / Frontend (out-of-scope for this spec, listed for awareness)

Strategy page renderers (`app/static/pages/strategy/`) may eventually need updates if they displayed `bullish_momentum` directly. V1.7.6 backend changes are the focus; UI will show 3-frame momentum via existing `*_features` rendering once frontend team picks it up. No frontend change in this spec.

## 3. Data Flow & Sequencing

### 3.1 Snapshot build path

```
StrategySnapshotBuilder.build()
│
├─ Collects indicators from indicator_matrix:
│     rsi_short, rsi_mid, rsi_long (computed at runtime via RSI(window))
│     macd_hist at short/mid/long + macd_prev at each scale
│     close_history_90 (last 90 close prices)
│
├─ Reads V2 derivatives_regime.funding_state (if V2 already ran)
│     (else funding_state = None → degraded)
│
├─ Calls _feature_components(indicators, structure, regime, direction_metrics,
│                            rsi_short, rsi_mid, rsi_long,
│                            macd_short, macd_mid, macd_long,
│                            macd_prev_short/..._long,
│                            funding_state=..., funding_degraded=...)
│     → emits momentum_short/mid/long + bearish mirrors
│     → emits funding_pressure_long/short (or None)
│     → emits funding_crowding_score (real value, not 0)
│
├─ DirectionScoringEngine.compute(snapshot)
│     → raw_long = weighted_score_skip(snapshot, mode_long_weights)
│     → raw_short = weighted_score_skip(snapshot, mode_short_weights)
│     → raw_neutral = weighted_score(snapshot, neutral_weights)  (unchanged)
│     → funding_crowding_score → _long_penalty / _short_penalty (now actually fires)
│
└─ setup_probability / EV gating → unchanged from V1.7.5
```

### 3.2 Failure / degraded paths

| Condition | Behavior |
|---|---|
| RSI at one scale missing (None) | `_compute_momentum_at_scale` returns (50, 50) for that scale only |
| All 3 RSI scales missing | All 6 momentum keys = 50; weight-sum unchanged; degraded flag not raised (RSI is always computed) |
| All MACD at one scale missing | Same — neutral (50, 50) for that scale |
| `close_history_90` insufficient | `percentile_rank` returns 50 (neutral fallback); momentum sub-scores get less spread but not 0 |
| V2 `funding_state` invalid / None | `funding_pressure_*` = None; `weighted_score_skip` renormalizes; `funding_degraded = True`; `funding_crowding_score` = 0 (preserves current dead-zero penalty) |
| V2 service unreachable (exception) | Caught at `_remap_funding_crowding`; `funding_state` = None path |

All paths preserve the existing invariant: **`weighted_score` output ∈ [0, 100]`, no escape outside band.**

## 4. Error Handling

| Error | Detection | Handling |
|---|---|---|
| RSI out-of-range (e.g. negative from bad input) | `clamp()` in `_compute_momentum_at_scale` | Clamped to [0, 100] before use |
| MACD delta NaN | `_num()` helper from `risk_reward.py` (already NaN-safe) | Returns 0 → neutral contribution |
| `percentile_rank` empty list | explicit `if not history: return 50.0` | Returns neutral |
| V2 funding_state returns unexpected string (e.g. `"EXTREME_HOT"` from future V2) | Mapping table lookup with `.get(state_str, missing_branch)` | Treated as degraded; `funding_pressure_*` = None |
| 50%+ weight slots degraded simultaneously | `weighted_score_skip` returns 50 (degraded-neutral) | Caller can detect via `funding_degraded=True` and `multi_factor_degraded=True` |
| Old consumer still reads `bullish_momentum` | `test_old_momentum_keys_deleted` test will fail | Forces explicit migration in code review |

## 5. Testing Strategy

### 5.1 Unit tests (new file `tests/test_v176_3timeframe_momentum.py`, 8 tests)

1. `test_momentum_at_scale_returns_neutral_when_inputs_missing` — RSI/MACD/close_history all None → (50, 50)
2. `test_momentum_at_scale_percentile_rank_handles_extreme_high` — RSI=95 with all history <90 → percentile 100 → score >95
3. `test_momentum_at_scale_percentile_rank_median_returns_50` — RSI exactly at median of 90-bar window → percentile 50 → score 50
4. `test_momentum_at_scale_percentile_rank_handles_NaN_close_history` — returns 50, no exception
5. `test_feature_components_emits_all_6_momentum_keys` — verifies `momentum_short/mid/long` + `_bearish` mirrors present
6. `test_feature_components_does_not_emit_old_momentum_keys` — `bullish_momentum` / `bearish_momentum` / `momentum_source` NOT in features dict
7. `test_3frame_momentum_independent_from_direction_metrics` — changes to direction_metrics do not affect any of 6 momentum sub-scores
8. `test_3frame_momentum_cross_scale_independent` — changing rsi_5 does not affect momentum_mid output

### 5.2 Unit tests (new file `tests/test_v176_funding_regime.py`, 7 tests)

9. `test_funding_pressure_positive_hot_suppresses_long` — funding_state="positive_hot" → funding_pressure_long=15, funding_pressure_short=85
10. `test_funding_pressure_negative_hot_suppresses_short` — funding_state="negative_hot" → mirrored
11. `test_funding_pressure_neutral_is_50_50` — neutral
12. `test_funding_degraded_returns_none_skip_behavior` — None funding_state → funding_pressure_* = None + flag
13. `test_funding_crowding_score_reconnected_from_v2_state` — replaces hardcoded 0 with mapped value 80/80/20/0
14. `test_weighted_score_skip_normalizes_when_funding_degraded` — when funding pressure is None, raw_long is renormalized using remaining slots
15. `test_penalty_includes_real_funding_value` — after reconnection, _long_penalty(0.18 × funding_crowding_score) reflects actual funding hotness

### 5.3 Schema / weight tests (added to existing `test_strategy_signal_snapshot.py`, 5 tests)

16. `test_weight_tables_sum_to_one_all_modes` — flat + trend + range + transition × {long, short}
17. `test_long_weights_by_mode_trend_has_3_momentum_frames` — trend table contains momentum_short/mid/long summing to ~0.17
18. `test_long_weights_by_mode_transition_has_momentum_short_015` — transition has vol_compression 0.30 + momentum_short 0.15
19. `test_long_weights_by_mode_range_keeps_only_momentum_mid` — range has momentum_mid 0.10, no momentum_short or momentum_long
20. `test_neutral_weights_unchanged_from_v175` — neutral weights sum and components identical to V1.7.5

### 5.4 Independence tests (modify `test_snapshot_feature_sources.py`)

21. `test_old_momentum_keys_deleted_from_snapshot` — `not in {"bullish_momentum", "bearish_momentum", "momentum_source"}`
22. Existing test `test_feature_components_keep_momentum_independent_from_direction_score` — augment inputs to also cover all 6 new momentum keys

### 5.5 End-to-end / regression

23. Run `pytest -k "v176"` for all new tests
24. Run `pytest tests/test_strategy_signal_snapshot.py tests/test_snapshot_feature_sources.py` for regression
25. Run `pytest tests/test_strategy_decision_rules.py` with new fixtures
26. Run full `pytest` to ensure no other consumers break

## 6. Migration / Rollout Plan (forward-looking, plan details live in writing-plans)

- **Stage 1**: Schemas + config (`market_strategy_signal_config_v17.json`) — additive only, no behavior change yet
- **Stage 2**: Add `momentum_scale_definitions` + `_percentile_rank` helper in `risk_reward.py` (no consumer change)
- **Stage 3**: Add `_compute_momentum_at_scale` and emit 6 new keys while keeping old 3 keys (back-compat shim)
- **Stage 4**: Update per-mode weight tables; change `weighted_score` to `weighted_score_skip` for funding slots
- **Stage 5**: Update all 9 consumer files to read new keys; remove old 3 keys; add `test_old_momentum_keys_deleted`
- **Stage 6**: Wire funding input from V2 — replace hardcoded 0 at `snapshot_builder.py:710`
- **Stage 7**: Update test fixtures in 4 test files
- **Stage 8**: Run full pytest suite; verify no regression; commit

Each stage has a corresponding commit for bisect/revert.

## 7. Out of Scope

- Frontend rendering changes (covered by separate V1.7.6-frontend follow-up if needed)
- Adding new V2 funding_state classes (Q4 decision: 3-classification only)
- Cross-sectional (multi-asset) ranking (this project is BTC-only)
- Funding rate data sourcing — V2 module already handles this upstream
- Live funding rate monitoring UI — separate V1.7.6-ui task if requested

## 8. References

- V1.7.4 spec: `docs/superpowers/specs/2026-07-02-regime-aware-scoring-modes-design.md`
- V1.7.5 spec: `docs/superpowers/specs/2026-07-02-volatility-compression-ev-multiplicative-gate-design.md`
- `app/services/strategy_signal/snapshot_builder.py:806-811` (current momentum formula)
- `app/services/strategy_signal/snapshot_builder.py:710` (hardcoded 0 — the dead code)
- `app/services/strategy_signal/scoring_engine.py:43-44, 117, 128` (weighted_score + penalty)
- `app/services/strategy_unified/derivatives_regime.py:14-18` (V2 funding_state classification)
- `app/monitoring/configs/market_strategy_signal_config_v17.json` (weight tables)
- `tests/test_snapshot_feature_sources.py` (independence invariant, must continue holding)
