# Current Volatility Baseline Audit

Status: `FROZEN_LEGACY_BASELINE`

| Current rule | Current use | Audit finding |
|---|---|---|
| NATR <=1 / >=3 | monitoring state | Fixed cross-timeframe thresholds |
| NATR 2 / 3.5 | technical classifier | Duplicated but inconsistent thresholds |
| BB width <=5% | compression label | Absolute threshold without distribution context |
| BB width / 90-period mean | `vol_compression` | Ratio buckets are incorrectly described as percentile rank |
| `vol_compression / 100` | transition score multiplier | Direct strategy effect lacks isolated incremental-value evidence |
| ATM IV <=40% / >=65% | derivatives risk | Fixed level ignores history, maturity and source regime |
| Funding +/-0.0003 | crowding state | Level alone ignores OI, persistence and venue dispersion |
| 25D skew +/-0.03 | skew state | Direction labels are stronger than the evidence contract permits |
| Annualized basis >8% | basis state | Fixed threshold ignores tenor and cross-exchange structure |

The legacy fields remain operational during shadow validation.  They must not
be renamed in-place or silently reinterpreted.  A promoted replacement needs
a new `formula_version`; the legacy field then becomes a compatibility alias
for one version and stops contributing to scoring.

## Current call chain

`indicator_monitoring -> analysis_bundle/market_context -> technical_signal_classifier`

`market_context + derivatives dashboard -> strategy_signal.snapshot_builder -> strategy_generator`

`strategy snapshot -> strategy_unified -> terminal_summary -> monitoring/alerts/front-end`
