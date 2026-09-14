# Latest light self-hosted verification

- Generated UTC: 2026-09-14T10:28:20Z
- Source commit: 05c42e98074c2bfa45c0c4ce41c686478765d0ff
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
...............................................................          [100%]
207 passed in 28.97s
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
