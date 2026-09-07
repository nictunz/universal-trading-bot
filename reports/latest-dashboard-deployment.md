# Latest dashboard deployment

- Generated UTC: 2026-09-07T12:10:34Z
- Source commit: e4bbc00a54cc89d1024a528f7f3530c6bca5b06d
- Mode: PAPER
- Host: trading-bot-new
- Bind: 0.0.0.0:8000
- Expected URL: http://34.132.172.40:8000/

## Outcomes

- Runtime deploy: success
- Service: success
- HTTP: success
- Socket: success

## Service
```text
{"status":"halted","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":["STALE_MARKET_DATA"]}
Dashboard started in PAPER mode.
Local:  http://127.0.0.1:8000/
Tunnel: http://127.0.0.1:8000/ via Termius Local Forwarding
PID:    281887
Log:    /home/kpj3669/.cache/universal-trading-bot-dashboard.log
```

## HTTP checks
```text
http://127.0.0.1:8000/health 200 {"status":"halted","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":["STALE_MARKET_DATA"]}
http://127.0.0.1:8000/api/state 200 {"strategy":"Volume Strategy FINAL Universal v15","symbols":[{"symbol":"BTC/USDT:USDT","timeframe":"15m","timestamp":"2026-09-07T11:45:00+00:00","position":{"side":null,"size":0.0,"entry":null,"tp":null,"sl":null,"entries":0},"signal":null,"signal_reason":"LIVE_HALTED:STALE_MARKET_DATA","values":{},"stats":{"closed_trades":0.0,"win_rate":0.0,"profit_factor":null,"realized_pnl":0.0,"open_pnl":0.0,"equity":3666.66675067,"live_halted":true,"live_safety_reason":"STALE_MARKET_DATA","protection_ok":true},"error":"","volume_sources":{"binance":{"mode":"MOBILE_RELAY","status":"OK"},"bitget":{"mode":"DIRECT","status":"OK"},"okx":{"mode":"DIRECT","status":"OK"},"bybit":{"mode":"MOBILE_RELAY","status":
http://127.0.0.1:8000/ 200 <!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1480px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;paddin
```

## Socket
```text
LISTEN 0      2048       127.0.0.1:8000       0.0.0.0:*    users:(("python",pid=281453,fd=13))
```

## App log
```text
```
