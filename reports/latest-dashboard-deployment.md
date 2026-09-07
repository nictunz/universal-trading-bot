# Latest dashboard deployment

- Generated UTC: 2026-09-07T14:12:10Z
- Source commit: 9bcd2217f1e7a564cac93bab369a83974c2f40fc
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
{"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":[]}
Dashboard started in PAPER mode.
Local:  http://127.0.0.1:8000/
Tunnel: http://127.0.0.1:8000/ via Termius Local Forwarding
PID:    287470
Log:    /home/kpj3669/.cache/universal-trading-bot-dashboard.log
```

## HTTP checks
```text
http://127.0.0.1:8000/health 200 {"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":[]}
http://127.0.0.1:8000/api/state 200 {"strategy":"Volume Strategy FINAL Universal v15","symbols":[{"symbol":"BTC/USDT:USDT","timeframe":"15m","timestamp":"2026-09-07T13:45:00+00:00","position":{"side":null,"size":0.0,"entry":null,"tp":null,"sl":null,"entries":0},"signal":null,"signal_reason":"NO_SIGNAL","values":{"strategy":"Volume Strategy FINAL Universal v15","version":"v15","volume_ratio":0.8077808341481323,"volume_break":false,"one_bar_volatility":0.03062636589809406,"one_bar_min":0.1,"one_bar_max":3.6,"one_bar_ok":false,"nbar_range":1.2398710077990864,"nbar_bars":36,"nbar_block_range":2.0637485032216336,"nbar_block_bars":200,"nbar_max_allowed":6.3,"nbar_ok":true,"nbar_blocked":false,"adx":33.129667402208185,"adx_min":11.6,
http://127.0.0.1:8000/ 200 <!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1480px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;paddin
```

## Socket
```text
LISTEN 0      2048       127.0.0.1:8000       0.0.0.0:*    users:(("python",pid=286068,fd=14))
```

## App log
```text
```
