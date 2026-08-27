# BTC Volatility Connectivity Evidence

Checked at: `2026-08-24T12:18Z`

| Source/path | Result | Evidence |
|---|---|---|
| Deribit DVOL direct, environment proxy disabled | `ConnectTimeout` | No direct route was available from this workstation; no empty success was recorded |
| Deribit DVOL configured proxy | HTTP 200 | Seven hourly rows; latest parsed close `44.25` |
| Volmex BVIV direct, environment proxy disabled | HTTP 200 | Six hourly OHLC rows |
| Volmex BVIV configured proxy | HTTP 200 | Six hourly OHLC rows; latest parsed close `47.21091330692171` |

The selected proxy was the redacted local endpoint `127.0.0.1:7890` detected
by the existing network policy.  Connectivity does not certify methodology,
licensing, historical completeness or incremental value.  Deribit direct
failure remains explicit while the proxy path is usable.
