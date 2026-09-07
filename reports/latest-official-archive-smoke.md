# Latest official archive smoke

- Generated UTC: 2026-09-07T08:36:54Z
- Source commit: 8079141f9fc1493b2a2b4d29f8f500aa5e68ef38
- Runner: trading-bot-new
- Unit tests: success
- Real network 4-exchange smoke: success

## Unit tests
```text
...                                                                      [100%]
3 passed in 26.56s
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
Mem:           958Mi       441Mi       185Mi        18Mi       330Mi       361Mi
Swap:          2.0Gi       1.0Gi       1.0Gi
NAME      TYPE SIZE    USED PRIO
/swapfile file   2G 1007.3M   -2
```
