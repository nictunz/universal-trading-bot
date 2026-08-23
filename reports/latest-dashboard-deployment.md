# Latest dashboard deployment

- Generated UTC: 2026-08-23T17:35:10Z
- Source commit: 33f8df240c983869a291a6771ba0c03015956a41
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
PID:    11778
Log:    /home/kpj3669/.cache/universal-trading-bot-dashboard.log
```

## HTTP checks
```text
http://127.0.0.1:8000/health 200 {"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":[]}
http://127.0.0.1:8000/api/state 200 {"strategy":"Volume Strategy FINAL Universal v15","symbols":[{"symbol":"ETH/USDT:USDT","status":"WAITING","error":"","volume_sources":{},"live_safety":{"enabled":false,"halted":false,"reason":"","consecutive_errors":0,"last_reconciliation":null,"last_data":null,"protection_ok":false,"exchange_position":null,"internal_position":null,"metadata":{}}}]}
http://127.0.0.1:8000/ 200 <!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1380px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;padding:6px 0}.good{color:#42e
```

## Socket
```text
LISTEN 0      2048         0.0.0.0:8000       0.0.0.0:*    users:(("python",pid=11778,fd=12))
```

## App log
```text
```
