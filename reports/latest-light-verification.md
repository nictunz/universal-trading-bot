# Latest light self-hosted verification

- Generated UTC: 2026-09-17T00:28:21Z
- Source commit: 4bde6d98765a4053b69bb3ab9ea60630b7b4792c
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
........................................................................ [ 28%]
........................................................................ [ 56%]
........................................................................ [ 84%]
.........................................                                [100%]
257 passed in 71.70s (0:01:11)
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
