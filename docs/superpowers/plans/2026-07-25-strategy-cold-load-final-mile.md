# Implementation Plan — Three Final-Mile Cold-Load Fixes

## Pre-flight

- [ ] Verify the spec doc list (4 docs):
  - `docs/superpowers/specs/2026-07-25-strategy-cold-load-final-mile.md` (umbrella)
  - `docs/superpowers/specs/2026-07-25-fix-c-drop-structure-dead-schema.md` (Fix C)
  - `docs/superpowers/specs/2026-07-25-fix-a-precompute-sqlite-contention.md` (Fix A)
  - `docs/superpowers/specs/2026-07-25-fix-b-indicator-coverage.md` (Fix B)
- [ ] Confirm `pricing/web` running: `python -m uvicorn app.main:app --port 8009 --log-level info` ready to inspect.
- [ ] Confirm DB tooling works:
  ```bash
  python -c "import sqlite3; conn=sqlite3.connect('runtime/data/trading_system.db'); cur=conn.cursor(); cur.execute('SELECT COUNT(*) FROM indicator_monitoring_policies'); print(cur.fetchone())"
  ```

## Execution order

**Fix C → Fix A → Fix B**.

Rationale:
- C is pure cleanup, lowest risk, isolated.
- A introduces contention reductions across hot paths; each change is small but spread across many files.
- B adds 220 background policy rows + new YAML entries; least-coupled change but biggest scope.

Each fix is a separate commit so rollback is easy.

---

## Step 1 — Fix C: drop dead structure_snapshot schema

### 1.1 Delete dead repository methods
Open `app/repositories/market_repository.py` and remove (after confirming no callers with `grep -rn "replace_structure_snapshot_bundle\|get_latest_structure_snapshot\|list_structure_" app/ tests/`):
- Lines 1336-1581 (the entire block of `get_latest_structure_snapshot`, `replace_structure_snapshot_bundle`, `list_structure_*`, `add_structure_*`).

### 1.2 Delete dead ORM models
Open `app/db/models/market.py` and remove the 7 `Structure*` classes (after `MarketEvent` etc.). Run `grep -n "class Structure" app/db/models/market.py` to find them.

Update `app/db/models/__init__.py` to drop the matching imports/re-exports.

### 1.3 Delete dead helpers
- Delete `app/services/structure/writers.py`.
- Delete `app/services/structure/readers.py`.

### 1.4 Add drop migration
Author `alembic/versions/0011_drop_dead_structure_tables.py`:

```python
"""Drop the structure_* tables — superseded by page_snapshot_cache.

Revision ID: 0011_drop_dead_structure_tables
Revises: <last revision id>
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_drop_dead_structure_tables"
down_revision = "0010_strategy_unified"  # adjust to actual last revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in [
        "structure_alerts",
        "structure_events",
        "structure_geometry",
        "structure_active_item",
        "structure_system_scores",
        "structure_system_judgement",
        "structure_snapshot",
    ]:
        if table in inspector.get_table_names():
            op.drop_table(table)


def downgrade() -> None:
    # Recreate empty tables matching original schema (best-effort).
    # Future revisions can recover from here if needed.
    pass
```

Find the actual last revision with `ls alembic/versions/`.

### 1.5 Tests
Author `tests/test_structure_schema_cleanup.py`:
```python
def test_no_dead_references_in_active_code():
    import app.repositories.market_repository as mr
    assert not hasattr(mr, "replace_structure_snapshot_bundle")
    assert not hasattr(mr, "get_latest_structure_snapshot")

def test_writers_module_gone():
    p = Path("app/services/structure/writers.py")
    assert not p.exists(), "writers.py should be deleted"

def test_readers_module_gone():
    p = Path("app/services/structure/readers.py")
    assert not p.exists(), "readers.py should be deleted"

def test_oracle_models_removed():
    import app.db.models.market as m
    for name in [
        "StructureSnapshot",
        "StructureSystemJudgement",
        "StructureSystemScore",
        "StructureActiveItem",
        "StructureGeometry",
        "StructureEvent",
        "StructureAlert",
    ]:
        assert not hasattr(m, name), f"model {name} should be removed"
```

### 1.6 Verify
```bash
python -m pytest tests/test_structure_schema_cleanup.py tests/test_structure*.py tests/test_chip*.py -q
python tests/verify_pages.py --pages structure-page
alembic upgrade head   # idempotent
```

---

## Step 2 — Fix A: precompute SQLite contention

### 2.1 Convert SELECT-then-INSERT to single-statement upserts

For each method below, replace the SELECT-then-INSERT pattern with `sqlite_insert(...).on_conflict_do_update(...)`:

- `app/repositories/market_repository.py:277` `upsert_page_snapshot_cache` — key `cache_key`
- `app/repositories/market_repository.py:462` `add_indicator_value`
- `app/repositories/market_repository.py:613` `upsert_translation_cache`
- `app/repositories/market_repository.py:650` `upsert_translation_text_cache`
- `app/repositories/market_repository.py:678` `upsert_translation_job`
- `app/repositories/market_repository.py:706` `upsert_market_event_translation_map`
- `app/repositories/market_repository.py:781` `add_market_event_links` — use `INSERT OR IGNORE` after adding unique constraint `(event_id, instrument_id)`
- `app/repositories/market_repository.py:853` `upsert_indicator_definition`
- `app/repositories/market_repository.py:905` `upsert_monitoring_policy`
- `app/repositories/market_repository.py:992` `add_or_update_observation` — already has `dedupe_key` unique constraint
- `app/repositories/market_repository.py:1115` `upsert_alert_rule`
- `app/repositories/market_repository.py:1225` `upsert_macro_event` — add unique constraint
- `app/repositories/market_repository.py:1276` `upsert_macro_source_health`

Helper template (reusable across all repos):
```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

def _on_conflict(stmt, **update_fields):
    return stmt.on_conflict_do_update(
        index_elements=list(update_fields.keys()),
        set_={k: getattr(stmt.excluded, k) for k in update_fields},
    )
```

### 2.2 Split `market_events_feed` per-entry commit

Refactor `app/services/market_events_feed.py:52-118`:
- Phase 1 (no DB session): fetch all feeds in parallel with `httpx.AsyncClient` + `asyncio.gather`.
- Phase 2 (per-entry session): for each entry, open a fresh short session, do the 2 writes, commit.

Update `app/workers/market_events_feed.py:35-49` to drop the outer session.

### 2.3 Split `market_event_translation` read / network / write

Refactor `app/workers/market_event_translation.py:155-210`:
- Phase 1: read event into a local dict, commit session, release lock.
- Phase 2: network call (no lock held).
- Phase 3: open new session, write translation result, commit.

### 2.4 Tests

`tests/test_market_repository_upserts.py`:
- `test_upsert_page_snapshot_cache_is_single_round_trip` — patch `session.execute`, assert exactly 1 call per upsert.
- `test_upsert_*_preserves_existing_row_on_conflict` — insert twice with same key, assert the second updates.

`tests/test_market_events_feed_per_entry_commit.py`:
- `test_sync_default_feeds_emits_per_entry_commits` — count session.commit() calls = N entries.
- `test_sync_default_feeds_holds_short_transactions` — for each entry, lock-hold time < 50 ms.

`tests/test_market_event_translation_per_event_split.py`:
- `test_translate_one_releases_writer_lock_during_network` — mock translator with `asyncio.sleep(0.5)`; while the sleep is in flight, no DB connection from this worker should be open.

### 2.5 Verify
```bash
python -m pytest tests/test_market_repository_upserts.py tests/test_market_events_feed_per_entry_commit.py tests/test_market_event_translation_per_event_split.py -q
python -u -m uvicorn app.main:app --port 8009 &
# Wait for precompute to run
sleep 60
curl http://127.0.0.1:8009/api/v1/strategy/scan?force=true
# Expect: HTTP 200 with matrix populated; no database is locked errors in /tmp/uv.log
grep -i "database is locked" /tmp/uv.log | wc -l
# Expect: small number (ideally 0)
```

---

## Step 3 — Fix B: indicator coverage for 4h/1d

### 3.1 Add 4h/1d entries to refresh_policies.yaml

Append to `app/monitoring/configs/refresh_policies.yaml` under `technical:` (10 indicators × 2 timeframes = 20 entries):

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
# ... similarly for ema_50, ema_200, adx_14, macd_12_26_9,
#     rsi_14, atr_14, natr_14, bbands_20_2, obv
```

### 3.2 Per-instrument expansion in `seed_defaults`

In `app/services/indicator_monitoring.py:192-205`, replace the BTC-only default with a `repository.list_instruments()` loop:

```python
instruments = await repository.list_instruments()
for instrument in instruments:
    if not instrument.instrument_id:
        continue
    for indicator_key, definition in technical_catalog.items():
        for timeframe in definition.get("supported_timeframes", []):
            if timeframe in {"1m", "5m", "1h", "4h", "1d"}:
                await self.upsert_monitoring_policy(...)
```

Skip `seed_defaults`'s existing `provider_settings` lookup that filters down to one instrument; expand to all configured.

### 3.3 (Optional) Wire indicator fill into strategy prewarm

In `app/services/precompute.py:_execute_task` around line 793, add:

```python
elif page_type == "indicators":
    indicator_service = IndicatorService(repository)
    for instrument_id in instrument_ids:
        for tf in SCAN_TIMEFRAMES:
            try:
                await indicator_service.ensure_indicator_data(
                    instrument_id=instrument_id,
                    timeframe=tf,
                    auto_calculate=True,
                )
            except Exception:
                logger.exception("indicator_fill failed %s %s", instrument_id, tf)
```

Update `app/api/v1/endpoints/strategy.py:403-439` to add `"indicators"` to candidates.

Skip if B.3 risks SQLite contention (likely). B.1 + B.2 alone should suffice.

### 3.4 Tests

`tests/test_refresh_policies_4h_1d.py`:
- `test_yaml_has_4h_entries_for_all_10_indicators`
- `test_yaml_has_1d_entries_for_all_10_indicators`
- `test_yaml_no_1w_30d_technical_entries_added`

`tests/test_indicator_seeding_per_instrument.py`:
- `test_seed_defaults_creates_per_instrument_policies` — mock 3 instruments, assert upsert called 3 × 10 × 3 = 90 times.

### 3.5 Verify
```bash
python -m pytest tests/test_refresh_policies_4h_1d.py tests/test_indicator_seeding_per_instrument.py -q
# After startup, count policies
python -c "import sqlite3; c=sqlite3.connect('runtime/data/trading_system.db').cursor(); c.execute(\"SELECT COUNT(*) FROM indicator_monitoring_policies WHERE timeframe IN ('4h','1d')\"); print(c.fetchone())"
# Expect: >= 110
python tests/verify_pages.py --pages indicators,ai-strategy
```

---

## Step 4 — End-to-end verification

After all three fixes:

1. `python -m pytest tests/ -q --ignore=slow` → expect 0 failures, ~1146+ tests passing.
2. `python tests/verify_pages.py` → all 9 pages OK, 0 console errors.
3. Cold-load smoke:
   ```bash
   # Wipe scan cache
   python -c "import sqlite3; conn=sqlite3.connect('runtime/data/trading_system.db'); conn.cursor().execute(\"DELETE FROM page_snapshot_cache WHERE cache_key LIKE '%strategy_scan%' OR page_type = 'strategy_scan'\"); conn.commit()"
   # Restart backend
   python -u -m uvicorn app.main:app --port 8009 --log-level info &
   sleep 12
   # First hit (warming)
   time curl -s http://127.0.0.1:8009/api/v1/strategy/scan?force=false
   # Expect: HTTP 200, source='warming', < 5s
   # Wait for precompute worker
   sleep 30
   # Second hit (now real data)
   time curl -s http://127.0.0.1:8009/api/v1/strategy/scan?force=false
   # Expect: HTTP 200, source='cache', matrix populated, opportunities_found > 0
   ```
4. Run `python tests/inspect_strategy_cold_load.py` — banner must transition to "发现 N 个交易机会" or "全部数据已就绪" within 60 s.

---

## Step 5 — Commit

Three commits, in execution order. Each tags the spec doc.

```bash
git add app/repositories/market_repository.py app/db/models/market.py app/db/models/__init__.py
git add <deletion of writers.py, readers.py>
git add alembic/versions/0011_drop_dead_structure_tables.py
git add tests/test_structure_schema_cleanup.py
git add docs/superpowers/specs/2026-07-25-fix-c-drop-structure-dead-schema.md
git add docs/superpowers/specs/2026-07-25-strategy-cold-load-final-mile.md

git commit -m "[fix-c] drop dead structure_snapshot schema

The 7 structure_* SQL tables are never written by current code;
StructureSnapshotService persists to page_snapshot_cache instead.
remove_structure_snapshot_bundle, get_latest_structure_snapshot,
list_structure_*, add_structure_event, add_structure_alert have zero
callers. Same for writers.py and readers.py.

Cleanup:
- 10 dead repository methods deleted (market_repository.py)
- 7 dead ORM models deleted (db/models/market.py) + __init__ exports
- writers.py and readers.py deleted
- migration 0011_drop_dead_structure_tables.py drops the tables
  idempotently

Tests: tests/test_structure_schema_cleanup.py

Behavior: zero change. /structure/tab/* endpoints still return the
same payload shape, sourced from page_snapshot_cache.

Spec: docs/superpowers/specs/2026-07-25-fix-c-drop-structure-dead-schema.md"

git add app/repositories/market_repository.py
git add app/services/market_events_feed.py app/workers/market_events_feed.py
git add app/workers/market_event_translation.py
git add tests/test_market_repository_upserts.py
git add tests/test_market_events_feed_per_entry_commit.py
git add tests/test_market_event_translation_per_event_split.py
git add docs/superpowers/specs/2026-07-25-fix-a-precompute-sqlite-contention.md

git commit -m "[fix-a] precompute SQLite contention: per-row upserts + split sessions

market_events_feed.sync_default_feeds opened one session and held it
across every RSS feed × entry × (SELECT+INSERT) round-trip. Other writers
(precompute, indicator_monitor, market_event_translation) all queued
behind this single transaction on SQLite's writer mutex, throwing
'OperationalError: database is locked' after busy_timeout=30 s.

Reductions in writer-lock hold time:

1. Convert 13 SELECT-then-INSERT repository methods to single-statement
   sqlite_insert(...).on_conflict_do_update(...) upserts. Each removes
   1 round-trip per write.

2. Split market_events_feed.sync_default_feeds per-entry commit:
   - Phase 1: fetch all feeds in parallel (no DB lock)
   - Phase 2: per-entry short session, commit after each entry
   Worker loses its outer session.

3. Split market_event_translation per-event into read/network/write
   so the slow translation API call doesn't hold the writer lock.

Tests:
- test_market_repository_upserts: assert one-round-trip per upsert
- test_market_events_feed_per_entry_commit: assert N commits = N entries
- test_market_event_translation_per_event_split: assert no writer lock
  during network phase

Behavior: identical persist semantics, faster concurrent writes.

Spec: docs/superpowers/specs/2026-07-25-fix-a-precompute-sqlite-contention.md"

git add app/monitoring/configs/refresh_policies.yaml
git add app/services/indicator_monitoring.py
git add tests/test_refresh_policies_4h_1d.py
git add tests/test_indicator_seeding_per_instrument.py
git add docs/superpowers/specs/2026-07-25-fix-b-indicator-coverage.md

git commit -m "[fix-b] indicator coverage: add 4h/1d technical policies + per-instrument seeding

Refresh_policies.yaml only listed technical candles for 1m/5m/1h —
empty indicator_observations for 4h/1d/1w/30d meant strategy's
multi-timeframe structure engine fell back to 'no observation' = zero
confidence on those horizons, dragging long_score/short_score toward
50/50 and biasing the scan toward 'WAIT'/'NO_EDGE' for every cell.

Changes:
1. refresh_policies.yaml: 10 indicators × 2 new timeframes (4h, 1d)
   = 20 new entries at 14400s / 86400s cadence.
2. seed_defaults() iterates repository.list_instruments() instead of
   defaulting to btc-usdt-perp, creating per-instrument policy rows
   for all enabled instruments.
3. (Optional B.3 — deferred) wire IndicatorService.ensure_indicator_data
   into the strategy prewarm.

Tests:
- test_refresh_policies_4h_1d: YAML has all 10 indicators at 4h + 1d,
  no 1w/30d entries.
- test_indicator_seeding_per_instrument: seed_defaults creates policy
  rows for every enabled instrument × timeframe.

Behavior: 4h/1d indicator_observations populate within 60-120 s of
uptime. Strategy's long_score/short_score for 4h/1d horizons now
reflect real EMA/RSI/MACD data, not zero-confidence fallbacks.

Spec: docs/superpowers/specs/2026-07-25-fix-b-indicator-coverage.md"
```

---

## Risk Summary

| Fix | Risk | Mitigation | Rollback |
|---|---|---|---|
| C | Code deletion may break tests referencing dead imports | Pin tests pre-commit | Revert one deletion at a time |
| A | Upsert conversion changes behavior on race conditions | Unique constraint guarantees idempotency | Revert one repository method |
| B | 220 background policy rows + 6 daily writes per cycle | Cadences 14400s+86400s, low CPU | Revert YAML entries (cheap) |