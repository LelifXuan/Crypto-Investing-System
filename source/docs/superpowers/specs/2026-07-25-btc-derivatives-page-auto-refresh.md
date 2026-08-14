# BTC Derivatives Page Auto-Refresh — Design (2026-07-25)

## 0. Context & Symptom

User complaint: 墙位迁移 (key-levels-history) chart on the BTC derivatives page stops at
2026-07-24 18:18 in their browser even when the live `/api/v1/btc-derivatives/dashboard`
endpoint returns 54 labels, the last being **2026-07-25T11:58:26 UTC**.

Phase 1 evidence:
- Live API labels (sampled):
  - `2026-07-23T03:03:56.735194+00:00` (first)
  - `2026-07-25T11:58:26.576555+00:00` (last)
- `key_levels_history` chart has 54 points; the dataset matches reality.
- The current `app/static/pages/btc_derivatives.js` does **not poll**:
  - `grep -n "setInterval\|polling" app/static/pages/btc_derivatives.js` → 0 matches.
  - `loadDashboard()` only runs on page mount (line 1309), on user click of "刷新"
    (line 1153), or on first cold-load (line 1275).
- The page has a proper `unmount()` (line 1314) which already calls
  `requestController?.abort()` — proving the lifecycle hooks were designed for
  long-lived work, but no timer was ever wired in.

So the user's report is the natural consequence: the page is a one-shot reader; if
they leave it open across midnight, the dashboard's wall-migration chart freezes on
whatever historical labels were returned at first load. Top-table "expiry dates" look
fresh because those are forward-dated contract expiries (2027-06-25 etc.), which are
inherently stable and don't time-stamp-decay.

The expiry matrix on the top half of the same page renders dates out to 2027-06-25
because those are *contract expiries* (forward), not *observation timestamps*. They
do not age. The wall-migration chart shows *observation timestamps* and ages.

The legitimate UX expectation is: the user opens the page, walks away, returns an
hour later, and the chart catches up without having to manually click "刷新".

## 1. Goal & Non-goals

**Goal**: Wall-migration chart (and the whole dashboard) auto-refresh at a sensible
cadence without user interaction, with strict abort/lifecycle guard so the timer is
cancelled on unmount/pause and re-armed on resume.

**Non-goals**:
- We are NOT introducing server-sent events or WebSockets; a plain `setInterval`
  with `requestController` abort is enough.
- We are NOT changing the existing "刷新" button semantics; manual refresh still
  runs `loadDashboard({ refresh: true })` which is heavier (job queue + force rebuild).
  The new auto-refresh reads cache (no force), which is the cheap path.
- We are NOT changing the wall-migration chart's data shape or any backend cache key.

## 2. Approach

A single lightweight polling loop in `renderBtcDerivatives()`:

```js
let autoRefreshTimer = null;
const AUTO_REFRESH_MS = 60_000;
function scheduleAutoRefresh() {
  clearTimeout(autoRefreshTimer);
  autoRefreshTimer = setTimeout(async () => {
    if (document.hidden) return scheduleAutoRefresh();
    try {
      await loadDashboard();  // cache-first; cheap
    } catch (e) {
      if (e?.name !== "AbortError") console.warn("btc:auto-refresh", e);
    } finally {
      scheduleAutoRefresh();
    }
  }, AUTO_REFRESH_MS);
}
```

And wire `scheduleAutoRefresh()` from:
- `renderBtcDerivatives` after the initial mount.
- `resume()` so navigating back to the page restarts the timer.
- `unmount()` and `pause()` call `clearTimeout(autoRefreshTimer)` and `abort()`.

`document.hidden` check ensures we don't run the refresh when the tab is in the
background — that would waste cycles and the next visit will run it anyway.

## 3. Files to change

| Path | Change |
|---|---|
| `app/static/pages/btc_derivatives.js` | Add `AUTO_REFRESH_MS = 60_000` constant + `scheduleAutoRefresh() / clearAutoRefresh()` helpers. Wire into mount/unmount/pause/resume. |
| `tests/test_btc_derivatives_frontend_static.py` | Add `test_btc_derivatives_page_auto_refreshes_via_interval` to pin: page exposes `AUTO_REFRESH_MS`, calls `scheduleAutoRefresh`, aborts on unmount, restarts on resume. |

## 4. Test plan

1. **Static checks**:
   - `python -c "import py_compile; py_compile.compile('tests/test_btc_derivatives_frontend_static.py', doraise=True)"`.
   - `python -m pytest tests/test_btc_derivatives_frontend_static.py -q` (must pass before and after).
2. **Live verification**:
   - Open `http://127.0.0.1:8002/btc-derivatives-page`, wait ~70 s, confirm the
     chart's last x-axis tick reads today's date (Asia/Shanghai). Use
     `tests/verify_pages.py --pages btc-derivatives`.
3. **Architecture compliance (AGENTS.md §六.4)**: this touches SPA lifecycle — run
   `tests/verify_pages.py` (full 9 pages) before declaring done.

## 5. Risks & open questions

| Risk | Mitigation |
|---|---|
| New timer competes with manual "刷新" button | Manual click also calls `loadDashboard()`, which already aborts prior in-flight requests via `requestController.abort()`. The polling timer is no different. |
| Browser tab throttling `setTimeout(fn, 60_000)` to 1+ minute | Acceptable: 60 s cadence matches the "naturally walking away from the page" UX. We are not promising sub-minute freshness. |
| Background-tab timer fires silently | Page is in background; `document.hidden` returns true → we reschedule without fetching. Tab-visibility `visibilitychange` listener optional; skip for v1. |
| Per-instrument polling would multiply this fan-out by 11 | Not in scope; btc-derivatives page is single-instrument. |
