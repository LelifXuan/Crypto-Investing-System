# BTC Implied Volatility Index Research

Status: `DATA_SOURCE_VALIDATED / COMPARISON_PENDING`

| Source | Construction | Availability decision |
|---|---|---|
| Deribit DVOL | Crypto-native volatility index; 24/7 venue | Public historical candle API; first shadow source |
| Volmex BVIV | Multi-tenor crypto implied-volatility family | Public API research candidate; licensing and continuity still audited |
| CME CF BVX/BVXS | 30-day constant-maturity variance-swap replication from CME options | Methodology reference only until licensed data is available |

Deribit endpoint: https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data

Volmex endpoint: https://rest-v1.volmex.finance/api

CME methodology: https://docs.cfbenchmarks.com/CME%20CF%20Bitcoin%20Volatility%20Index%20-%20Real%20Time.pdf

BVX is published during CME calculation days/hours and pre-launch history may
be backtested; it cannot be treated as a 24/7 interchangeable DVOL series.

## Decision

Implement a Deribit public adapter, retain source identity, and return
`source_unavailable` rather than substitute another IV index.  No IV level is
promoted to a risk or directional rule.
