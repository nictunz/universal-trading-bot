# Latest dashboard deployment

- Generated UTC: 2026-08-24T02:49:14Z
- Source commit: 8e1105b7db3764cb6a8e82a478eaecead5731f85
- Mode: PAPER
- Host: trading-bot-new
- Bind: 0.0.0.0:8000
- Expected URL: http://34.132.172.40:8000/

## Outcomes

- Runtime deploy: success
- Service: failure
- HTTP: skipped
- Socket: success

## Service
```text
```

## HTTP checks
```text
http://127.0.0.1:8000/health 200 {"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":[]}
http://127.0.0.1:8000/api/state 200 {"strategy":"Volume Strategy FINAL Universal v15","symbols":[{"symbol":"ETH/USDT:USDT","timeframe":"5m","timestamp":"2026-08-23T22:20:00+00:00","position":{"side":null,"size":0.0,"entry":null,"tp":null,"sl":null,"entries":0},"signal":null,"signal_reason":"NO_SIGNAL","values":{"strategy":"Volume Strategy FINAL Universal v15","version":"v15","volume_ratio":0.0,"volume_break":false,"one_bar_volatility":0.012582854034831996,"one_bar_min":0.1,"one_bar_max":1.0,"one_bar_ok":false,"nbar_range":5.552795716730132,"nbar_bars":288,"nbar_block_range":4.912242202237502,"nbar_block_bars":200,"nbar_max_allowed":5.0,"nbar_ok":true,"nbar_blocked":false,"adx":24.361453925335756,"adx_min":20.0,"adx_max":100.0,
http://127.0.0.1:8000/ 200 <!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1480px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;paddin
```

## Socket
```text
LISTEN 0      2048         0.0.0.0:8000       0.0.0.0:*    users:(("python",pid=21532,fd=14))
```

## App log
```text
```
