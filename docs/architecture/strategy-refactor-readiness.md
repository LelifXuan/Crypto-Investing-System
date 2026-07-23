# AI Strategy Refactor Readiness

Policy: audit first, no deletion in phase 1.

Default reuse policy: cache first with explicit freshness metadata.

| ID | Path | Classification | Risk | Next Action |
| --- | --- | --- | --- | --- |
| legacy-signal-service | `app/services/signal_service.py` | compatibility | Legacy recommendation service is still referenced by saved strategy records and compatibility tests. | Keep until `StrategySignalService` save/review flows no longer require legacy payload compatibility. |
| strategy-config-v16-fallback | `app/services/strategy_signal/config_loader.py` | compatibility | v17 config loader still falls back to v16 to protect old portable bundles. | Replace only after portable release tests and config migration tests pin v17-only behavior. |
| monitoring-terminal-fallbacks | `app/services/terminal_summary_engine.py` | replace | Many fallback branches protect missing source modules but can obscure source hierarchy. | Move source hierarchy decisions into `MarketContextBuilder.data_quality.dependencies` before deleting fallbacks. |
| monitoring-dashboard-legacy-technical | `app/services/monitoring_dashboard.py` | replace | Legacy technical observations are merged with analysis bundle output and may duplicate evidence. | Prefer market-context dependency metadata once monitoring and strategy share the same context contract. |
| page-cache-key-duplication | `app/services/cache_registry.py` | keep | Cache key functions are intentionally centralized and should remain the single source of cache identity. | Add new shared keys here only; avoid page-local cache key string literals. |
| strategy-page-data-adapter | `app/static/pages/strategy.js` | replace | Data loading and rendering are still in one module, making the upcoming UI layout refactor harder. | After market context is stable, extract bundle normalization into a small adapter before UI redesign. |

## v1.7 Status (2026-07-02)

Read-only probe (§F) completed and confirmed the strategy page was operating on a half-filled market context:

- `MarketContextBuilder.producer` emitted `market_data={}` and `derivatives_features={"key_levels_axis": ...}`, dropping funding/OI/skew/basis/walls/max_pain from `joint_analysis`.
- `OnchainFeatureEngine` had no upstream policy (no DB row with `category="onchain"`), so strategy always rendered "链上数据当前缺失".
- `derivatives_regime` only fuzzy-matched a Chinese summary string, never used structured fields.
- `evidence_trace` rendered internal namespace (`weighted_direction_score`, `higher_tf_constraint + tactical_conflict`) as user-facing text.
- Two confidence sources competed (`mtf_structure.confidence` vs `evidence_trace.confidence`) and disagreed on 1d/4h nodes.
- Frontend `pages/strategy/index.js` only called `/strategy/unified` — never fetched monitoring dashboard / derivatives dashboard / macro overview.

Plan mode refused to execute until root causes were mapped to commits C1–C20. Plan agent returned control with build-mode approval.

## v1.7 Execution Order (21 commits, Q-FINAL = a)

| # | Domain | Commit | Notes |
| --- | --- | --- | --- |
| C0  | docs      | strategy-refactor-readiness update + §F probe summary | This file |
| C1  | macro     | market_context: chip_structure fields (market_data + chip_features) | |
| C2  | network   | market_context: derivatives structured fields (funding/oi/skew/basis/walls/max_pain) | |
| C3a | infra     | onchain: DefiLlama policy adapter + 4 observation seed | |
| C3b | infra     | onchain: sync_onchain triggers DefiLlama | |
| C3c | macro     | market_context: onchain metrics exposure + capital_flow fallback | |
| C3d | test      | onchain policy adapter + integration tests | |
| C4  | config    | market_context: freshness_breakdown flatten | |
| C5  | macro     | regime_engines: multi-source pick + drop in-engine confidence | |
| C6  | macro     | evidence_builder: sole confidence output (3-factor weighted) | |
| C7  | macro     | evidence_builder: human_explanation zh + render field whitelist | |
| C8  | macro     | regime_engines: structured judgment (no string fuzzy match) | |
| C9  | macro     | trade_plan: actual price levels + invalidation real | |
| C10 | macro     | risk_gate: zh message/action | |
| C11 | frontend  | strategy/index.js: parallel 4 endpoint fetch | |
| C12 | frontend  | strategy/adapter.js: merge 4 endpoint + evidence_ref | |
| C13 | frontend  | renderEvidenceTrace: natural language card (drop meta UI) | |
| C14 | frontend  | renderTradePlans: real price levels | |
| C15 | frontend  | renderHorizonStack + Governance: verdict unified + dual column | |
| C16 | frontend  | renderMarketOperation: confidence via evidence_ref | |
| C17 | frontend  | renderRiskPanel: dedupe + footer data-degraded card | |
| C18 | frontend  | styles.css: visual consistency | |
| C19 | test      | pytest full update + new tests + verdict mapping | |
| C20 | docs      | CHANGELOG v1.7 + AGENTS.md §六.2 cross_page_fetch instance check | |

## Scope Confirmed

- 4 endpoints in parallel: `/strategy/unified`, `/monitoring/dashboard`, `/btc-derivatives/dashboard`, `/monitoring/macro-overview`.
- Confidence unified to evidence_trace (single output source).
- Evidence card renders only `human_explanation` + `confidence` + freshness/timeframe; `calculation_rule` / `input_features` / `source_modules` stay in payload for API consumers but are not rendered.
- 4/4 endpoint failure → page-level errorState; otherwise page renders and shows a footer "data degraded" card listing per-endpoint cache_state.
- Different timeframe nodes may produce different verdicts (regime engines now do multi-source pick).
- Verdict mapping (C15):
  - `NO_EDGE` / `CONTEXT_NEUTRAL` → `RANGE_NO_EDGE`
  - `CONTEXT_LONG` + LONG → `STRATEGIC_LONG_TACTICAL_LONG` (strategic TF) / `CONTEXT_ALIGNED_LONG` (tactical TF)
  - `CONTEXT_SHORT` + SHORT → `STRATEGIC_SHORT_TACTICAL_SHORT` / `CONTEXT_ALIGNED_SHORT`
  - `CONTEXT_MISSING` → `DATA_DEGRADED`
- P1 (Etherscan / DeBank / Dune) remain stubbed; only DefiLlama (P0) wired in v1.7.

## Risks

- DefiLlama public endpoint may be region-restricted in mainland China; httpx already swallows HTTPError → strategy stays green with onchain dimension flagged as upstream_missing.
- 4-endpoint parallel fetch may surface historical bug in abort controller — guarded by Promise.allSettled + per-endpoint try/catch in adapter.
- Confidence unification may regress ~6 existing pytest assertions; C19 updates tests in the same change.

## Verify Pages Gate

Per AGENTS.md §六.2, after C11–C17:

```
python tests/verify_pages.py --pages strategy,monitoring-overview
```