# Latest light self-hosted verification

- Generated UTC: 2026-09-17T13:22:31Z
- Source commit: 70ff04e5de8d5fe2006dc6a61c11d0d68f14e671
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
........................................................................ [ 26%]
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 24.93s
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
