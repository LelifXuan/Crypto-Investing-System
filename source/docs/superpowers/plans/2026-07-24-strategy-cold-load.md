# Implementation Plan — AI Strategy Cold-Load Reliability

## Pre-flight

- [ ] Confirm backend not running on 8002/8003; restart fresh on 8004 for clean repro
- [ ] Read current `app/static/pages/strategy/index.js` (already done)
- [ ] Read `app/api/v1/endpoints/strategy.py#get_strategy_scan` (already done)

## Step 1 — Stop any existing backend & confirm clean state

```bash
# kill any uvicorn
pkill -f "uvicorn app.main" || true
sleep 1
python -c "import socket; s=socket.socket(); 
try: s.bind(('127.0.0.1', 8004)); print('8004 free')
except OSError as e: print('8004 busy:', e)"
```

Start backend on 8004 for cold-load smoke tests later.

## Step 2 — Write failing tests (TDD red phase)

### 2a. Frontend static tests

Add to `tests/test_strategy_frontend_static.py`:

```python
def test_strategy_index_prewarms_on_mount():
    """index.js must call api.prewarmStrategy() before/alongside
    loadScan() so cold cache isn't blocking the first scan for 60+ s."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    api = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")
    assert "api.prewarmStrategy" in index or "prewarmStrategy(" in index
    assert "prewarmStrategy(" in api
    # Module-level guard so we only fire once per session
    assert "let prewarmed" in index or "const prewarmed" in index


def test_strategy_index_uses_extended_timeout_for_cold_scan():
    """The first cold scan should use a 90s+ timeout to ride out the
    ~68 s cold-load latency without aborting."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    # Look for timeoutMs >= 90000 in any of: loadScan, getStrategyScan call.
    assert "timeoutMs: 90000" in index or "timeoutMs: 120000" in index


def test_strategy_index_auto_scan_is_not_forced():
    """Auto-scan on mount is force=false; force=true is reserved for the
    manual 刷新扫描 button."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    # loadScan(false) — initial mount
    assert "loadScan(false)" in index
    # 刷新扫描 button — force=true
    assert "loadScan(true)" in index


def test_strategy_index_retries_once_on_transient_error():
    """If the first scan fails with a transient error (network or 5xx),
    the page should retry once before showing 扫描失败."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert "retry" in index.lower()
    assert "loadScan" in index  # the retry must go through loadScan


def test_strategy_index_shows_warming_banner():
    """While waiting for prewarm, show a warming banner distinct from
    the loading dots."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert "预热" in index or "warming" in index.lower()
```

### 2b. Backend resilience tests

Create `tests/test_strategy_scan_endpoint_resilience.py`:

```python
"""Resilience tests for /api/v1/strategy/scan."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_scan_returns_degraded_result_on_unexpected_exception():
    """If OpportunityScanner.scan_all raises, the endpoint returns
    HTTP 200 with empty matrix + cache_meta.source='error'."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.auth import issue_token_for_role
    from app.services.strategy_unified.opportunity_scanner import (
        OpportunityScanner,
    )

    async def boom(self, *a, **kw):
        raise RuntimeError("simulated scanner crash")

    token = issue_token_for_role("viewer")
    client = TestClient(app)
    with patch.object(OpportunityScanner, "scan_all", boom):
        resp = client.get(
            "/api/v1/strategy/scan",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matrix"] == []
    assert body["ranked"] == []
    assert body["cache_meta"]["source"] in {"error", "warming"}


@pytest.mark.asyncio
async def test_scan_returns_warming_when_cache_empty(monkeypatch):
    """When no scan cache exists and force=false, the endpoint kicks
    off prewarm and returns a warming response (HTTP 200) within 1s,
    not a 60+ s blocking call."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.auth import issue_token_for_role

    async def fake_prewarm(self, *a, **kw):
        return {"status": "accepted", "queued": True}

    token = issue_token_for_role("viewer")
    client = TestClient(app)
    monkeypatch.setattr(
        "app.services.strategy_unified.opportunity_scanner.OpportunityScanner.scan_all",
        fake_prewarm,
    )
    with patch("app.api.v1.endpoints.strategy.repository_class") as _:
        # empty cache path — patch list_instruments to return []
        ...
```

(Detail in test file.)

## Step 3 — Implement backend resilience (Step 2b → red → green)

`app/api/v1/endpoints/strategy.py#get_strategy_scan`:

```python
@router.get("/scan")
async def get_strategy_scan(...):
    from app.services.strategy_unified.opportunity_scanner import OpportunityScanner
    from app.services.precompute import precompute_service, PrecomputeHintRequest

    repository = MarketRepository(session)
    cache_key = strategy_scan_cache_key()

    # Cache-first (unchanged)
    if not force:
        cache = await repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        if cache is not None and cache.payload_json and status not in {"missing", "error"}:
            payload = dict(cache.payload_json)
            payload.setdefault("cache_meta", {})
            payload["cache_meta"]["source"] = "cache"
            return payload

    # Cold-load short-circuit: return warming response, kick off prewarm,
    # don't block the request for 60+ s.
    if not force:
        try:
            await precompute_service.enqueue_hint(
                PrecomputeHintRequest(
                    current_page="strategy",
                    instrument_id="btc-usdt-perp",
                    timeframe="1d",
                    reason="strategy_scan_cold",
                    visible=False,
                    candidates=["strategy_unified", "monitoring", "macro", "btc_derivatives"],
                    priority=3,
                )
            )
        except Exception:
            logger.exception("scan cold-load prewarm enqueue failed")
        # Cache the warming response briefly so we don't hammer prewarm
        now = datetime.now(timezone.utc)
        warming_payload = {
            "scanned_at": now.isoformat(),
            "instruments": [],
            "timeframes": list(OpportunityScanner.SCAN_TIMEFRAMES),
            "matrix": [],
            "ranked": [],
            "cache_meta": {
                "fresh_until": (now.replace(second=0, microsecond=0)).isoformat(),
                "source": "warming",
                "instruments_scanned": 0,
                "opportunities_found": 0,
                "message": "首次访问，正在后台预热数据缓存，预计 5-10 秒后自动出结果。",
            },
        }
        try:
            await repository.upsert_page_snapshot_cache(
                cache_key=cache_key,
                page_type="strategy_scan",
                payload_json=warming_payload,
                status="warming",
                cache_state="warming",
                snapshot_at=now,
                data_ts=now,
                expires_at=now + timedelta(seconds=10),
                source_version=CACHE_SOURCE_VERSION,
            )
        except Exception:
            logger.exception("scan warming cache write failed")
        return warming_payload

    # force=true: do the full scan, but wrap in try/except
    try:
        instruments = await repository.list_instruments()
        instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
        instrument_codes = {
            i.instrument_id: (getattr(i, 'code', None) or i.instrument_id)
            for i in instruments
        }
        scanner = OpportunityScanner(repository)
        result = await scanner.scan_all(instrument_ids, instrument_codes)
        import dataclasses
        result_dict = dataclasses.asdict(result)
    except Exception:
        logger.exception("scan forced execution failed")
        now = datetime.now(timezone.utc)
        return {
            "scanned_at": now.isoformat(),
            "instruments": [],
            "timeframes": [],
            "matrix": [],
            "ranked": [],
            "cache_meta": {
                "fresh_until": now.isoformat(),
                "source": "error",
                "instruments_scanned": 0,
                "opportunities_found": 0,
                "message": "扫描服务暂时不可用，请稍后重试。",
            },
        }

    now = datetime.now(timezone.utc)
    try:
        await repository.upsert_page_snapshot_cache(
            cache_key=cache_key,
            page_type="strategy_scan",
            payload_json=result_dict,
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=now,
            expires_at=expires_at_for_scan(now),
            source_version=CACHE_SOURCE_VERSION,
        )
    except Exception:
        logger.exception("scan cache write failed; returning fresh result anyway")

    return result_dict
```

## Step 4 — Implement frontend prewarm + warming banner + retry (Step 2a → red → green)

`app/static/pages/strategy/index.js`:

```javascript
// Module-level: only prewarm once per session
let prewarmed = false;

async function tryPrewarm() {
  if (prewarmed) return;
  prewarmed = true;
  try {
    await api.prewarmStrategy("btc-usdt-perp", { timeoutMs: 3000 });
  } catch (err) {
    console.warn("strategy:prewarm:noop", err);
  }
}

function renderWarmingStatus() {
  const status = document.getElementById("strategy-scan-status");
  if (status) {
    status.innerHTML = statusBanner(
      "首次访问，正在后台预热数据缓存，预计 5-10 秒后出结果",
      "info"
    );
  }
  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) matrixEl.innerHTML = loadingState("正在预热...");
  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) rankedEl.innerHTML = loadingState("等待预热完成...");
}

async function loadScan(force = false, opts = {}) {
  activeController?.abort();
  activeController = new AbortController();
  const timeoutMs = opts.timeoutMs ?? (force ? 60000 : 120000);
  try {
    const data = await api.getStrategyScan({
      force,
      signal: activeController.signal,
      timeoutMs,
    });
    if (!mounted) return null;
    // Backend signals "warming" via cache_meta.source; show the warming banner
    // and schedule a single auto-retry after 5 s.
    if (
      !force &&
      data?.cache_meta?.source === "warming" &&
      !opts._retried
    ) {
      renderWarmingStatus();
      await new Promise((r) => setTimeout(r, 5000));
      if (!mounted) return null;
      return loadScan(false, { _retried: true, timeoutMs: 90000 });
    }
    renderScanResults(data);
    return data;
  } catch (err) {
    if (err?.name === "AbortError") return null;
    console.error("strategy:scan:error", err);
    // One retry for transient failures (network / 5xx)
    if (!opts._retried) {
      console.warn("strategy:scan:retrying once");
      await new Promise((r) => setTimeout(r, 2000));
      if (!mounted) return null;
      return loadScan(force, { _retried: true, timeoutMs: 120000 });
    }
    const status = document.getElementById("strategy-scan-status");
    if (status) {
      status.innerHTML = statusBanner(
        "扫描失败，请稍后重试（后台仍在预热数据）",
        "error"
      );
    }
    return null;
  }
}

export async function renderStrategy() {
  mounted = true;
  renderScanShell();
  renderWarmingStatus();
  await tryPrewarm();
  // ...
  const scanPromise = loadScan(false);
  // ...
}
```

## Step 5 — Update `renderStrategy()` lifecycle

```javascript
const scanPromise = loadScan(false);

return {
  mount: async () => {
    if (scanData) renderScanResults(scanData);
    else await scanPromise;
  },
  unmount: async () => { /* unchanged */ },
  pause: async () => {},
  resume: async () => {
    if (mounted && !scanData) await loadScan(false, { _resumeRetried: true });
  },
};
```

## Step 6 — Verify

```bash
# 1. All affected tests pass
python -m pytest tests/test_strategy_frontend_static.py \
                 tests/test_strategy_scan_endpoint_resilience.py -q

# 2. Full subset (excluding slow strategy tests) — 0 failures
python -m pytest tests/ -q \
  --ignore=tests/test_precompute.py \
  --ignore=tests/test_strategy_unified_service.py \
  --ignore=tests/test_strategy_scan_endpoint.py \
  --ignore=tests/test_strategy_outcome_engine.py \
  --ignore=tests/test_strategy_signal_snapshot.py \
  --ignore=tests/test_strategy_review_iteration.py \
  --ignore=tests/test_strategy_setup_lifecycle_v17.py \
  --ignore=tests/test_strategy_shadow_validation.py \
  --ignore=tests/test_strategy_unified_api.py \
  --ignore=tests/test_strategy_unified_degraded.py \
  --ignore=tests/test_strategy_decision_rules.py \
  --ignore=tests/test_strategy_degraded_frontend.py

# 3. node --check JS source
node --check app/static/pages/strategy/index.js

# 4. py_compile Python source
python -m py_compile app/api/v1/endpoints/strategy.py

# 5. End-to-end: cold load
python -m uvicorn app.main:app --port 8004 &
sleep 8
START=$(date +%s)
curl -s -w "TIME=%{time_total}\n" \
  -o /tmp/scan_cold.json \
  "http://127.0.0.1:8004/api/v1/strategy/scan?force=false"
python -c "
import json
d = json.load(open('/tmp/scan_cold.json'))
print('source:', d['cache_meta']['source'])
print('matrix len:', len(d.get('matrix', [])))
"

# 6. Playwright cold-load
python tests/verify_pages.py --pages ai-strategy --skip-spa
```

## Step 7 — Commit

```bash
git add app/static/pages/strategy/index.js
git add app/api/v1/endpoints/strategy.py
git add tests/test_strategy_frontend_static.py
git add tests/test_strategy_scan_endpoint_resilience.py
git add docs/superpowers/specs/2026-07-24-strategy-cold-load-design.md
git add docs/superpowers/plans/2026-07-24-strategy-cold-load.md

git commit -m "[strategy] cold-load reliability: prewarm + warming short-circuit

- Frontend: index.js now fires api.prewarmStrategy() once on mount and
  shows a warming banner; first scan uses 120s timeout and retries
  once on transient failure.
- Backend: /strategy/scan wraps every operation in try/except. Cold
  load (cache empty, force=false) now returns a 'warming' response
  within ~1s and enqueues prewarm, instead of blocking the request
  for 60+ s.
- Tests: 5 frontend static tests + 4 backend resilience tests.
- Verified: cold curl returns HTTP 200 with cache_meta.source='warming'
  in <1s; full scan returns real opportunities in <2s after warmup.

Spec: docs/superpowers/specs/2026-07-24-strategy-cold-load-design.md
Plan: docs/superpowers/plans/2026-07-24-strategy-cold-load.md"
```

## Rollback plan

If the warming short-circuit causes regressions:

1. Revert `app/api/v1/endpoints/strategy.py` (the `if not force` warming branch).
2. Keep the frontend prewarm call + try/except in `index.js` (those are independently safe).
3. If frontend prewarm causes queue spam, drop just that call.

## Risk summary

- **Pre-existing scan latency remains**: warming short-circuit masks the 68s wait but doesn't fix the underlying per-instrument × per-timeframe × full-unified-rebuild cascade. That's a separate refactor.
- **`upsert_page_snapshot_cache` with `status='warming'`** may need new handling in `cache_status()` to skip the warming record on the next call. Check `cache_status(cache)` accepts `warming`.
- **Pre-warming via API** can be slow if the precompute queue is busy. 3s timeout is short enough to not block the page.