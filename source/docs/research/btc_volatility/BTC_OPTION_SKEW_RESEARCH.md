# BTC Option Skew Research

Status: `UNRESOLVED`

Canonical research convention records both:

- `25D risk reversal = call_25d_iv - put_25d_iv`;
- legacy `put_call_skew = put_25d_iv - call_25d_iv`.

Every payload must expose the convention to prevent sign inversion.  Delta
selection, interpolation band, expiry/DTE, bid/ask quality and provider are
part of the formula metadata.

Upside skew, downside skew and symmetric wings are option-demand states, not
bullish/bearish votes.  The existing +/-3 vol-point classifier stays legacy
until point-in-time episode and ablation evidence passes.
