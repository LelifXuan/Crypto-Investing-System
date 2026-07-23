# System Architecture

This repository is now a local-first FastAPI trading intelligence system with a
server-rendered SPA shell, background precompute workers, cached page snapshots,
and several domain-specific analysis pipelines.

## Runtime Entry Points

- `app/main.py` builds the FastAPI application, mounts `/static`, registers API
  and web routers, starts configured workers, and queues first-page prewarm
  hints for core dashboards.
- `app/api/router.py` mounts the versioned REST API under `settings.api_v1_prefix`.
  Endpoint modules should remain thin: validate request parameters, construct a
  repository/service, and return schema objects.
- `app/web/router.py` renders the shared SPA template for page URLs such as
  `/monitoring-page`, `/strategy-page`, `/structure-page`, and compatibility
  aliases such as `/dashboard`, `/alerts-page`, and `/etf-page`.
- `app/templates/page.html` and `app/static/main.js` are the browser bootstrap
  path. Page modules live in `app/static/pages`, shared frontend helpers in
  `app/static/core`, and cross-page UI utilities in `app/static/ui`.

## Backend Layers

- `app/db/models` contains SQLAlchemy persistence models.
- `app/repositories` owns database access and should not contain product
  scoring or rendering decisions.
- `app/schemas` contains public DTOs used by API responses and service
  boundaries.
- `app/services` contains business logic. Large domains are split into packages
  when they have their own contracts, helpers, or source adapters:
  `macro`, `btc_derivatives`, `strategy_signal`, `strategy_unified`,
  `structure`, `onchain`, `translation`, and `network`.
- `app/cache`, `app/services/cache_registry.py`, `app/services/page_snapshot_cache.py`,
  and `app/services/precompute.py` define cache identity, freshness, and
  precompute coordination. Page-local string cache keys should be avoided.
- `app/workers` hosts long-running background workers for market data,
  indicator monitoring, event feeds, translation, and page precompute.

## Main Product Domains

- Monitoring overview combines macro, technical observations, structure,
  alerts, cross-asset context, and terminal summaries.
- Technical analysis uses analysis bundles, indicator monitoring, signal
  classification, and frontend chart modules.
- Market structure lives under `app/services/structure` with a matching SPA
  page module. Structure services should publish snapshot payloads rather than
  leaking page-only formatting upstream.
- AI strategy is split between legacy strategy-signal scoring and the newer
  unified strategy layer. Compatibility paths are documented in
  `docs/cleanup-audit.md` and should be removed only after tests prove they are
  no longer public or persistence dependencies.
- Macro data is provider-driven: `app/services/macro/providers` fetches raw
  sources, transforms normalize fields, and scoring/overview services assemble
  page-ready context.
- BTC derivatives and A-share ETF modules keep their own source/cache adapters
  because they have separate upstream availability and refresh contracts.

## Frontend Boundaries

- `app/static/main.js` is responsible for routing, lazy loading, lifecycle
  handling, and global page state.
- `app/static/pages/*.js` should own one page experience. If a page grows large,
  split it into a directory with an `index.js` lifecycle module and focused
  render/adapter files.
- `app/static/core/api.js` is the REST client and cache invalidation layer.
  Page modules should prefer it over handwritten `fetch` calls.
- `app/static/core/knowledge.js` is a catalog artifact consumed by the knowledge
  page and tooltips; syntax checks and import tests are required after edits.
- `app/static/styles.css` is currently a high-complexity shared stylesheet. New
  selectors should stay page-scoped with `body[data-page="..."]` when possible.

## Runtime and Report Artifacts

- Runtime data belongs under ignored directories such as `runtime`, `runtime_dev`,
  `logs`, `cache`, or `reports`, not in source modules.
- `tests/screenshots` is a tracked verification baseline/report area used by
  page checks and should not be deleted as generic clutter.
- One-off Playwright export images under `reports/portable_playwright_screenshots`
  are generated release artifacts and should not remain tracked.

## High-Complexity Hotspots

The following files are intentionally called out before future refactors:

- `app/services/terminal_summary_engine.py`
- `app/services/monitoring_dashboard.py`
- `app/services/indicator_monitoring.py`
- `app/services/macro_overview.py`
- `app/services/strategy_signal/*`
- `app/services/strategy_unified/*`
- `app/static/core/knowledge.js`
- `app/static/styles.css`

Treat changes in these areas as workflow or reasoning changes: keep edits small,
add focused regression tests, and run page verification when frontend behavior or
cross-page data flow is affected.
