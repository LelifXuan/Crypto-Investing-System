# BTC Realized Volatility Baseline

Status: `IMPLEMENTED_IN_SHADOW / EVIDENCE_PENDING`

## Candidate definitions

- Close RV: `sqrt(A * mean(log(C_t/C_t-1)^2))`.
- EWMA: `sigma_t^2=lambda*sigma_t-1^2+(1-lambda)*r_t^2`.
- Parkinson, Garman-Klass and Rogers-Satchell use OHLC log ranges.
- Yang-Zhang combines open-gap, open-close and Rogers-Satchell variance.
- Bipower variation estimates the continuous component; jump variation is the
  non-negative difference between close RV variance and bipower variance.
- Bollinger bandwidth is `(upper-lower)/middle`; compression rank is the
  rolling empirical mid-rank, not bandwidth divided by its mean.

Annualization uses `365*24*60*60 / bar_seconds`, matching BTC 24/7 trading.
The frozen neighborhoods are 7/14/21, 21/30/45 and 60/90/120 observations;
these are research candidates, not formal thresholds.

## BTC suitability notes

Range estimators are more information-efficient under ideal OHLC sampling but
carry assumptions about drift, gaps and microstructure.  Yang-Zhang's
overnight component has a different interpretation in a continuous BTC market,
so it must be compared rather than presumed superior.

References: Parkinson (1980), Garman & Klass (1980), Rogers & Satchell (1991),
Yang & Zhang (2000), and the realized-volatility literature summarized by the
Chicago Fed: https://www.chicagofed.org/publications/working-papers/2008/wp2008-14

## Decision

No estimator is promoted.  Shadow snapshots publish every candidate with its
window and formula version for single-feature ablation.
