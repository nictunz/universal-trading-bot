# Latest light self-hosted verification

- Generated UTC: 2026-09-17T05:31:19Z
- Source commit: 1a8ffd6cc924dddfdda79ff059fff7f7ae95cc09
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
...............................................                          [100%]
263 passed in 54.58s
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
