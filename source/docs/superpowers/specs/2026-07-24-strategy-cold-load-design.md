# AI Strategy Page — Cold-Load Reliability

## Context

User reports: "AI策略页有问题，一直加载不出来结果。我看了各个页面，还是老生常谈的问题。我不点开就不抓取对应的数据开始计算，这种情况下AI策略页自然就得不到数据进行多空判定。"

Translated: *"The AI Strategy page has a problem — it never loads results. Same old issue across pages — if I don't open them, the data isn't fetched and calculations don't start. So the Strategy page can't get data to make long/short decisions."*

Verified reproduction:

- `GET /api/v1/strategy/scan?force=false` (cold, no scan cache) → **68.0s** (eventually HTTP 200 with valid data).
- `GET /api/v1/strategy/scan?force=true` on cold cache → also 68s (has to rebuild everything).
- Frontend `getStrategyScan({ timeoutMs: 60000 })` → **60s timeout** (api.js#640).
- Backend eventually returns 200 but the frontend already aborted at 60s → "扫描失败，请稍后重试".
- After the first successful scan, subsequent calls take ~4ms (cache hit).
- After workers warm caches once, even `force=true` scans take ~1s.

### Root causes (in priority order)

1. **No `prewarmStrategy()` call from the strategy page mount.** The `/strategy/prewarm` endpoint exists explicitly for this purpose and its docstring reads:
   > "Called by the SPA on mount when the strategy payload is missing or degraded."
   But `app/static/pages/strategy/index.js` never invokes `api.prewarmStrategy(...)`. Only the daily first-page middleware queues a warmup, and it does so after a **5-second delay**. The strategy page fires `loadScan(false)` immediately, racing the warmup.

2. **Backend scan endpoint has no try/except envelope.** Any exception that escapes `OpportunityScanner.scan_all()`'s per-cell catch (e.g. cache write failure, instrument list failure, db session error) becomes an HTTP 500. The frontend flattens that into the same Chinese error banner.

3. **Cold scan latency exceeds frontend timeout by ~13%.** The scanner calls `build_unified_strategy(force=False)` 3× per instrument (once per timeframe), and each call rebuilds market context from analysis / monitoring / macro / structure / derivatives / onchain — many of which are themselves cold. With 11 instruments × 3 timeframes = 33 cells, each rebuilding fresh, total wall time is ~68s.

4. **No graceful "warming" UI state.** The frontend shows "正在计算各品种各周期策略..." which is identical whether scan is in flight, scan is warming, or scan just failed. User can't tell whether to wait or to refresh.

5. **SQLite lock contention.** Logs show `(sqlite3.OperationalError) database is locked` from `precompute task failed for strategy_bundle:btc-usdt-perp:4h:v3` and `market event translation worker failed (0)`. This is a secondary issue but worth a small fix.

## Goal

Cold direct-load of the AI Strategy page should reliably show **real opportunities** within ~10s (with a clear "warming up" indicator while caches build), and never produce the false-negative "扫描失败" banner when the underlying endpoint would eventually return data.

Out of scope: changing the unified-strategy service's deep semantics, fixing macro provider staleness, addressing SQLite lock at the SQLAlchemy layer.

## Design

### Frontend (the load-bearing fix)

`app/static/pages/strategy/index.js`:

1. **On mount, call `api.prewarmStrategy("btc-usdt-perp")` first** — fire-and-forget, 3s timeout (matches the existing endpoint), do not await. Do this BEFORE `loadScan(false)`.
   - If prewarm returns `accepted=true`, schedule a deferred `loadScan` call 4-6 seconds later (so the warmup has time to start populating caches).
   - If prewarm returns `accepted=false` or fails, fall through to immediate `loadScan` as today.

2. **Show a "warming" status banner while waiting.** Distinct from the loading dots. Text: `正在预热数据缓存，预计 5-10 秒后出结果` with an animated dot.

3. **Increase frontend timeout for the cold scan.** Bump from 60s to 120s for the very first scan only. After the first successful response, revert to 60s.

4. **Treat 504/timeout on the first scan as a soft failure.** Don't show "扫描失败". Instead show `后台预热中，请 10 秒后点击刷新扫描` and keep the empty matrix visible. Add a manual refresh button.

5. **Add a `force` parameter to the auto-scan.** When the user clicks 刷新扫描, pass `force=true`. Don't auto-`force` on mount.

6. **Retry once on transient network failure** (e.g. `ERR_NETWORK_CHANGED`, HTTP 5xx) before showing the error banner. One retry, with `force=false`, after a 2s delay.

### Backend (smaller fix)

`app/api/v1/endpoints/strategy.py#get_strategy_scan`:

1. **Wrap the entire body in try/except.** On any uncaught exception, log it and return a degraded `ScanResult` (empty matrix + empty ranked + `cache_meta.source="error"` + a `cache_meta.message` describing the error). HTTP stays 200.

2. **Don't fail-fast on cache write errors.** If `upsert_page_snapshot_cache(...)` raises, log and still return the result.

3. **Add a `warming` short-circuit.** If `cache is None and not force`, kick off prewarm + return an empty `ScanResult` with `cache_meta.source="warming"` and HTTP 200, so the frontend can show its "warming" UI instead of holding the connection for 68s. Cache TTL is currently 60s in api.js; the empty warming response should also be cached briefly (e.g. 10s) to avoid re-triggering.

### Out-of-band: tighten frontend timeout defaults

`app/static/core/api.js#getStrategyScan`: keep the 30s default but make sure callers can override. The strategy page will pass 120000.

### SQLite lock (cheap mitigation)

In the precompute worker failure log path (`app/services/precompute.py`), the failures are logged but the task isn't retried or scheduled to back off. Add a 1s sleep before re-queueing failed tasks on `OperationalError("database is locked")` to let concurrent writers finish.

This is a low-risk polish. If it doesn't measurably help, revert.

## Tests

### Frontend (static)

In `tests/test_strategy_frontend_static.py` add:

1. `test_strategy_index_prewarms_on_mount` — assert that `index.js` calls `api.prewarmStrategy(...)` (or fires a prewarm request) before / alongside `loadScan`.
2. `test_strategy_index_uses_120s_timeout_for_first_scan` — assert the cold timeout is bumped.
3. `test_strategy_index_does_not_force_on_mount` — assert the auto-scan is non-forced.
4. `test_strategy_index_retries_once_on_transient_error` — assert there's a retry path with `force=false`.

### Backend (pytest)

In a new file `tests/test_strategy_scan_endpoint_resilience.py`:

1. `test_scan_returns_degraded_result_on_unexpected_exception` — patch `OpportunityScanner.scan_all` to raise; expect HTTP 200 with empty matrix + `cache_meta.source="error"`.
2. `test_scan_returns_warming_when_cache_empty` — patch cache lookup to return None; expect HTTP 200 with empty matrix + `cache_meta.source="warming"` and verify prewarm endpoint was called.
3. `test_scan_does_not_fail_on_cache_write_error` — patch `upsert_page_snapshot_cache` to raise; expect HTTP 200.
4. `test_scan_keeps_returning_5xx_free` — fire 20 concurrent scans; expect zero 5xx responses.

## Risk

- **Prewarm side effects**: prewarm kicks off background work; calling it from every page mount could spam the precompute queue. Mitigate by only firing it once per session (use a module-level `let prewarmed = false` flag in `index.js`).
- **Warming short-circuit**: returning empty `ScanResult` could surprise downstream callers who expect at least one cell. Mitigate by emitting a `cache_meta.message` field that consumers can read.
- **Retry once**: a stuck endpoint will now block for `2s + timeoutMs` instead of just `timeoutMs`. Bounded — single retry, single extra round trip.

## Verification

After implementation:

1. `pytest tests/test_strategy_frontend_static.py tests/test_strategy_scan_endpoint_resilience.py -q` → all green.
2. `pytest tests/ -q --ignore=...slow...` → 0 failures.
3. `python tests/verify_pages.py --pages ai-strategy --skip-spa` → OK.
4. `python tests/verify_pages.py --pages ai-strategy` (full SPA) → OK.
5. Cold-load smoke: stop backend, restart, immediately `curl /api/v1/strategy/scan?force=false` → response within 10s with `cache_meta.source` either `warming` or `cache` (never a hang > 60s).
6. UI smoke: open `/strategy-page` in browser, see warming banner → opportunities within 10s.

## Rollback

If prewarm-from-mount causes regressions, drop the `prewarmStrategy()` call from `index.js`. The warming short-circuit on the backend is independently safe and should stay.