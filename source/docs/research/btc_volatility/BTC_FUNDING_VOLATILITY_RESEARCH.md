# BTC Funding Volatility Research

Status: `UNRESOLVED`

Candidate features are level, empirical percentile, robust z-score,
persistence, funding x OI, delta-funding x delta-OI and cross-exchange
dispersion.  Rates are normalized to their actual settlement interval before
comparison; raw rates remain available.

The current +/-0.0003 buckets remain legacy.  High funding in a trend, high
funding in a range, rising OI and falling OI are distinct observations.  No
funding feature may independently produce a bearish or bullish decision.
