# Strategy Scan Hub — Frontend Test Rewrite

## Context

The AI Strategy page was rewritten as a **multi-instrument Opportunity Scanner hub** in commits `28df2e3` / `46fb31f` / `6d3949b`. The page no longer renders a single unified-strategy view; it shows:

1. A **Scan Matrix** — instrument × timeframe grid of opportunity cells
2. A **Ranked Opportunities list** — only directional signals, sorted by score
3. A **Slide-in Detail Panel** — opens when a cell / card is clicked, fetches `/strategy/unified` for that instrument+timeframe, and renders the full strategy modules (overview, execution plan, decision audit, evidence stack, market operation, risk panel, event watch, data degraded footer)

`tests/test_strategy_frontend_static.py` and `tests/test_strategy_market_context_static.py` were left untouched after the rewrite. They still encode the **old** unified-only architecture, so 12 tests fail.

This spec rewrites both files to validate the **current** scan-hub architecture.

## Test scope (per file)

### `tests/test_strategy_frontend_static.py`

Replace all tests with assertions that match the scan-hub contract:

1. **Registration** — `main.js` registers `./pages/strategy.js?v=trade-4h-v1`, router has `/strategy-page`, page.html has `data-page-link="ai-strategy"`, the link comes **after** `knowledge-base`.
2. **Entry shim** — `app/static/pages/strategy.js` re-exports `renderStrategy` as default + named export from `index.js`. No mojibake (`缁熶竴绛栫暐` / `统一策略快照尚未就绪，后台预热中` etc. are not present).
3. **Scan shell** — `index.js` builds the scan shell with:
   - `strategy-scan-page` class
   - `strategy-scan-refresh` button
   - Two cards `#strategy-scan-matrix-section` and `#strategy-scan-ranked-section`
4. **Scanner wiring** — `index.js` imports `renderScanMatrix` / `renderScanRanked` / `bindScanMatrix` / `bindScanRanked` / `openDetailPanel` from the right modules. Calls `api.getStrategyScan(...)` (not `getUnifiedStrategy` directly) for the hub-level scan, and uses an `AbortController` for cancellation.
5. **Detail panel** — `renderDetailPanel.js` exports `openDetailPanel(instrumentId, timeframe, loadStrategy, onClose)`. The panel:
   - Removes any existing `#strategy-detail-panel` / `#strategy-detail-overlay` before opening
   - Appends an `<aside id="strategy-detail-panel">` and `<div id="strategy-detail-overlay">`
   - Has a `#strategy-detail-close` button and an Escape-key handler
   - Loads the strategy via `loadStrategy()` and renders `renderOverview` / `renderExecutionPlan` / `renderDecisionAudit` / `renderEvidenceStack` / `renderMarketOperation` / `renderRiskPanel` / `renderEventWatch` + `buildDataDegradedCard`
   - Renders error state on failure
6. **Scan Matrix renderer** — `renderScanMatrix.js`:
   - Renders a `scan-matrix-table` with columns `品种 / 周线 / 日线 / 4H`
   - Each cell is a `<button class="scan-cell-btn">` with `data-instrument` + `data-timeframe` attributes
   - Empty / no-trade cells render `<button>等待</button>`
   - `bindScanMatrix(onSelect)` attaches click handlers that call `onSelect(instrumentId, timeframe)`
7. **Ranked renderer** — `renderScanRanked.js`:
   - Renders `.scan-ranked-list` containing `.scan-ranked-card` articles
   - Each card has `data-tone` (bullish/bearish), `data-instrument`, `data-timeframe`
   - Shows `direction_label`, `score`, `summary`, `confidence`, `risk_reward`, `leverage_hint` (rendering `spot` as `现货`)
   - Renders the empty-state copy `当前无明确交易机会。所有品种×级别均处于等待状态。`
   - `bindScanRanked(onSelect)` attaches click handlers
8. **Click flow** — `index.js#onSelectOpportunity(instrumentId, timeframe)` opens the detail panel and loads `getUnifiedStrategy` for that pair. The panel receives the loaded `model` and renders all sub-modules.
9. **No legacy renderers** — `index.js` must not import `renderHorizonStack` / `renderTradePlans` / `renderEvidenceTrace` / `renderNarrative` / `renderTradeDecision` / `renderDetailPanel` (the legacy module exists for the slide-in panel but its name should not be confused with the unified-only architecture).
10. **mount/unmount lifecycle** — `renderStrategy()` returns `{ mount, unmount, pause, resume }`. `unmount` aborts the active controller and resets `mounted = false`.
11. **No stale "待评估" / "暂不能评估" copy** — combined assertion across all strategy/* files.
12. **No position-management copy** — combined assertion across strategy/* files: forbid `ADD_LONG` / `REDUCE_LONG` / `CLOSE_LONG` / `HOLD_LONG` / `TAKE_PROFIT`.
13. **Beijing-time policy** — `formatDateTime` policy comment in `dom.js` does not contain the literal phrase `北京时间` (already covered by `test_timezone_label_removed.py`); we **don't** duplicate it here.

### `tests/test_strategy_market_context_static.py`

Replace with assertions that match the **current** endpoint surface used by the scan hub:

1. **`api.js` exposes scan endpoint** — `api.getStrategyScan` is exported; `requestJson("/strategy/scan"`.
2. **Hub orchestration** — `index.js` uses `api.getStrategyScan` (not `api.getMonitoringDashboard` etc. at the hub level — those are still wired via `loadStrategy`).
3. **Detail-panel orchestration** — `renderDetailPanel.js` uses `getUnifiedStrategy` via `loadStrategy(instrumentId, timeframe, ...)` (the outer caller inside `onSelectOpportunity`).
4. **No legacy render calls** — the legacy `renderHorizonGovernance` / `renderEventWatch` / `renderTradePlans` etc. are no longer wired into the **scan shell**; they're only used by the detail panel.
5. **Market-context backend** — `app/services/strategy_signal/snapshot_builder.py` still uses `MarketContextBuilder` + emits `"market_context"` key (kept as a contract — the panel still consumes unified data).
6. **Risk-gate labels** — `risk_gate.py` still uses the four canonical Chinese labels (`核心周期数据缺失` / `高影响事件窗口` / `衍生品确认降级` / `链上数据缺失`).
7. **Macro regime** — `macro_regime.py` still emits `human_explanation` and contains `宏观`.
8. **Backend hides internal diagnostics** — runtime assertion that `MacroRegimeEngine.compute().evidence`, `OnchainRegimeEngine._strategy_impact`, and `UnifiedStrategyService._price_structure_dimension(...).evidence` don't expose `operation_bias` / `regime_key` / `NEUTRAL` / `战略栈=` / `战术栈=`.
9. **`verdict_for_node`** — unchanged contract for all canonical states.
10. **Confidence reflects conclusive state** — `MultiTimeframeStructureEngine().build_nodes` for a fresh `CONTEXT_SHORT` node yields `confidence >= 70`.
11. **Confidence reflects range_no_edge** — same, for `NO_EDGE`, yields `confidence >= 60`.

## Out of scope

- Anything that doesn't impact the **frontend contract** (backend Python unit tests for risk_gate / macro_regime / mtf_structure stay in their own files, not duplicated here).
- Internal diagnostic text ("等待更多证据" etc.) — we only forbid copy that historically leaked into the UI.
- Performance / DOM timing — covered by `tests/verify_pages.py`.
- Multi-page snapshot / Playwright tests for the strategy page — already exercised by `verify_pages.py`.

## Migration

1. Rewrite `tests/test_strategy_frontend_static.py` from scratch (delete + new file).
2. Rewrite `tests/test_strategy_market_context_static.py` from scratch (delete + new file).
3. Run `pytest tests/test_strategy_frontend_static.py tests/test_strategy_market_context_static.py -q` — expect all green.
4. Run `pytest tests/ -q --ignore=tests/test_precompute.py --ignore=tests/test_strategy_unified_service.py --ignore=tests/test_strategy_scan_endpoint.py --ignore=tests/test_strategy_outcome_engine.py --ignore=tests/test_strategy_signal_snapshot.py --ignore=tests/test_strategy_review_iteration.py --ignore=tests/test_strategy_setup_lifecycle_v17.py --ignore=tests/test_strategy_shadow_validation.py --ignore=tests/test_strategy_unified_api.py --ignore=tests/test_strategy_unified_degraded.py --ignore=tests/test_strategy_decision_rules.py --ignore=tests/test_strategy_degraded_frontend.py` — expect **0 strategy failures**.
5. Run `python tests/verify_pages.py --pages ai-strategy` to ensure the page still renders without JS errors.

## Risk

- The legacy renderers (`renderOverview`, `renderExecutionPlan`, etc.) **are still consumed by the detail panel**, so their existence is fine — they just aren't wired at the hub level. We only assert they exist (via `renderDetailPanel.js` imports) and aren't double-mounted at the hub level.
- `formatHelpers.js` (shared helper) is still imported by the legacy renderers, so it's not removed; we don't test it directly here.