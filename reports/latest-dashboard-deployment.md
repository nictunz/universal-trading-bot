# Latest dashboard deployment

- Generated UTC: 2026-09-09T08:18:47Z
- Source commit: f0c8467e8cf57303d9ead1037e84b16f5a2eaa55
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
PID:    345128
Log:    /home/kpj3669/.cache/universal-trading-bot-dashboard.log
```

## HTTP checks
```text
http://127.0.0.1:8000/health 200 {"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":[]}
http://127.0.0.1:8000/api/state 200 {"strategy":"Volume Strategy FINAL Universal v15","symbols":[{"symbol":"BTC/USDT:USDT","timeframe":"15m","timestamp":"2026-09-09T08:00:00+00:00","position":{"side":null,"size":0.0,"entry":null,"tp":null,"sl":null,"entries":0},"signal":null,"signal_reason":"NO_SIGNAL","values":{"strategy":"Volume Strategy FINAL Universal v15","version":"v15","volume_ratio":3.1808599483876296,"volume_break":false,"one_bar_volatility":0.1638028510277283,"one_bar_min":0.1,"one_bar_max":3.6,"one_bar_ok":true,"nbar_range":1.4708321743102606,"nbar_bars":36,"nbar_block_range":2.7995258098600697,"nbar_block_bars":200,"nbar_max_allowed":6.1,"nbar_ok":true,"nbar_blocked":false,"adx":45.53605613282449,"adx_min":11.6,"ad
http://127.0.0.1:8000/ 200 <!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1480px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;paddin
```

## Socket
```text
LISTEN 0      2048       127.0.0.1:8000       0.0.0.0:*    users:(("python",pid=304301,fd=13))
```

## App log
```text
/home/kpj3669/universal-trading-bot-dashboard/universal_bot/main.py:278: DeprecationWarning: 
        on_event is deprecated, use lifespan event handlers instead.

        Read more about it in the
        [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
        
  @app.on_event("startup")
DASHBOARD_HTTP_BIND host=0.0.0.0 port=8000
RUNTIME_WORKER_START
ERROR:    [Errno 98] error while attempting to bind on address ('0.0.0.0', 8000): address already in use
```
