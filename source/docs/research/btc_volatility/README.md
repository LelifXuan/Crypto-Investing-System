# BTC Native Volatility Research

Status: `RESEARCH_ONLY / SHADOW`

This directory is the human-readable companion to
`btc_volatility_research_registry.v1.json`.  Reports are ordered; a later
report may not promote a feature that failed or skipped an earlier gate.

No document in this directory changes canonical direction, position size,
leverage, stops, or permissions.  `UNRESOLVED` is a valid final result.

## Reproduction contract

- All observations carry `event_time`, `available_at`, `calculated_at`, source,
  formula version and parameter-set ID.
- Values are persisted as `numeric(38,18)` and exposed as decimal strings.
- Candidate families and parameter neighborhoods are frozen before outcomes
  are inspected.
- First-round tests are single-feature ablations against the existing
  realized-volatility target; composite scores and ML are prohibited.
- Synthetic history and silent neutral-value filling are prohibited.
