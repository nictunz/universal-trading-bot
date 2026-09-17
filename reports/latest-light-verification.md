# Latest light self-hosted verification

- Generated UTC: 2026-09-17T01:39:42Z
- Source commit: 94b977fd8d342692e5beb19740f847c2a926dfdc
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 82%]
..............................................                           [100%]
262 passed in 98.32s (0:01:38)
```
## Dashboard
```text
{"health": {"status": "ok", "strategy": "Volume Strategy FINAL Universal v15", "symbols": 1, "errors": [], "live_halted": []}, "state_symbols": 1, "html_bytes": 24764}
```
## Provider
```text
binance_eth= BINANCEFTS_PERP_ETH_USDT
bybit_sol= BYBIT_PERP_SOL_USDT
period_5m= 5MIN
```
