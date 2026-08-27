# BTC IV-RV Relationship Research

Status: `UNRESOLVED`

Candidate outputs are same-horizon `IV-RV`, `IV/RV`, delta-IV minus delta-RV,
and the four high/low quadrants.  “High” and “low” must come from frozen
point-in-time empirical distributions, not 40%/65% constants.

Alignment contract:

1. Match constant-maturity IV horizon to the RV forecast horizon.
2. Join only when IV `available_at <= decision_time`.
3. Preserve source hours and stale age.
4. Never forward-fill CME observations across a crypto weekend as fresh.

Primary test: existing vol-target versus existing vol-target plus exactly one
IV-RV feature under matched exposure and risk.  Until that test passes, the
quadrants are descriptive and cannot adjust leverage.
