# BTC Volatility Surface and Tail Research

Status: `UNRESOLVED`

Candidate cross-sections include 10D/25D put IV, ATM IV, 25D/10D call IV,
25D butterfly, 10D butterfly, smile convexity and wing richness.  Calculations
require a single source, timestamp and expiry slice before constant-maturity
interpolation.

Sparse wings, crossed markets, stale quotes or delta extrapolation produce
`data_insufficient`; ATM values must not be copied into a missing wing.  Tail
richness remains diagnostic until it adds information beyond IV level and RV.
