# Latest official archive smoke

- Generated UTC: 2026-08-25T10:54:36Z
- Source commit: d46ebdb3c8240d9572e8af7f3957d8f1c494c8db
- Runner: trading-bot-new
- Unit tests: success
- Real network 4-exchange smoke: success

## Unit tests
```text
...                                                                      [100%]
3 passed in 6.10s
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
Mem:           958Mi       298Mi       424Mi        20Mi       236Mi       503Mi
Swap:          2.0Gi       900Mi       1.1Gi
NAME      TYPE SIZE   USED PRIO
/swapfile file   2G 900.1M   -2
```
