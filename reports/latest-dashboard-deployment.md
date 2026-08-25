# Latest dashboard deployment

- Generated UTC: 2026-08-25T10:56:37Z
- Source commit: 864b2c3e05ca38b7b395cba34ddf563f8ac025ed
- Mode: PAPER
- Host: trading-bot-new
- Bind: 0.0.0.0:8000
- Expected URL: http://34.132.172.40:8000/

## Outcomes

- Runtime deploy: success
- Service: success
- HTTP: failure
- Socket: success

## Service
```text
{"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":2,"errors":[],"live_halted":[]}
Dashboard started in PAPER mode.
Local:  http://127.0.0.1:8000/
Tunnel: http://127.0.0.1:8000/ via Termius Local Forwarding
PID:    55131
Log:    /home/kpj3669/.cache/universal-trading-bot-dashboard.log
```

## HTTP checks
```text
http://127.0.0.1:8000/health 200 {"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":2,"errors":[],"live_halted":[]}
```

## Socket
```text
LISTEN 0      2048       127.0.0.1:8000       0.0.0.0:*    users:(("python",pid=50550,fd=13))
```

## App log
```text
```
