# Latest official archive smoke

- Generated UTC: 2026-08-23T19:17:14Z
- Source commit: 5dbed25ad8cad3ea2fd93e38f4eab672b6e784b3
- Runner: trading-bot-new
- Unit tests: success
- Real network 4-exchange smoke: success

## Unit tests
```text
...                                                                      [100%]
3 passed in 4.36s
```
## Four-exchange smoke
```json
{
  "symbol": "ETH/USDT:USDT",
  "bars": 287,
  "four_exchange_volume": true,
  "volume_source_bars": {
    "binance": 288,
    "bitget": 287,
    "okx": 288,
    "bybit": 288
  },
  "volume_source_status": {
    "bitget": {
      "mode": "DIRECT_NATIVE",
      "status": "OK"
    },
    "binance": {
      "mode": "OFFICIAL_ARCHIVE",
      "status": "OK"
    },
    "okx": {
      "mode": "DIRECT",
      "status": "OK"
    },
    "bybit": {
      "mode": "OFFICIAL_ARCHIVE",
      "status": "OK"
    }
  },
  "trades": 0,
  "win_rate": 0.0,
  "return_percent": 0.0,
  "max_drawdown_percent": 0.0
}
```
## Memory
```text
               total        used        free      shared  buff/cache   available
Mem:           958Mi       335Mi       371Mi        20Mi       251Mi       466Mi
Swap:          2.0Gi       528Mi       1.5Gi
NAME      TYPE SIZE   USED PRIO
/swapfile file   2G 527.5M   -2
```
