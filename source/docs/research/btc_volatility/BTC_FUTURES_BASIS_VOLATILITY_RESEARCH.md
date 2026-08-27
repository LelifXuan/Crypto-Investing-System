# BTC Futures Basis Volatility Research

Status: `UNRESOLVED`

Store perpetual basis, dated-future basis, annualized basis, compression,
inversion and venue dispersion.  Annualization uses actual seconds to expiry;
expired or near-zero-tenor contracts are rejected.

Basis, Funding, OI, DVOL and Liquidation are first tested separately.  Their
joint patterns may motivate a later Regime candidate, but the first round does
not construct a weighted score.  The current 8% rule remains a named legacy
diagnostic during shadow validation.
