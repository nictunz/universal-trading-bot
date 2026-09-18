# Latest light self-hosted verification

- Generated UTC: 2026-09-18T03:10:56Z
- Source commit: bf0376fd82e24586e46fc1aec86737cc063edd0a
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 77%]
..............................................................           [100%]
278 passed in 24.95s
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
