# BTC Volatility Term Structure Research

Status: `UNRESOLVED`

Research features:

- constant-maturity front/medium/long IV;
- slope per day-to-expiry, curvature and front-end shock;
- full-curve shift versus isolated inversion;
- source liquidity, quote age and interpolation distance.

The existing first-minus-last ATM IV value is retained as legacy diagnostics
only.  Candidate calculations must interpolate variance, preserve actual DTE,
and reject extrapolation beyond the supported maturity bracket.  No inversion
threshold is frozen until historical coverage and event studies are complete.
