# Strategy Page — Distinguish "Data Ready" from "Data Pending"

## Context

User feedback (2026-07-24):

> "全在'转换中'，那不就是没计算完成嘛。我点开看技术指标和形态结构页都没东西的。自然都能想到策略页肯定出不了结果。"

Translation: "Everything says 'transition', isn't that just 'not yet computed'? When I click into the technical indicators page and structure page, they have no data either. Naturally I'd think the strategy page can't get results either."

### Root cause: UX, not data

After v1 + v2 fixes the strategy page loads and renders without 5xx. The user can navigate, see the scan matrix, click cells, see the detail panel.

The actual data flow IS working:
- `/api/v1/indicators?btc-usdt-perp&1d` returns 4 EMA points with real values.
- `/api/v1/structure/tab/bundle?btc-usdt-perp&1d` returns `overall.bias=weak_bullish, regime=transition, confidence=0.85`.
- `/api/v1/strategy/scan` returns `matrix: 33 cells, ranked: 3 opportunities` (on warm cache).
- Strategy bundle for btc 1d: `decision.strategy_state=WAIT_LOWER_TF_CONFIRMATION, strategy_bias=short, confidence=39.95`.

But the user **doesn't see this**. They see:
- Scan matrix: every cell says **"等待"** (waiting)
- Detail panel: every timeframe says **"转换中"** (transition) / **"中性"** / 91% confidence
- Banner: **"当前无明确交易机会"** (no clear opportunities right now)

The user's mental model: "转换中" / "等待" / "无明确" all imply **"system hasn't finished computing"**. So they reasonably assume the data isn't ready.

But the truth is: **the data is ready and the verdict is "no edge"**. The market is genuinely in transition. long_score=49.05, short_score=56.36 — both below the LONG_THRESHOLD=60 and SHORT_THRESHOLD=60. So the engine correctly returns NEUTRAL → side=NONE.

The user's complaint is therefore a **semantic UX bug**, not a data bug.

### Goal

Make it immediately obvious to the user whether the page is:
- **A: warming** (data still being computed; banner shows "首次访问，正在预热...")
- **B: ready, no edge** (data computed; verdict is "no clear direction")
- **C: ready, ranked opportunities** (data computed; opportunities shown)

Today the UI conflates B and C-with-no-opportunities: both show "等待" / "当前无明确交易机会". The user can't tell whether to wait for more data or accept that there's no edge.

## Design

### 1. Scanner must expose per-cell cache_state

Add a `cache_state` field to `ScanItem` so the renderer knows whether each cell is "data missing" vs "data ready, no edge":

```python
@dataclass(slots=True)
class ScanItem:
    instrument_id: str
    instrument_code: str
    timeframe: str
    direction: str          # "LONG" | "SHORT" | "WAIT"
    direction_label: str
    confidence: float
    score: float
    summary: str
    risk_reward: float
    leverage_hint: str
    position_cap: str
    primary_driver: str
    conflicts: list[str]
    cache_state: str        # "fresh" | "missing" | "stale" | "warming" | "error"
    data_quality: float      # 0-100, from payload.confidence_report.confidence_score
```

Populate from `payload["freshness_state"]` and `payload["confidence_report"]["confidence_score"]`.

### 2. ScanResult cache_meta adds a "ready" count

```python
cache_meta={
    "fresh_until": ...,
    "source": "live",
    "instruments_scanned": len(instrument_ids),
    "opportunities_found": len(ranked),
    "cells_ready": <count of cache_state=="fresh">,
    "cells_pending": <count of cache_state in {"missing","warming","error"}>,
}
```

### 3. Frontend: differentiate cell states

In `renderScanMatrix.js`, render three distinct cell states:

| cache_state | UI | Rationale |
|---|---|---|
| `fresh` + direction=`WAIT` | "无明确方向" (neutral tone) | data is ready, no edge |
| `fresh` + direction=LONG/SHORT | arrow + confidence (existing) | actionable |
| `missing`/`warming`/`error` | "数据待补" + spinner | genuinely pending |

And in `renderScanRanked.js`, the empty state copy should differ:

- If `cache_meta.cells_pending > 0`: "数据仍在补齐中..."
- Else: "当前无明确交易机会" (existing)

In `renderScanResults` (index.js), the top banner should similarly split:

- If any cell is pending: "数据补齐中 (X/Y)，已有 N 个明确机会"
- Else if opportunities: "发现 N 个交易机会" (existing)
- Else: "全部数据已就绪，当前无明确交易方向" (NEW copy)

### 4. Detail panel: replace "转换中" with "区间/无方向"

The user reads "转换中" as "still loading". Replace with copy that conveys "data is ready, market is in transition":

- In `renderEvidenceStack.js#STRUCTURE_LABELS`, change `TRANSITION: "转换中"` → `TRANSITION: "区间转换"` (already includes 区间) and add `READY: "数据已就绪"` etc.
- In the timeline_state mapping in `_timeframe_state`, add explicit labels: `BULLISH`, `BEARISH`, `TRANSITION`, `DATA_UNAVAILABLE` — keep them but also add a small "数据已就绪" badge when all timeframes are non-DATA_UNAVAILABLE.

Actually simpler: in the per-timeframe row in the detail panel, if `freshness == "fresh"`, prepend "✓ 数据已就绪" chip. If `freshness == "missing"`, prepend "⏳ 数据待补".

### 5. Strategy page CTA

When the banner says "全部数据已就绪，当前无明确交易方向", also show the user "可点击「刷新扫描」以强制重算" hint. Let them know they can force a re-scan if they think data is stale.

## Files

### Backend
- `app/services/strategy_unified/opportunity_scanner.py` — add `cache_state` + `data_quality` to `ScanItem`, populate them in `_extract_scan_item`, compute `cells_ready`/`cells_pending` in `ScanResult.cache_meta`.

### Frontend
- `app/static/pages/strategy/renderScanMatrix.js` — three states (ready+wait / actionable / pending).
- `app/static/pages/strategy/renderScanRanked.js` — split empty-state copy by pending count.
- `app/static/pages/strategy/index.js` — `renderScanResults` builds banner differently based on `cells_ready`/`cells_pending`/`opportunities_found`.
- `app/static/pages/strategy/renderEvidenceStack.js` — prepend data-status badge per timeframe.
- `app/static/pages/strategy/adapter.js` — labels for `TRANSITION`/`DATA_UNAVAILABLE`.

### Tests
- `tests/test_strategy_market_context_static.py` — assert the scanner populates `cache_state` per cell.
- `tests/test_strategy_frontend_static.py` — assert:
  - `renderScanMatrix` has three-branch switch on `cache_state`
  - `renderScanRanked` empty-state has both "数据补齐中" and "当前无明确交易机会" copies
  - Banner logic splits "ready, no edge" from "still pending"

### Verification
1. Cold load → eventually shows "全部数据已就绪，当前无明确交易方向" (not "当前无明确交易机会").
2. Pending state shows "数据补齐中 (X/Y)".
3. Ready + 3 opportunities shows existing banner.
4. Detail panel shows "✓ 数据已就绪" chips when freshness=fresh.
5. `pytest` all green.
6. `verify_pages.py --pages ai-strategy` OK.

## Out of scope

- Actually fixing the underlying data freshness (those are separate worker issues — indicator monitor only covers 1m/5m/1h, structure_snapshot is dead schema, etc.).
- Changing the threshold (60 for direction) — that's a domain tuning question.

## Risk

- The new copy is more verbose. Risk: users see a longer banner. Mitigation: keep banner concise, put details in tooltip/popover.
- RenderScanMatrix changes the cell layout. Risk: existing CSS may not match. Mitigation: keep CSS class names stable (`scan-cell-wait`, `scan-cell-data-ready`, `scan-cell-pending`).