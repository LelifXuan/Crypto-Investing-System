# Three Final-Mile Cold-Load Fixes

## Context

The v1–v3 commits fixed the user-facing cold-load bugs:
- v1 (`8c38f76`): warming short-circuit + prewarm call + try/except.
- v2 (`6505998`): bounded warming poll + cache warming source preserved.
- v3 + v3.1 (`cbd8384`, `dba0326`): distinguish "data ready, no edge" from "data pending" copy.

After those fixes the page never falls into the misleading "no opportunities" state, but the user still waits 30+ seconds for real data because three deeper issues remain:

1. **Precompute worker is starved by long-held writer transactions** — `market_events_feed.sync_default_feeds` opens one session, holds it across many network fetches + per-entry upserts. Other workers (precompute, indicator_monitor, market_event_translation) all queue behind it on SQLite's single writer lock. Combined with several SELECT-then-INSERT repositories that issue 2 round-trips per logical write, the precompute queue stays slow.

2. **Indicator monitor only covers 1m/5m/1h timeframes** — `refresh_policies.yaml` lists no technical candles for 4h/1d/1w/30d, so the unified strategy's 4h+ timeframe nodes never have `indicator_observations` to read. The 28 rows in `indicator_values` for btc 1d are leftover from manual `IndicatorService.calculate_all` calls — the background monitoring worker writes only `indicator_observations`.

3. **`structure_snapshot` SQL tables are dead schema** — `replace_structure_snapshot_bundle` and `app/services/structure/writers.py` + `readers.py` have zero callers. Active code persists to `page_snapshot_cache` instead. The 7 `structure_*` tables are never written.

## Goal

Reduce cold-load wall time from 30+ s → ≤ 10 s on a fresh database, and eliminate the placeholder copy path so future cold loads show real data within minutes of the first user visit.

## Three Independent Fixes

### Fix A — Precompute SQLite contention

**Root cause**: `market_events_feed.sync_default_feeds` opens one session at line 36 of the worker, holds it across all 4 RSS feeds × N entries × {SELECT, INSERT/UPDATE, SELECT, INSERT for links}. While this transaction is open, `precompute_worker`, `indicator_monitor`, and `market_event_translation` each want to write and queue on SQLite's writer mutex. busy_timeout=30 s eventually times out, throwing `OperationalError: database is locked`.

**Fix** (3 sub-changes):

1. **Convert SELECT-then-INSERT repository methods to single-statement upserts** (use `sqlite_insert.on_conflict_do_update` everywhere a unique key exists). Each removes one round-trip per write and cuts writer-lock hold time roughly in half.

   Targets (in `app/repositories/market_repository.py`):
   - `upsert_page_snapshot_cache` (line 277)
   - `add_indicator_value` (line 462)
   - `add_or_update_observation` (line 992) — already has `dedupe_key` unique constraint; just need `on_conflict_do_update`
   - `upsert_indicator_definition` (line 853)
   - `upsert_monitoring_policy` (line 905)
   - `upsert_alert_rule` (line 1115)
   - `upsert_macro_event` (line 1225)
   - `upsert_macro_source_health` (line 1276)
   - `upsert_translation_cache` (line 613)
   - `upsert_translation_text_cache` (line 650)
   - `upsert_translation_job` (line 678)
   - `upsert_market_event_translation_map` (line 706)
   - `add_market_event_links` (line 781) — `INSERT OR IGNORE` on `(event_id, instrument_id)` after adding the unique constraint
   - `add_structure_event` (line 1506) — but this becomes dead code in Fix C, so skip

2. **Split `market_events_feed.sync_default_feeds` per-entry commit**. Refactor `app/services/market_events_feed.py:52-118` and `app/workers/market_events_feed.py:35-49`: fetch all entries first (no session), then open per-entry short sessions, commit after each entry's batch. The transaction duration drops from "many seconds" to "few ms".

3. **Split `market_event_translation.translate_one` into read → network → write** in `app/workers/market_event_translation.py:155-210`: SELECT event into a dict, close session, do translation network call (no lock held), re-open session, INSERT/UPDATE.

Expected effect:
- `OperationalError: database is locked` from market_event_translation drops to ~0.
- Precompute lock-wait drops from 30 s → < 5 s.
- Combined cold-load wall time drops to 3-8 s.

### Fix B — Indicator coverage for 4h/1d/1w

**Root cause**: `app/monitoring/configs/refresh_policies.yaml` has 23 technical policies, all at 1m/5m/1h. The catalog (`indicator_catalog.yaml`) supports 4h and 1d for ten candle-derived indicators, but the refresh policies don't queue them. 1w/30d have no catalog entries (out of scope for this fix).

Plus a structural issue: `seed_defaults()` only creates per-instrument policies for BTC; the worker doesn't auto-expand policies for other instruments when iterating.

**Fix** (3 sub-changes):

1. **Add 4h + 1d entries to `app/monitoring/configs/refresh_policies.yaml`** under `technical:` for the 10 candle-derived indicators. Use cadence `14400` s (4h) and `86400` s (1d). Keep the same `event_driven_preferred` mode.

2. **Wire indicator fill into strategy prewarm**. Update `app/api/v1/endpoints/strategy.py:403-439` `prewarm_strategy_dependencies` to include a `"indicators"` candidate. New precompute task type (`page_type="indicators"`): for each instrument × configured timeframe (1w, 1d, 4h), call `IndicatorService.ensure_indicator_data(...)`. Implementation in `app/services/precompute.py:_execute_task` with a new branch.

3. **Per-instrument policy expansion** (optional, smaller scope). Update `IndicatorMonitoringService.seed_defaults()` (line 192-205) so it inserts per-instrument policy rows for all enabled instruments, not just the default btc-usdt-perp. Acceptance: 11 instruments × 10 indicators × 2 timeframes = 220 policy rows at startup. Acceptable; bounded.

Expected effect:
- `indicator_observations` populated for btc 4h + 1d + (eventually) other instruments.
- Strategy page refresh → indicators are guaranteed cached within 60-120 s after first hit.

### Fix C — Drop dead structure_snapshot schema

**Root cause**: Active code persists to `page_snapshot_cache`, not the SQL tables. `replace_structure_snapshot_bundle`, `add_structure_event`, `add_structure_alert` have zero callers. `app/services/structure/writers.py` and `readers.py` are dead. Models in `app/db/models/market.py:648-836` are not consumed.

**Fix** (2 sub-changes):

1. **Delete dead Python code**:
   - `app/repositories/market_repository.py`: remove `get_latest_structure_snapshot`, `replace_structure_snapshot_bundle`, `list_structure_system_judgements`, `list_structure_system_scores`, `list_structure_active_items`, `list_structure_geometry`, `add_structure_event`, `list_structure_events`, `add_structure_alert`, `list_structure_alerts` (lines 1336-1581).
   - `app/db/models/market.py`: remove 7 `Structure*` ORM classes (~lines 648-836). Update `app/db/models/__init__.py` to drop the imports.
   - `app/services/structure/writers.py`: delete file.
   - `app/services/structure/readers.py`: delete file.

2. **Add migration `alembic/versions/0011_drop_dead_structure_tables.py`** that drops the 7 tables. Idempotent: skip if they don't exist.

Verification:
- App starts without import errors.
- `/structure/tab/bundle` returns the same payload shape (response uses `page_snapshot_cache`).
- All tests pass.

## Execution Order

1. Fix C first (lowest risk, cleanup).
2. Fix A (medium risk; touches hot paths but each is mechanical).
3. Fix B last (highest scope; touches 11 instruments × 10 indicators × 4h/1d = 220 background writes per refresh).

After all three:
- `python -m pytest tests/ -q --ignore=slow` → 0 failures.
- `python tests/verify_pages.py --pages ai-strategy,structure-page,indicators` → OK.
- `python tests/inspect_strategy_cold_load.py` → banner shows real data within 30 s, no false "no opportunities" message.

## Files Touched (across all three fixes)

| File | A | B | C |
|---|---|---|---|
| `app/repositories/market_repository.py` | Y | | Y |
| `app/services/market_events_feed.py` | Y | | |
| `app/workers/market_events_feed.py` | Y | | |
| `app/workers/market_event_translation.py` | Y | | |
| `app/workers/precompute_worker.py` | | Y | |
| `app/services/precompute.py` | | Y | |
| `app/services/indicator_monitoring.py` | | Y | |
| `app/api/v1/endpoints/strategy.py` | | Y | |
| `app/monitoring/configs/refresh_policies.yaml` | | Y | |
| `app/db/models/market.py` | | | Y |
| `app/db/models/__init__.py` | | | Y |
| `app/services/structure/writers.py` | | | Y (delete) |
| `app/services/structure/readers.py` | | | Y (delete) |
| `alembic/versions/0011_drop_dead_structure_tables.py` | | | Y (new) |
| Tests: `tests/test_market_repository_upserts.py` | Y | | Y |
| Tests: `tests/test_market_events_feed_per_entry_commit.py` | Y | | |
| Tests: `tests/test_precompute_indicator_branch.py` | | Y | |
| Tests: `tests/test_refresh_policies_4h_1d.py` | | Y | |
| Tests: `tests/test_structure_schema_cleanup.py` | | | Y |

## Risk & Rollback

- **Fix A** writes and reads change behavior: if any test relied on the old SELECT-then-INSERT round-trip pattern, tests may break. Rollback path: revert one repository method at a time.
- **Fix B** adds new background writes that compete with precompute for SQLite lock. Risk: deadlock or rate-limit. Mitigate by limiting per-cycle count to one instrument × 2 timeframes. Rollback: remove the YAML entries (cheap).
- **Fix C** deletes dead code. Worst case: a test that imports `StructureSnapshot` ORM breaks. Rollback: restore the deleted code from git history.

## Out of Scope

- Replacing SQLite with Postgres. Would solve lock contention entirely but requires infrastructure change.
- Unifying `indicator_values` and `indicator_observations` into one table. Different contracts; defer.
- Adding 1w/30d to the technical catalog. Out of scope for this round; tracked separately.

## Verification Plan

1. After each fix: run `pytest tests/test_strategy_*.py tests/test_market_events_feed_per_entry_commit.py tests/test_market_repository_upserts.py tests/test_structure_*.py -q`.
2. After all three: run full subset, expect 0 failures.
3. After all three: run `python tests/inspect_strategy_cold_load.py` (no force=true) — within 60 s the banner must transition from "warming" → "发现 N 个交易机会" or "全部数据已就绪，当前无明确交易方向".
4. After all three: `python tests/verify_pages.py` for ai-strategy, structure-page, indicators — all OK with 0 console errors.