# AI Strategy Cold-Load v2 — Banner State Machine

## Context

Follow-up inspection (`tests/inspect_strategy_cold_load.py`) of the v1 fix
(commit `8c38f76`) showed two compounding bugs on cold load:

**Bug A (frontend)**: After the first scan returned `warming`, the
5-second retry in `loadScan` could STILL get a `warming` response (the
warming cache TTL is 10s). With `_retried=true`, the warming branch was
skipped, falling through to `renderScanResults(data)` which interpreted
the empty matrix as `当前无明确交易机会` — a misleading state because
nothing had actually been computed yet.

**Bug B (backend)**: When the warming cache was read on a subsequent
request, `cache_status` returned `"stale"` (because `expires_at` had
passed) and the endpoint fell through the cache-hit branch with
`payload["cache_meta"]["source"] = "cache"` — overwriting the
`warming` signal. The frontend then saw `cache_meta.source === "cache"`
with an empty matrix and rendered "no opportunities" again.

After both fixes, the inspection shows:

| t | Banner |
|---|---|
| 0.16s | 首次访问，正在后台预热数据缓存，预计 5-10 秒后出结果 [WARMING] |
| 1-30s | (continues polling, banner stays WARMING) |
| 30s+ | 后台仍在预热数据，请点击「刷新扫描」按钮重试 [WARMING give-up] |

The page never falls into the misleading "no opportunities" state. The
user has a clear path forward (click 刷新扫描).

## Goal

On cold direct load:

1. Show the warming banner immediately (works after v1).
2. Keep showing the warming banner — **never** transition to "no
   opportunities" until the backend signals a real result.
3. After ~30s of waiting (6 retries × 5s), give up gracefully with a
   "请点击刷新扫描重试" banner — never "扫描失败" (which implies a
   fault, not just slow warming).
4. Once real data arrives, transition to the normal "发现 N 个交易机会"
   banner.

## Design

### Frontend (`app/static/pages/strategy/index.js`)

Refactor `loadScan` so warming responses return a tagged sentinel
`{ __state: "warming" }` instead of falling through to
`renderScanResults`. New `pollWhileWarming(attempt)` function handles
the bounded retry loop:

```js
async function loadScan(force, opts) {
  // ...
  if (!force && data?.cache_meta?.source === "warming") {
    return { __state: "warming", payload: data };
  }
  renderScanResults(data);
  return data;
}

async function pollWhileWarming(attempt = 0) {
  if (!mounted) return;
  if (attempt >= WARMING_RETRY_LIMIT) {
    renderWarmingStatus("后台仍在预热数据，请点击「刷新扫描」按钮重试");
    return;
  }
  await sleep(WARMING_RETRY_DELAY_MS);
  const result = await loadScan(false, { timeoutMs: 90000 });
  if (result?.__state === "warming") {
    pollWhileWarming(attempt + 1);
  }
}

// In renderStrategy():
const first = await loadScan(false);
if (first?.__state === "warming") pollWhileWarming(0);
```

The warming guard does NOT depend on a `_retried` flag — it applies to
**every** warming response, not just the first.

### Backend — two small fixes

1. **Endpoint cache-hit branch** (`app/api/v1/endpoints/strategy.py`):
   don't overwrite `cache_meta.source` to "cache" when the cached
   payload already has `source === "warming"`. Preserves the signal so
   the frontend can keep polling.

2. **`cache_status()` helper** (`app/services/cache_registry.py`):
   short-circuit `cache_state == "warming"` to return `"warming"`
   instead of falling through to the freshness check. Without this,
   a stale warming record would be reported as `"stale"` and the
   endpoint would fall through to the cold-load short-circuit again.

### Tests

- `tests/test_strategy_frontend_static.py`: 3 new tests
  (polling loop with bound, graceful give-up message, warming guard
  applies to every response).
- `tests/test_strategy_scan_endpoint_resilience.py`: 2 new tests
  (warming source preserved on cache hit; real cache hit still
  overwrites to "cache").

### Verification (all green)

- 1137 passed, 7 skipped, 0 failed.
- `verify_pages.py --pages ai-strategy` OK, no JS errors.
- Cold inspection: warming banner stays for the full 30s, then
  graceful give-up banner appears. No misleading "no opportunities"
  state ever shown.

### Out of scope

- Optimizing the precompute queue to finish faster. That's a deeper
  performance problem (separate spec).
- Polling cadence tuning beyond 5s/6 attempts.

## Risk

- The polling loop can keep the request active for 30s. Acceptable —
  the warming cache prevents each request from blocking more than ~4ms.
- If the page is unmounted mid-poll, we abort cleanly via the
  `if (!mounted) return` guards.
- The give-up banner must NOT say "扫描失败" (which is used elsewhere
  for genuine errors). Pinned by tests.