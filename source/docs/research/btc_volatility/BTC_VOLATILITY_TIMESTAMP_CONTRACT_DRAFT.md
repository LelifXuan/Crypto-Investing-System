# BTC Volatility Timestamp Contract Draft

Status: `IMPLEMENTED_FOR_SHADOW_BASELINE`

Required invariant: `event_time <= available_at <= decision_time`.

- Candle `event_time` is the provider bar timestamp; the estimated close time
  is retained separately.
- `available_at` is when the application could first have observed the value.
- `calculated_at` is not a substitute for source availability.
- Funding settlement, option snapshot, OI publication and liquidation receipt
  retain their distinct timestamps.
- CME observations are stale outside their publication session; crypto venue
  data remains 24/7.
- Joins use backward as-of semantics with a recorded maximum age.  Future or
  synthetic observations fail the snapshot.
