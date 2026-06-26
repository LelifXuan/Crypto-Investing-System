# BTC Derivatives Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a chart-first BTC derivatives decision-support page with option-wall/max-pain history, long/short evidence, and a finite-risk hedge planner.

**Architecture:** Add typed Pydantic API contracts and a focused `app/services/btc_derivatives` package for normalized models, deterministic metrics, history snapshots, chart contracts, evidence classification, and hedge planning. Expose stable dashboard and hedge-plan endpoints, then render the payload through the existing static SPA and Chart.js helpers. P0 uses deterministic fixture data plus a local JSON snapshot store marked explicitly as fixture/cache data; no order execution or live-provider claims are added.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, pytest, vanilla ES modules, Chart.js, existing static SPA/CSS.

---

### Task 1: Contract and metric foundations

**Files:**
- Create: `app/schemas/btc_derivatives.py`
- Create: `app/services/btc_derivatives/__init__.py`
- Create: `app/services/btc_derivatives/models.py`
- Create: `app/services/btc_derivatives/options_metrics.py`
- Create: `app/services/btc_derivatives/futures_metrics.py`
- Test: `tests/test_btc_derivatives_metrics.py`
- Test: `tests/test_btc_derivatives_wall_max_pain.py`

- [ ] Write failing schema tests proving empty chart payloads and partial rows validate.
- [ ] Run the targeted tests and confirm missing-module failures.
- [ ] Add normalized futures/options dataclasses and Pydantic response/request contracts.
- [ ] Write failing tests for option walls, max pain, 25D skew fallback, ratios, liquidity, aggregate OI, and price/OI regime.
- [ ] Run the tests and confirm the expected missing-function failures.
- [ ] Implement only the deterministic metric helpers needed by those tests.
- [ ] Run both metric test modules and confirm they pass.

### Task 2: History, chart contracts, and evidence engine

**Files:**
- Create: `app/services/btc_derivatives/wall_tracker.py`
- Create: `app/services/btc_derivatives/chart_builder.py`
- Create: `app/services/btc_derivatives/market_state_engine.py`
- Test: `tests/test_btc_derivatives_state_engine.py`

- [ ] Write failing tests for wall/max-pain migration labels and all stable chart ids.
- [ ] Run the tests and confirm expected failures.
- [ ] Implement JSON snapshot read/append with bounded history and corrupt-file fallback.
- [ ] Implement Chart.js-friendly payload builders for all ten chart contracts.
- [ ] Write failing tests for upside-squeeze, downside-stress, deleveraging, and long/short help/hurt evidence.
- [ ] Implement the evidence engine with explicit confidence and warning language.
- [ ] Run the state-engine tests and confirm they pass.

### Task 3: Finite-risk hedge engine

**Files:**
- Create: `app/services/btc_derivatives/hedge_engine.py`
- Test: `tests/test_btc_derivatives_hedge_engine.py`

- [ ] Write failing tests for short-grid upper proximity, upper breach, long-grid lower proximity, lower breach, high IV, poor liquidity, and budget checks.
- [ ] Assert forbidden actions/phrasing never include naked selling or ratio spreads presented as protection.
- [ ] Run the tests and confirm expected failures.
- [ ] Implement deterministic finite-risk decisions: buy call/put, debit spreads, reduce grid, wait, or no hedge.
- [ ] Run the hedge-engine tests and confirm they pass.

### Task 4: Dashboard orchestration and API

**Files:**
- Create: `app/services/btc_derivatives/service.py`
- Create: `app/api/v1/endpoints/btc_derivatives.py`
- Modify: `app/api/router.py`
- Test: `tests/test_btc_derivatives_api.py`

- [ ] Write failing API tests for stable dashboard shape, selected-expiry behavior, refresh, and hedge-plan safety.
- [ ] Run the tests and confirm 404/missing-module failures.
- [ ] Implement fixture-backed dashboard assembly, history snapshot update, data-quality reporting, and compact evidence summary.
- [ ] Register GET `/dashboard`, POST `/dashboard/refresh`, and POST `/hedge-plan`.
- [ ] Add the router without disturbing existing endpoint registrations.
- [ ] Run API tests and confirm they pass.

### Task 5: Chart-first SPA page

**Files:**
- Create: `app/static/pages/btc_derivatives.js`
- Modify: `app/static/core/api.js`
- Modify: `app/static/main.js`
- Modify: `app/templates/page.html`
- Modify: `app/web/router.py`
- Modify: `app/static/styles.css`
- Test: `tests/test_btc_derivatives_frontend_static.py`

- [ ] Write failing static tests for route/nav/module/API registration, ten chart slots, warning copy, hedge form fields, and forbidden trading language.
- [ ] Run the static tests and confirm expected failures.
- [ ] Add API helper methods and SPA registration with Chart.js asset loading.
- [ ] Add route/title/nav entries by appending to current user changes.
- [ ] Build the page shell: decision cards, four-chart overview, futures layer, options layer, history layer, hedge planner, and data-quality layer.
- [ ] Render charts through `renderChart`, `lineDataset`, and `barDataset`; destroy them on unmount.
- [ ] Add scoped responsive CSS for dense desktop and single-column mobile layouts.
- [ ] Run static tests and `node --check` for every changed JS file.

### Task 6: Full verification and runtime QA

**Files:**
- Modify if needed: `tests/verify_pages.py`

- [ ] Compile every new/changed Python file.
- [ ] Run `ruff check` on BTC derivatives files.
- [ ] Run all BTC derivatives tests.
- [ ] Run the full pytest suite and record any unrelated pre-existing failures separately.
- [ ] Start the local app and run page verification for `btc-derivatives` plus shared SPA navigation.
- [ ] Inspect the rendered desktop and mobile screenshots, verify all chart/error states, expiry switching, refresh, and hedge-plan submission.
- [ ] Audit source and rendered copy for order placement, naked option selling, deterministic max-pain claims, guaranteed wall claims, and unsafe ratio-spread language.
