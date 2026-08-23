# Latest official archive smoke

- Generated UTC: 2026-08-23T16:44:02Z
- Source commit: 6cd638e35a64fa6bdcb397fe8712ea8088a54eae
- Runner: trading-bot-new
- Unit tests: success
- Real network 4-exchange smoke: success

## Unit tests
```text
...                                                                      [100%]
3 passed in 17.29s
```
## Four-exchange smoke
```json
{
  "symbol": "ETH/USDT:USDT",
  "bars": 288,
  "four_exchange_volume": true,
  "volume_source_bars": {
    "binance": 288,
    "bitget": 288,
    "okx": 288,
    "bybit": 288
  },
  "volume_source_status": {
    "bitget": {
      "mode": "DIRECT",
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
Mem:           958Mi       329Mi       394Mi        19Mi       234Mi       471Mi
Swap:          2.0Gi       519Mi       1.5Gi
NAME      TYPE SIZE   USED PRIO
/swapfile file   2G 519.7M   -2
```
