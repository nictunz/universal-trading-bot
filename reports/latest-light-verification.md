# Latest light self-hosted verification

- Generated UTC: 2026-09-13T01:19:08Z
- Source commit: b43ecc414f5de92bbd9c3eb005acfb50ab5087f5
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
........................................................................ [ 40%]
........................................................................ [ 81%]
.................................                                        [100%]
177 passed in 22.69s
```
## Dashboard
```text
{"health": {"status": "ok", "strategy": "Volume Strategy FINAL Universal v15", "symbols": 1, "errors": [], "live_halted": []}, "state_symbols": 1, "html_bytes": 24288}
```
## Provider
```text
binance_eth= BINANCEFTS_PERP_ETH_USDT
bybit_sol= BYBIT_PERP_SOL_USDT
period_5m= 5MIN
```
