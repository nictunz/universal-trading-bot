# Latest light self-hosted verification

- Generated UTC: 2026-09-14T09:51:43Z
- Source commit: f1ead4c018251fa59189e76c437095ac3785d1fc
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
........................................................................ [ 34%]
........................................................................ [ 69%]
..............................................................           [100%]
206 passed in 100.00s (0:01:40)
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
