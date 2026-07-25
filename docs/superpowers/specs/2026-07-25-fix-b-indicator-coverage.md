# Fix B — Indicator Coverage for 4h/1d/1w

## Context

`app/monitoring/configs/refresh_policies.yaml` lists 23 technical candles, all at 1m/5m/1h/`5s`. The catalog (`indicator_catalog.yaml`) supports 4h and 1d for ten candle-derived indicators, but the refresh policies don't queue them.

`IndicatorMonitoringService` writes `indicator_observations` (not `indicator_values`). Indicator 4h/1d data is therefore empty in `indicator_observations`. The unified strategy's `data_quality` for those horizons is computed by `evidence_confidence` from a `freshness_state` of `"missing"`, returning 0 confidence — affecting long_score/short_score weighting.

`seed_defaults()` only creates per-instrument policies for `btc-usdt-perp` (default), so adding policy YAML entries alone doesn't cover other instruments.

## Goal

Populate `indicator_observations` for `4h` and `1d` technical candles across all enabled instruments within 60-120 s of cold start. (1w/30d out of scope — catalog doesn't yet support them.)

## Approach

Two complementary sub-fixes.

### B.1 — Add 4h + 1d entries to refresh_policies.yaml

In `app/monitoring/configs/refresh_policies.yaml`, add under `technical:`:

```yaml
- indicator_key: ema_20
  scope_type: instrument
  timeframe: 4h
  mode: event_driven_preferred
  event_key: market.candle.closed
  fallback_interval_seconds: 14400
  priority: 3
- indicator_key: ema_20
  scope_type: instrument
  timeframe: 1d
  mode: event_driven_preferred
  event_key: market.candle.closed
  fallback_interval_seconds: 86400
  priority: 3
# ... and similarly for ema_50, ema_200, adx_14, macd_12_26_9,
#     rsi_14, atr_14, natr_14, bbands_20_2, obv
```

10 indicators × 2 new timeframes = 20 new policy entries.

### B.2 — Per-instrument policy expansion at seed time

In `app/services/indicator_monitoring.py:192-205` (`seed_defaults`), change the loop that creates per-instrument policies so it iterates over `repository.list_instruments()` and creates a `(instrument_id, indicator_key)` row for each.

Currently (line 170-205):
```python
default_instrument = "btc-usdt-perp"
# ... only creates policies for default_instrument
```

After:
```python
instruments = await repository.list_instruments()
for instrument in instruments:
    if not instrument.instrument_id:
        continue
    for indicator_key in catalog_indicators:
        upsert_monitoring_policy(
            policy_id=f"{indicator_key}-{instrument.instrument_id}",
            indicator_key=indicator_key,
            scope_type="instrument",
            instrument_id=instrument.instrument_id,
            # ...
        )
```

At startup this creates 11 instruments × 10 indicators × 3 timeframes (1m/5m/1h + new 4h/1d) = 330 policy rows. Reasonable scale.

### B.3 (optional, smaller scope) — Wire indicator fill into strategy prewarm

Extend `app/api/v1/endpoints/strategy.py:403-439` (`prewarm_strategy_dependencies`) to include `"indicators"` as a candidate.

New precompute task type (`page_type="indicators"`) implements in `app/services/precompute.py:_execute_task` (around line 793):

```python
elif page_type == "indicators":
    service = IndicatorService(repository)
    for instrument_id in instrument_ids:
        for tf in SCAN_TIMEFRAMES:  # ("1w", "1d", "4h")
            try:
                await service.ensure_indicator_data(
                    instrument_id=instrument_id,
                    timeframe=tf,
                    auto_calculate=True,
                )
            except Exception:
                logger.exception("indicator_fill failed %s %s", instrument_id, tf)
```

`ensure_indicator_data` (`app/services/indicators.py:152-197`) checks freshness; if stale, calls `calculate_all` which fetches provider candles + computes EMA/RSI/MACD/BBANDS and writes `indicator_values`. The strategy's `market_context.py` reads from `indicator_observations` via `chip_structure`, NOT `indicator_values`, so B.3 alone is not enough — B.1+B.2 (which populate observations) are required.

Therefore B.3 is **optional**: only do it if we want a backup fill path. Skipping it is fine.

## Tests

`tests/test_refresh_policies_4h_1d.py`:
- `test_yaml_has_4h_indicators`: parse YAML, verify indicators `ema_20, ema_50, ema_200, adx_14, macd_12_26_9, rsi_14, atr_14, natr_14, bbands_20_2, obv` all have a 4h entry.
- `test_yaml_has_1d_indicators`: same, 1d.
- `test_yaml_1w_30d_unaffected`: verify YAML does not introduce 1w/30d policies (they have no catalog entry).

`tests/test_indicator_seeding_per_instrument.py`:
- `test_seed_defaults_creates_per_instrument_policies`: mock repository.list_instruments to return 3 instruments; call `seed_defaults()`; assert upsert_monitoring_policy called 3 × 10 × 3 = 90 times for the default timeframes.

`tests/test_precompute_indicator_branch.py` (only if B.3 implemented):
- `test_indicators_branch_fills_4h_1d_1w`: patch IndicatorService; trigger prewarm with "indicators" candidate; assert `ensure_indicator_data` called for each (instrument, timeframe) pair.

## Behavior unchanged

- No change to API response shapes.
- No change to indicator_observations schema.
- 1m/5m/1h refresh cadences preserved (4h/1d are additive).
- 1w/30d still unsupported (out of scope for this fix).

## Risk & Rollback

- **Risk**: Adding 220 background policy rows increases startup cost by ~1-2 s. Acceptable.
- **Risk**: Per-instrument expansion could accidentally create duplicate policy rows if `seed_defaults` is called multiple times. Mitigation: make upsert idempotent (existing unique `policy_id` constraint handles this).
- **Risk**: B.3 (indicator fill) loops over 11 instruments × 3 timeframes = 33 calls, each ~3 s = ~100 s total. Mitigate by limiting B.3 to one (instrument, timeframe) per precompute hint, or skip B.3 entirely.
- **Rollback**: revert YAML entries (cheap), revert `seed_defaults` change, remove B.3.

## Verification

1. `pytest tests/test_refresh_policies_4h_1d.py tests/test_indicator_seeding_per_instrument.py -q` → all green.
2. After startup, query DB:
   ```sql
   SELECT COUNT(*) FROM indicator_monitoring_policies
   WHERE timeframe IN ('4h','1d');
   ```
   Expect ≥ 10 × 11 = 110 rows.
3. `python tests/verify_pages.py --pages indicators,ai-strategy` → OK.
4. Cold-load inspection: `python tests/inspect_strategy_cold_load.py` — within 60 s, `daily.long_score` should reflect real EMA20/RSI data (>0 confidence), not the previous "no observation" floor.