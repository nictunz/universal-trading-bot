# Latest light self-hosted verification

- Generated UTC: 2026-09-07T19:51:44Z
- Source commit: 6df8aa2d73cf505637675a7f93c8c4b7ed57493c
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
........................................................................ [ 63%]
.........................................                                [100%]
113 passed in 11.40s
```
## Dashboard
```text
{"health": {"status": "ok", "strategy": "Volume Strategy FINAL Universal v15", "symbols": 1, "errors": [], "live_halted": []}, "state_symbols": 1, "html_bytes": 23235}
```
## Provider
```text
binance_eth= BINANCEFTS_PERP_ETH_USDT
bybit_sol= BYBIT_PERP_SOL_USDT
period_5m= 5MIN
```
