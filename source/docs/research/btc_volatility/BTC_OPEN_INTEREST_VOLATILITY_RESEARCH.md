# BTC Open Interest Volatility Research

Status: `UNRESOLVED`

Research OI level, change, OI/volume, OI/market-cap, perpetual-versus-dated
composition and exchange concentration.  Store native contracts and normalized
USD notionals separately with conversion metadata.

`price change x OI change` quadrants describe possible leverage creation,
covering or deleveraging; they do not assign direction without liquidation and
positioning evidence.  Provider discontinuities and contract-multiplier changes
must split the series rather than appear as OI shocks.
