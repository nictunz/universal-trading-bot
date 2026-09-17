# Latest light self-hosted verification

- Generated UTC: 2026-09-17T12:23:32Z
- Source commit: 9d425d5a4c494ad1921368d4b73068a2f6281399
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
........................................................................ [ 79%]
........................................................                 [100%]
272 passed in 24.98s
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
