# Trading System FastAPI

Windows-first local crypto research and trading management app built with `FastAPI + SQLite + Gate.io`.

Current version: **V1.5.5** (see [Release Timeline](#release-timeline) below).

## Release Timeline

The `V1.5` series ships explainability + performance + UI clarity changes on top of the
monitoring overview explainability loop. Each release is independently shippable and
self-contained; the version numbers below are ordered by when the work landed.

### V1.5 — monitoring overview explainability loop

V1.5 focuses on the **monitoring overview explainability loop**. The terminal
summary is now produced as a three-row `decision_brief`:

- `市场情况` (market situation)
- `交易指引` (trading guidance)
- `风险点 / 失效条件` (risk / invalidation)

Each row carries an `evidence_strength` (0-1) computed from the new
multi-period conflict matrix in `terminal_summary.decision_brief.source_alignment.matrix`.
When evidence drops below `0.5` the row tone is demoted to `warning`
and the summary is prefixed with an explicit uncertainty note.

The decision_brief is persisted to `ComputedDatasetCache` after every
`MonitoringDashboardService.refresh_bundle` so users can review
historical decisions through `GET /monitoring/decision-brief/history`.

### V1.5.1 — long/short reasoning audit (7 fixes)

V1.5.1 was the audit-driven re-implementation of the long/short reasoning
chain. The audit found that:

- `normalize_direction_metrics(score)` was silently treating signed chip
  scores (range -100..+100) as legacy 0..100 values, double-counting them
  in the score engine;
- `next_trigger` was not polymorphic — a string trigger, a list of
  triggers, and a dict-shaped trigger all produced different output, and
  one path silently dropped;
- gates were parsed ad-hoc per call site, so `block` / `warning` were
  string-matched and a structured `GateDiagnostic` was lost;
- the 5 feature sources (trend / structure / regime / momentum / flow)
  were not independent — a single EMA tweak polluted multiple scores;
- the lower-TF snapshot was inferred from aggregate data quality instead
  of being loaded from the cache;
- ATR × leverage was not used for futures margin pressure;
- `MonitoringDashboardService` was overwriting the caller's
  `instrument_id` / `timeframe` from its own defaults.

The seven T01-T07 fixes:

- **T01** `normalize_direction_metrics(score, *, scale="signed")`
  enforces explicit scale. Chip is `scale="signed"`; legacy
  inputs raise `ValueError`.
- **T02** `next_trigger` now accepts `str | list | dict` and produces a
  single canonical text.
- **T03** Gates are parsed as `GateDiagnostic` (code, status, severity,
  message, current, required) with `block / warning / info` levels;
  the trading row joins blockers with `；` and warns inline.
- **T04** `snapshot_builder` splits the score into 5 independent
  components (mtf_trend / structure / regime / momentum / flow) and
  tags each with a `*_source` field so callers know which input moved.
- **T05** `lower_tf_snapshot` is loaded from `PageSnapshotCache`; the
  previous `data_quality_score < 60` heuristic is gone.
- **T06** `compute_futures_risk` reads `atr_14` × `default_leverage` and
  emits `block / downsize / watch / ok` pressure tiers, with a
  liquidation-buffer check that forces `block` if stop is < 1.5 ATR
  from the liquidation price.
- **T07** `MonitoringDashboardService.get_bundle` no longer overwrites
  caller inputs; empty-string `instrument_id` falls back to
  `btc-usdt-perp` / `1d` only when the FastAPI default is in effect.

### V1.5.2 — monitoring overview 4 user-reported fixes

V1.5.2 closed the four issues the user found while clicking through the
monitoring page on a live deployment:

- **T08** Structure module now reads the real `structure_bundle` cache
  (with `strategy.structure_overall` and `alerts.chip_structure`
  fallbacks) so the row no longer permanently renders `待确认`.
- **T09** Decision brief rows redesigned: `trading_guidance` (which
  re-rendered the strategy page) and `risk_invalidation` (which
  enumerated every chip / divergence / structure risk) are gone. New
  row set: `market_situation` (1-sentence headline + per-TF bullets)
  + `mtf_breakdown` (per-TF list when timeframes disagree) +
  `key_risk` (top 1-2 critical invalidation conditions + data gaps).
- **T10** Futures margin pressure is gated on actionable strategy
  state — `OBSERVE / NO_EDGE / WAIT_* / EVENT_WAIT / RISK_OFF /
  INVALID_PLAN_LEVELS / terminal` states hide the bullet. The
  "OBSERVE + 建议减半仓位" contradiction no longer renders.
- **T11** `MonitoringDashboardService.get_bundle` actually calls
  `refresh_bundle` when the cache is stale. The previous code only
  logged "refresh is needed" and returned the stale payload. The fix
  calls refresh, then falls back to stale if refresh itself fails.

### V1.5.3 — dead-code cleanup + quick-win perf

V1.5.3 deleted dormant V1.5.1 / V1.5.2-era helpers and applied the
quick-win performance fixes the audit identified:

- **A1-A6** Removed 5 dormant helpers in `terminal_summary_engine`
  (`_summarize_legacy`, `_decision_describe_timeframes`,
  `_decision_describe_strategy_levels`, `_decision_build_trading_row`,
  `_decision_build_risk_row`).
- **A9** Removed 2 dead endpoints (`/alerts/chip-structure`,
  `/strategy/iteration-proposals`) and the corresponding JS helpers.
- **A10-A12** Removed 3 unread `MonitoringDashboardRead` fields
  (`technical_source`, `technical_indicator_count`, `onchain_observations`),
  2 schema aliases (`StrategyV15DecisionRead`, `StrategyV15BundleRead`),
  the `build_bundle` alias, and the unused `_cached` parameter on
  `_terminal_summary_payload`.
- **B1** Static asset cache header: `no-store` → `public, max-age=3600,
  must-revalidate` (relies on existing `?v=<mtime>` bust).
- **B2** Parallelised 4 sequential cache reads in `get_bundle` with
  `asyncio.gather`; the inner 3-TF loop in
  `_load_cached_analysis_timeframes` is also gathered.
- **B5** Chip payload dedupe via `SharedQueryCache`
  (`alerts_bundle:chip_payload:v1:{inst}:{tf}`, TTL
  `settings.shared_query_cache_seconds`).
- **B6** Chart.js CDN tag wrapped in `{% if page_id == "market-analysis" %}`
  and given `defer` — 8 of 9 pages skip the 200 KB download.
- **B10** `strategy.js` review-refresh listener race fix via document
  event delegation.
- **B11** `analysis.js scheduleBundleRetry` capped at 3 attempts.
- **B12** `alerts.js` status-change click now does surgical row update
  (state + actions cells only) instead of refetching the whole bundle.

### V1.5.4 — data-pipeline refactor + SPA routing

V1.5.4 reworks the data-pipeline hot path and converts tab navigation
to in-process SPA routing:

- **C1** In-process cache for `ComputedDatasetCacheService.
  get_or_build_indicator_series`, keyed on the existing
  `indicator_series_cache_key` (which already includes the candle
  timestamp so a new candle auto-invalidates).
- **C3** New `MarketRepository.list_latest_observations_by_key` with
  SQL window function; macro overview no longer pulls 5000 rows to
  dedupe in Python.
- **C5** `MonitoringDashboardService.get_bundle` caches the validated
  `MonitoringDashboardRead` model in `SharedQueryCache` keyed on
  `(instrument_id, timeframe, data_ts, cache_state)` with 60s TTL.
- **C7** New `MarketRepository.list_candles_for_instruments` collapses
  the 5 cross-asset queries in `_cross_asset_snapshot` to 1 SQL.
- **C12** `upsert_computed_dataset_cache` rewritten as
  dialect-native `INSERT ... ON CONFLICT (cache_key) DO UPDATE`
  (Postgres / SQLite each use their dialect).
- **C11** `monitoring.js` `applyMonitoringDiff` builds a stable shell
  with 5 named containers and only swaps the leaf innerHTML on
  refresh (vs. rebuilding the whole tree).
- **D1** `main.js` progressive SPA routing: intercept clicks on
  `[data-page-link]`, preventDefault, pushState, re-run boot() against
  the same shell. Backend `/<page>-page` routes still work as deep-link
  fallbacks.

### V1.5.5 — monitoring overview 6 user-reported fixes

V1.5.5 closed the second round of user feedback on the monitoring page:

- **⑥** `monitoring_dashboard._load_cached_structure_payload` now
  reads `payload.snapshot.overall.{overall_bias, score, regime,
  confidence, ...}` instead of the wrong top-level `payload.get("score")`.
  The fix resolved the "structure page is bearish, monitoring is
  neutral" contradiction the user observed. `StructureSummaryAdapter.
  _BIAS_TO_IMPACT` gained `weak_bullish / weak_bearish / mild_* /
  uncertain / no_clear_structure` mappings with score clamps so
  weak-direction tokens no longer fall through to `neutral`. The
  chip_structure proxy path now forces `confidence=0.2` +
  `is_proxy=True` so the proxy never masquerades as a real signal.
- **②** `_determine_regime` catch-all sub-classifies into
  `偏多震荡` (global_score >= 55) / `偏空震荡` (<= 45) /
  `中性震荡` (middle). The frontend collapses the two `regime` +
  `bias · confidence` chips into a single regime chip + a confidence
  number.
- **③** Headline (`_generate_text` catch-all) and the four
  `_decision_build_market_row` summary branches are now 1 sentence
  each. The regime prefix is removed (the head chip already shows it).
- **④** `_decision_build_key_risk_row` no longer renders
  `数据缺口` bullets (those are internal data-quality reports, not
  user-facing risks); the row summary is now
  `关键失效条件：{topmost invalidation}`. `_decision_text` no longer
  `str(dict)`-reprs a Mapping — it unwraps `text / message / label /
  reason / summary` keys, and single-element lists.
- **⑤** New `SOURCE_REF_META` mapping gives each `source_ref` key a
  Chinese label + target page. The frontend renders chips as
  `<a data-page-link="{page}">` and reuses the V1.5.4 D1 SPA router.
  `missing:{bundle}` refs get `(未刷新)` suffix and route to the
  owning page.
- **①** `monitoring-snapshot-grid` switched to
  `grid-template-areas: "terminal terminal / macro technical"`. The
  TERMINAL BRIEF card now spans the full content width, with MACRO
  and TECHNICAL sharing row 2. The 6 vote tiles stay inside the brief
  card and the headline gets `line-clamp: 3`.

See `docs/RELEASE.md` for the per-release pre-flight checklists and
`docs/RELEASE.md` for the live verification commands.

## Source Of Truth

- Main project directory: this repository root
- Recommended runtime: local single-user mode
- Supported Python: `3.11` and `3.14`
- Recommended local host: `127.0.0.1`

This project is a local research tool, not a public SaaS app and not an automated execution engine.

## Project Layout

- `app/`: API, workers, services, templates, static assets
- `tests/`: regression and behavior checks
- `alembic/`: database migrations
- `scripts/`: workspace automation, cleanup, release packaging
- `docs/`: project documentation and archived notes

Local runtime state is intentionally kept outside this repository:

- `..\runtime_dev\.venv`: development Python environment
- `..\runtime_dev\source_runtime`: source-mode database, logs, cache, and temp files
- `..\TradingSystemPortable`: generated portable build; do not edit it by hand

## Windows Quick Start

1. Create and activate a supported virtual environment outside the source tree.

```powershell
py -3.11 -m venv ..\runtime_dev\.venv
..\runtime_dev\.venv\Scripts\Activate.ps1
```

You can also use:

```powershell
py -3.14 -m venv ..\runtime_dev\.venv
```

2. Copy the example environment file.

```powershell
Copy-Item .env.example .env
```

3. Install dependencies and run the quality check.

```powershell
python scripts/tasks.py install
python scripts/tasks.py check
```

4. Start the local app.

```powershell
python scripts/tasks.py dev-local
```

If you use the workspace-standard external environment, this helper starts the
source instance on port `8002` and keeps runtime files out of the repository:

```powershell
.\scripts\dev_env.ps1 -StartServer
```

For double-click startup from the source tree, use:

```powershell
.\start_source.bat
```

`start_portable.bat` is only for the generated `TradingSystemPortable` bundle.
It expects an embedded Python runtime at `runtime_env\python` and will fail when
double-clicked from the source repository.

5. Open the local UI.

- Dashboard: [http://127.0.0.1:8002/dashboard](http://127.0.0.1:8002/dashboard)
- Indicators: [http://127.0.0.1:8002/indicators-page](http://127.0.0.1:8002/indicators-page)
- Market events: [http://127.0.0.1:8002/market-events-page](http://127.0.0.1:8002/market-events-page)
- Imports: [http://127.0.0.1:8002/imports-page](http://127.0.0.1:8002/imports-page)

## Windows Task Runner

Use either `python scripts/tasks.py <task>` or `.\scripts\dev.ps1 <task>`.

Available tasks:

- `install`: install editable app and development dependencies
- `dev`: run Uvicorn on `127.0.0.1:8000`
- `dev-local`: run Uvicorn on `127.0.0.1:8002`
- `test`: run `pytest -q`
- `lint`: run `ruff check .`
- `check`: run lint, tests, compile smoke, import check, and JS syntax check
- `clean`: remove generated caches, logs, and safe local runtime artifacts
- `release-zip`: build the GitHub release zip
- `build-portable`: build the portable distribution bundle
- `portable-preflight`: validate the portable bundle before release

Development tasks fail fast when:

- Python is not `3.11`
- Python is not `3.11` or `3.14`
- no virtual environment is active
- required tools such as `pytest`, `ruff`, or `uvicorn` are missing

## Makefile Mapping

The `Makefile` remains available for CI and Unix-like environments.

- `make install`
- `make dev`
- `make dev-local`
- `make test`
- `make lint`
- `make check`
- `make clean`
- `make release-zip`

## Health And Stability

- Health endpoints:
  - `/health`
  - `/health/live`
  - `/health/ready`
- Default worker profile: `desktop_light`
- Market event translation uses provider cooldown handling to reduce repeated `429` noise
- Websocket disconnects are treated as recoverable and reconnect automatically

## Verification Gate

Per `AGENTS.md` and `docs/RELEASE.md`, every change must pass:

```text
[ ] python -m ruff check .              All checks passed
[ ] python -m compileall -q app tests scripts   0 error
[ ] python -c "import app.main"          OK
[ ] python -m pytest -q                  X passed, 0 failed
[ ] node --check app/static/**/*.js       all passed
```

V1.5.5 baseline: **493 passed / 5 skipped / 0 failed** (5 skipped are
pre-existing `chip_structure` tests).

## Cleanup Rules

`python scripts/tasks.py clean` removes only safe generated artifacts:

- `__pycache__`
- `.pytest_cache`
- `.ruff_cache`
- `.mypy_cache`
- `run/`
- `*.pyc`
- `*.log`
- `dist/`
- `build/`
- `site/`
- `htmlcov/`
- `trading_system.db-shm`
- `trading_system.db-wal`
- `trading_system.db-journal`

The cleanup task does not remove:

- `.env`
- `trading_system.db`
- local imported data
- `docs/`
- tests, migrations, or application source files

## Release Packaging

Build the release archive with:

```powershell
python scripts/tasks.py release-zip
```

Output:

```text
dist/trading-system-fastapi-github.zip
```
