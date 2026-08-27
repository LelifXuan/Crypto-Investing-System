# BTC Volatility Data Availability Map

Status: `DRAFT / POINT_IN_TIME_AUDIT_ACTIVE`

| Family | Current source | Historical suitability | Formal use |
|---|---|---|---|
| OHLC realized volatility | Gate.io cached candles | Available across configured timeframes; gaps must be measured | Shadow candidates ready |
| Deribit DVOL | Public JSON-RPC candles | Public; verify earliest date, gaps and methodology changes per run | Shadow ingestion allowed |
| Deribit/OKX option chain | Existing live collectors | Current cross-sections; retained history must be audited | Diagnostic only |
| Volmex BVIV/BVRV | Public REST | Endpoint supports multiple tenors; continuity/licensing audit pending | Research only |
| CME BVX/BVXS | Licensed benchmark | Trading-hour mismatch; pre-launch values may be backtested | Methodology only without license |
| Funding/OI/Basis | Existing multi-provider collectors | Uneven windows and provider breaks | Diagnostic until manifests pass |
| Liquidation | No verified historical source | Insufficient | `source_unavailable` |

Every dataset manifest records first/last event time, observed frequency,
missing ratio, provider/methodology changes, retrieval time, content hash,
license, direct/proxy result and whether values are observed or backtested.

Environment-specific connectivity evidence is recorded in
`BTC_VOLATILITY_CONNECTIVITY_EVIDENCE.md`; it is not generalized into a market
or data-quality conclusion.
