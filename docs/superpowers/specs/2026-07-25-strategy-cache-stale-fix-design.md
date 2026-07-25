# Strategy Cache Stale-Fix — Design (2026-07-25)

## 0. Context & Symptom

User reported the strategy page's "机会排序" list shows rows whose summary text is

> "4H 数据不足，不能建立最低交易级别判断。"

on **12 of 33** rows, even though a forced rebuild (`/api/v1/strategy/unified?force=true`)
returns a non-empty `timeframe_stack` with six live nodes (1M / 1w / 1d / 4h / 1h / 15m)
and ~162 `signal_coverage` rows. The cache is stale; the engine is healthy.

Concretely the live scan endpoint serves the scanner's stale per-instrument cache:

- `OpportunityScanner.scan_all(...)` (file:
  `app/services/strategy_unified/opportunity_scanner.py`) calls
  `service.build_unified_strategy(iid, force=False)` per cell. That call site has
  **no `force` parameter** in the existing public signature.
- The per-instrument cache written before the 2026-07-25 `[fix-b]` indicator coverage
  commit (which fanned out candle-derived indicators to 4h / 1d for every instrument)
  contains `trade_decision.primary_reason.message = "4H 数据不足…"`.
- The scanner copies `decision.get(...)`-derived strings into the per-row `summary`
  field, propagating that stale text into the user-visible matrix and ranked list.
- The endpoint `/api/v1/strategy/scan?force=true` does **not** fix the issue because
  the per-cell call inside `scan_all` re-uses `force=False`.

Goal: make the user never see a description that contradicts the current data state,
even when indicator data for an `(instrument, timeframe)` pair arrives mid-session.

Non-goals:

- We are NOT rewriting the trade-decision reason dictionary; the engine may still
  return `FOUR_HOUR_DATA_UNAVAILABLE` when data is genuinely missing.
- We are NOT touching the AUDITABLE DECISION card on the detail panel; that card's
  "全是系统内部的逻辑计算文本" complaint is owned by a separate UX track.
- We are NOT introducing a PARTIAL/settled two-stage UX. Today's contract is
  "either the payload is good enough to show, or we show degradation".
- We are NOT changing `ScanItem`'s field shape; the current 17-field dataclass on
  disk is the contract.

## 1. Approach Chosen (Approach B, instrument × timeframe 粒度)

Three orthogonal changes:

1. **Force propagation.** Make `OpportunityScanner.scan_all` accept `force: bool`
   and pass it to every `build_unified_strategy` call. `/scan?force=true` then
   means what it says.
2. **Layer-level cache scrub.** Before `upsert_page_snapshot_cache(..., payload)`,
   run `_scrub_for_cache(payload, is_degraded)`. If `is_degraded=True`, null out
   `trade_decision.primary_reason.message`, `trade_decision.summary`, and every
   `secondary_reasons[*].message`. Engine-side `status`/`side`/`permission` are
   preserved so the frontend can still render the "current direction / leverage"
   cards without leaking the stale rationale.
3. **Indicator-driven cache invalidation (instrument_id × timeframe 粒度).**
   Add a tiny `indicator_freshness_ledger` table. Hook
   `MarketRepository.add_or_update_observation(...)` to bump
   `(instrument_id, timeframe)`'s ledger entry. In
   `get_unified_strategy(...)`, the cache validity test now also requires
   `ledger.last_observation_at <= cache.snapshot_at`. A miss falls through to
   the existing `_guard_cached_strategy` enqueue-hint path. This is the **same**
   granularity as the cache key (`strategy_unified:<instrument_id>`), and finer
   than `(instrument_id, *)` because ledger rows only exist for timeframes the
   strategy actually queries.

## 2. Files to change

| Path | Change |
|---|---|
| `app/services/strategy_unified/opportunity_scanner.py` | Add `force: bool = False` kwarg to `OpportunityScanner.scan_all`. Replace `force=False` literal in the loop with the kwarg. |
| `app/api/v1/endpoints/strategy.py` | Forward request-level `force` to `scanner.scan_all(..., force=force)`. Add indicator-ledger cache-validity check before returning the cached payload; on miss, fall through to existing enqueue path. |
| `app/services/strategy_unified/unified_service.py` | New `_scrub_for_cache(payload, is_degraded) -> dict`. Apply before each `repository.upsert_page_snapshot_cache(...)` call inside `build_unified_strategy`. |
| `app/repositories/market_repository.py` | New `bump_indicator_freshness(instrument_id, timeframe, observed_at)` upsert. New `get_latest_indicator_freshness_for_instrument(instrument_id) -> datetime \| None` (aggregate max over timeframes). Append a single `await self.bump_indicator_freshness(...)` call at the end of `add_or_update_observation` so every writer path automatically takes part in invalidation. |
| `alembic/versions/0012_indicator_freshness_ledger.py` | New alembic migration: `indicator_freshness_ledger(instrument_id, timeframe, last_observation_at)` with PK `(instrument_id, timeframe)`. |
| `app/db/models/market.py` | Register the `IndicatorFreshnessLedger` model. |
| `tests/test_opportunity_scanner_force_propagation.py` | New: monkeypatch `UnifiedStrategyService.build_unified_strategy` and pin that `force=True` is forwarded. |
| `tests/test_unified_service_scrubs_stale_message.py` | New: pin `_scrub_for_cache` removes stale text and preserves `status` / `side` / `permission`. |
| `tests/test_market_repository_indicator_ledger.py` | New: pin `bump_indicator_freshness` upsert + `get_latest_indicator_freshness_for_instrument` returning the max across timeframes. |
| `tests/test_unified_endpoint_indicator_invalidation.py` | New: cache present + `ledger > snapshot_at` → endpoint enqueues hint instead of returning the stale payload. |

## 3. Component design

### 3.1 `_scrub_for_cache(payload, is_degraded)`

```python
def _scrub_for_cache(payload: dict, *, is_degraded: bool) -> dict:
    """Cache-time view of a Unified payload.

    Removes or nulls any human-readable rationale fields whenever the
    payload was built under degraded data conditions, so a stale cache
    hit cannot leak "4H 数据不足…" text after the underlying indicators
    arrive. Engine-level fields (status, side, permission, ...) are
    preserved so the renderer can still show the engine's verdict.
    """
    if not is_degraded:
        return payload
    scrubbed = dict(payload)
    decision = dict(scrubbed.get("trade_decision") or {})
    primary = dict(decision.get("primary_reason") or {})
    primary["message"] = None
    decision["primary_reason"] = primary
    decision["summary"] = None
    decision["secondary_reasons"] = [
        {**r, "message": None} for r in (decision.get("secondary_reasons") or [])
    ]
    scrubbed["trade_decision"] = decision
    return scrubbed
```

The function returns a **shallow copy** with `trade_decision` rebuilt; original
`base_payload` is not mutated, so any post-build in-memory use still sees the full
diagnostic.

### 3.2 `IndicatorFreshnessLedger`

Schema (Alembic migration `0012`):

```sql
CREATE TABLE indicator_freshness_ledger (
    instrument_id   TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    last_observation_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (instrument_id, timeframe)
);
CREATE INDEX ix_ledger_timeframe ON indicator_freshness_ledger (timeframe);
```

A new writer path enters every time `MarketRepository.add_or_update_observation`
runs. The hook is appended **at the end of that method**, so all existing
indicator-monitoring worker paths and any future writer inherit the invalidation
behavior automatically — no per-callsite change.

### 3.3 Cache-validity test in `get_unified_strategy`

`/unified` receives `instrument_id` only (no `timeframe` query param). The cache
key is `strategy_unified:<instrument_id>`. Because *any* `(instrument_id, *)`
indicator-observation arrival can shift the engine's verdict (a fresh 1d EMA
rescales the strategic view), the cache-validity gate aggregates over all ledger
rows for the instrument:

```python
latest_observation = await repository.get_latest_indicator_freshness_for_instrument(
    normalized_instrument,
)
cache_valid = (
    cache is not None
    and cache.payload_json
    and status not in {"missing", "error"}
    and (latest_observation is None or latest_observation <= cache.snapshot_at)
)
if not cache_valid:
    # fall through to the existing enqueue-hint path with reason
    # "strategy_unified_indicator_ledger_stale"
    ...
```

`get_latest_indicator_freshness_for_instrument` performs
`SELECT MAX(last_observation_at) FROM indicator_freshness_ledger WHERE instrument_id = ?`.
When the table is empty for the instrument (very early in cold-start),
`latest_observation is None` and the gate falls back to the existing
`cache_status(cache)` rule — no regression.

### 3.4 Force propagation

```python
class OpportunityScanner:
    async def scan_all(
        self,
        instrument_ids: list[str],
        instrument_codes: dict[str, str],
        *,
        timeframes: tuple[str, ...] = SCAN_TIMEFRAMES,
        force: bool = False,    # <-- new
    ) -> ScanResult:
        ...
        payload = await service.build_unified_strategy(iid, force=force)
        ...
```

Endpoint:

```python
result = await scanner.scan_all(
    instrument_ids, instrument_codes, force=force,
)
```

Cost model: 11 instruments × 3 timeframes = 33 cells. Forced build is ~1.5 s/cell
in production (per the previous test runs), so the worst-case scan is ~50 s. That
matches the user-accepted scanning cost.

## 4. Data flow

```text
[user clicks 刷新扫描]
        |
        v
GET /api/v1/strategy/scan?force=true
        |
        v
get_strategy_scan(force=true)
        |
        v
OpportunityScanner.scan_all(force=True)
        |
        +-- for each (iid, tf):
        |     UnifiedStrategyService.build_unified_strategy(iid, force=True)
        |       |
        |       +-- compute nodes / dims / horizons / decision
        |       +-- _scrub_for_cache(base_payload, is_degraded=is_degraded)
        |       +-- repository.upsert_page_snapshot_cache(cache_key, payload=scrubbed)
        |
        v
result_dict = dataclasses.asdict(result)   # 17-field ScanItem shape unchanged
        |
        +-- repository.upsert_page_snapshot_cache("strategy_scan", result_dict)
        v
200 OK with fresh matrix / ranked

[Meanwhile, /api/v1/strategy/unified?instrument_id=X&timeframe=4h]
        |
        v
cache hit?
        |
        +-- ledger.last_observation_at <= cache.snapshot_at ? OK
        +-- ledger.last_observation_at  > cache.snapshot_at ? INVALIDATE
                -> enqueue hint("strategy_unified_indicator_ledger_stale")
                -> rebuild or fall through

[Indicator worker writes a new observation]
        |
        v
MarketRepository.add_or_update_observation(obs)
        |
        +-- sqlite_insert(IndicatorObservation).on_conflict_do_update(...)
        +-- self.bump_indicator_freshness(obs.instrument_id, obs.timeframe, obs.observation_ts)
        v
ledger row updated -> next /unified call sees the new value
```

## 5. Error handling

| Failure | Handling |
|---|---|
| `bump_indicator_freshness` raises | `logger.warning(...)`; observation upsert still commits. Invalidation is best-effort; the next soft-failure is `page_snapshot_cache.expires_at`. |
| `get_latest_indicator_freshness` raises | `logger.warning(...)`; treat as `None` (i.e. the cache validity gate stays at the existing `cache_status` rule). |
| `_scrub_for_cache` raises | Should not — pure dict manip — but if it does, the `upsert_page_snapshot_cache` call is wrapped in `try/except` already (see `app/api/v1/endpoints/strategy.py` line 521+). |
| `force=true` rebuild throws per-cell | Per-cell `try/except` already exists inside `scan_all` (line 95 of opportunity_scanner.py). Cell is skipped; ranked list shrinks; cache_meta.instruments_scanned is honest. |

## 6. Test plan

1. **Static checks**:
   - `python -c "import py_compile; py_compile.compile(<path>, doraise=True)"`
     for `opportunity_scanner.py`, `unified_service.py`, `market_repository.py`,
     `endpoints/strategy.py`, `models/market.py`.
   - `node --check` is N/A (no JS touched).
2. **Unit tests** (`pytest -q tests/test_opportunity_scanner_force_propagation.py
   tests/test_unified_service_scrubs_stale_message.py
   tests/test_market_repository_indicator_ledger.py
   tests/test_unified_endpoint_indicator_invalidation.py`):
   - `scan_all(force=True)` invokes `build_unified_strategy(..., force=True)` for every cell.
   - `_scrub_for_cache` removes stale text under `is_degraded=True`, leaves
     `status` / `side` / `permission` intact, and **does not mutate** the input dict.
   - `bump_indicator_freshness` upserts `(instrument_id, timeframe)` rows and
     `get_latest_indicator_freshness` returns the most recent observed_at.
   - `/unified` endpoint with a stale cache + new ledger row triggers an enqueue
     hint instead of returning the cached payload.
3. **Live verification** after restart on port 8002:
   - `curl /api/v1/strategy/scan?force=true` → matrix[*].summary must not contain
     "4H 数据不足".
   - Insert a synthetic `IndicatorObservation` for `bnb-usdt-perp / 4h`
     (`observation_ts > cache.snapshot_at`) → subsequent
     `curl /api/v1/strategy/unified?instrument_id=bnb-usdt-perp&timeframe=4h` must
     enqueue hint and rebuild.
4. **Frontend verification** (AGENTS.md §六.2 — this is an architecture change
   touching the cache + endpoint plumbing):
   - `python tests/verify_pages.py` (full 9 pages). Required, not optional.
   - `python tests/verify_pages.py --pages ai-strategy` as a focused sanity
     check before the full run.
5. **Regression**:
   - `pytest tests/ -q` (full test suite). Existing
     `tests/test_strategy_scan_endpoint_resilience.py`,
     `tests/test_refresh_policies_4h_1d.py`,
     `tests/test_indicator_seeding_per_instrument.py`, and
     `tests/test_strategy_market_context_static.py` must still pass.

## 7. Rollout

Single PR (this is one logical change spanning scan, endpoint, repository,
migration). Backend restart required (uvicorn --reload picks up Python changes
but the new alembic migration needs explicit `alembic upgrade head`). After
restart, no warm-up is necessary — the cache invalidation logic takes effect on
the next request per (instrument, timeframe).

## 8. Risks & open questions

| Risk | Mitigation |
|---|---|
| Alembic was previously skipped (the codebase has 0011 already merged). Need to confirm the `IndicatorFreshnessLedger` model imports cleanly into the SQLAlchemy metadata. | Migration test runs `alembic upgrade head` in CI; if it fails, the PR is blocked. |
| `add_or_update_observation` is on the hottest indicator write path; even a tiny extra round-trip affects throughput. | The bump is one `INSERT OR UPDATE` on the ledger PK; SQLite WAL handles this with single-digit microseconds. Profile if p99 regresses. |
| Cache scrub might break consumers that read `trade_decision.primary_reason.message` from cache (none today, but...) | None today. The adapter at `app/static/pages/strategy/adapter.js` does not read `primary_reason.message`. |
| Force=true scan ~50 s might exceed browser timeout on slow networks. | Tracked separately; current behavior already accepts up to ~60 s for warm-rebuild cold loads, and the frontend shows a "刷新中" spinner. |
| User-visible cache miss means a brief "n/a" placeholders for one render cycle. Acceptable? | Yes; matches existing "等待后台重建" copy in `renderDecisionAudit.js` and `_degraded_payload`. |
