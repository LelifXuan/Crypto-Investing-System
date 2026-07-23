# Cleanup Audit

Policy: audit first, delete only with reference evidence and tests. Current
uncommitted feature work is treated as the working baseline and must not be
reverted by cleanup.

## Classification Legend

- `keep`: still a public route, test fixture, persistence compatibility layer, or
  active source of truth.
- `cleanup`: safe to remove or ignore as generated/runtime artifact.
- `replace later`: valid compatibility path today, but should be collapsed after
  a replacement contract is stable.
- `delete candidate`: likely removable, but requires a dedicated test update or
  migration PR.

## Artifact Cleanup

| Item | Classification | Evidence | Action |
| --- | --- | --- | --- |
| `reports/portable_playwright_screenshots/*.png` | cleanup | Tracked release/export screenshots. Referenced only as an output path by `scripts/sync_portable_local.ps1`; not used as test baselines. | Remove from git and ignore future generated PNGs under that directory. |
| `tests/screenshots/*.png` and `tests/screenshots/verify_pages_report.json` | keep | `tests/verify_pages.py` writes and documents these paths; historical plans reference them as page verification outputs. | Keep tracked unless the verification workflow is redesigned. |
| Root `pytest_err.log` / `pytest_out.log` | cleanup | Empty local pytest output files; logs are already ignored by `*.log`. | Remove local files when present. |
| `__analyze.py` | cleanup | Untracked one-off analysis helper, not imported by app/tests/scripts. | Remove local file when present. |
| `runtime`, `runtime_dev`, `logs`, `.pytest_cache`, `.ruff_cache`, `dist`, `*.egg-info` | cleanup | Runtime/build/cache directories. Most are already ignored and handled by `scripts/clean_workspace.py`. | Keep ignored; do not add generated contents to git. |

## Compatibility and Legacy Register

| Item | Classification | Evidence | Next Action |
| --- | --- | --- | --- |
| `app/api/v1/endpoints/etf.py` | keep | Re-exports the `/etf` compatibility router from `ashare_etf`; API router mounts it and ETF tests cover quote behavior through current services. | Keep until `/etf/*` public compatibility is formally dropped. |
| `app/services/etf_quotes.py` | keep | Compatibility service re-export; direct references exist in code/tests and historical ETF contract comments. | Keep; if removed later, update imports and add a compatibility deprecation test. |
| `/dashboard` web route | keep | `tests/test_health_import.py` requests `/dashboard`; route maps to monitoring overview. | Keep as a stable local shortcut. |
| `/alerts-page` web route | keep | `tests/verify_pages.py` and `tests/test_alert_center_removed.py` document that alert center now routes to AI strategy. | Keep until navigation and historical URLs stop relying on it. |
| `/etf-page` web route | keep | Compatibility alias for A-share ETF page. | Keep unless all bookmarks/tests migrate to `/ashare-etf-page`. |
| `app/static/pages/strategy.js` | replace later | `app/static/main.js` lazy-loads this wrapper; several static tests assert the wrapper and cache-busting path. | Later migrate main.js directly to `pages/strategy/index.js` in a focused frontend PR. |
| `app/static/pages/structure.js` + `pages/structure/index.js` wrapper | replace later | `main.js` loads `pages/structure/index.js`, which dynamically imports the large legacy page module. Static tests inspect both files. | Later split the large page into adapter/render modules before deleting the wrapper. |
| `app/services/signal_service.py` | replace later | Documented in `strategy-refactor-readiness.md`; still protects saved strategy records and compatibility tests. | Keep until save/review flows no longer require legacy payloads. |
| `monitoring_dashboard` legacy technical merge | replace later | Legacy DB observations are still merged with analysis-bundle observations. This protects older caches but may duplicate evidence. | Replace after monitoring and strategy share a market-context dependency contract. |
| `terminal_summary_engine` fallback branches | replace later | Many fallbacks protect missing module data and stale snapshots. | Move source hierarchy into typed data-quality dependencies before deletion. |
| `ashare_etf` legacy rebalance payload fields | keep | API code and tests explicitly support old `cash_to_invest` + `positions` payloads. | Keep until portable clients migrate to the HALO/cash-flow contract. |
| BTC derivatives archive migration | keep | `tests/test_derivatives_archive.py` verifies one-time migration from legacy cache files. | Keep until all portable caches are versioned past the migration window. |

## Refactor Hotspots

- `app/services/terminal_summary_engine.py`: large reasoning and rendering
  adapter. Do not bulk rewrite; extract only tested pure helpers.
- `app/services/monitoring_dashboard.py`: central dashboard aggregation and
  cache behavior. Any cleanup needs monitoring, strategy, and page verification.
- `app/services/indicator_monitoring.py`: source sync and persistence hub; keep
  provider contracts explicit.
- `app/services/macro_overview.py` and `app/services/macro/*`: many provider and
  fallback paths. Cleanup should preserve source-quality metadata.
- `app/static/core/knowledge.js`: catalog data plus schema factory. Always run
  `node --check` and catalog import tests after changes.
- `app/static/styles.css`: shared stylesheet hotspot. Prefer page-scoped
  selectors and avoid cosmetic cleanup without screenshots.

## Cleanup Rules

- Do not remove public URLs, schema fields, or compatibility modules without a
  failing-first test that proves the new contract.
- Generated artifacts should be ignored and removable by `scripts/clean_workspace.py`
  or a documented command.
- A deletion PR should list: reference search, affected tests, rollback path, and
  whether the item was `cleanup`, `replace later`, or `delete candidate`.
