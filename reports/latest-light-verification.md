# Latest light self-hosted verification

- Generated UTC: 2026-09-14T20:50:31Z
- Source commit: 29c678d0ebb08f0c5d221fbc32d31cbe9a0b4d90
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
........................................................................ [ 68%]
...................................................................      [100%]
211 passed in 120.43s (0:02:00)
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
