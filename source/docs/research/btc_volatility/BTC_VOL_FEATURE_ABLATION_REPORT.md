# BTC Volatility Feature Ablation Report

Status: `NO_CANDIDATE_PROMOTED`

Comparison unit: `existing vol-target` versus `existing vol-target + one
frozen feature`.  Runs must match exposure, risk, stops, fees and decision
timestamps.

Promotion requires three independent years/regimes with consistent effect,
bootstrap 95% support, DSR at 95%, PBO <=0.50, and no greater than 5%
degradation in another primary risk measure.  Results are decomposed into risk
compression, exposure, timing and true incremental information.

No completed point-in-time dataset currently satisfies the protocol, so every
candidate remains `UNRESOLVED` and the canonical strategy is unchanged.
