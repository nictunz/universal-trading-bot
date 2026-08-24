# Latest dashboard deployment

- Generated UTC: 2026-08-24T12:45:58Z
- Source commit: 2410af8af5314215a2d69f5cb623645ddd6eb430
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
Obtaining file:///home/kpj3669/universal-trading-bot-dashboard
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Checking if build backend supports build_editable: started
  Checking if build backend supports build_editable: finished with status 'done'
  Getting requirements to build editable: started
  Getting requirements to build editable: finished with status 'done'
  Preparing editable metadata (pyproject.toml): started
  Preparing editable metadata (pyproject.toml): finished with status 'done'
Requirement already satisfied: pandas>=2.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (2.3.3)
Requirement already satisfied: numpy>=1.24 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (2.2.6)
Requirement already satisfied: requests>=2.32 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (2.34.2)
Requirement already satisfied: python-dotenv>=1.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (1.2.3)
Requirement already satisfied: pydantic>=2.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (2.13.4)
Requirement already satisfied: pydantic-settings>=2.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (2.15.0)
Requirement already satisfied: ccxt>=4.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (4.5.75)
Requirement already satisfied: fastapi>=0.110 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (0.141.1)
Requirement already satisfied: uvicorn>=0.29 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (0.52.4)
Requirement already satisfied: yfinance>=0.2.40 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (1.6.0)
Requirement already satisfied: certifi==2026.6.17 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2026.6.17)
Requirement already satisfied: cryptography<51,>=50 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (50.0.0)
Requirement already satisfied: typing_extensions==4.16.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (4.16.0)
Requirement already satisfied: aiohttp<3.15,>=3.14.3 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.14.3)
Requirement already satisfied: yarl<2,>=1.20 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.24.5)
Requirement already satisfied: aiohttp-fast-zlib==0.3.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (0.3.0)
Requirement already satisfied: zlib-ng==1.0.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.0.0)
Requirement already satisfied: uvloop==0.22.1 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (0.22.1)
Requirement already satisfied: orjson==3.11.9 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.11.9)
Requirement already satisfied: coincurve==21.0.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (21.0.0)
Requirement already satisfied: aiohappyeyeballs==2.7.1 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2.7.1)
Requirement already satisfied: aiosignal==1.4.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.4.0)
Requirement already satisfied: attrs==26.1.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (26.1.0)
Requirement already satisfied: frozenlist==1.8.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.8.0)
Requirement already satisfied: multidict==6.7.1 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (6.7.1)
Requirement already satisfied: propcache==0.5.2 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (0.5.2)
Requirement already satisfied: cffi==2.0.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2.0.0)
Requirement already satisfied: pycparser==3.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.0)
Requirement already satisfied: charset_normalizer==3.4.7 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.4.7)
Requirement already satisfied: idna==3.18 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.18)
Requirement already satisfied: urllib3==2.7.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2.7.0)
Requirement already satisfied: async-timeout<6.0,>=4.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from aiohttp<3.15,>=3.14.3->ccxt>=4.0->universal-trading-bot==0.1.0) (5.0.1)
Requirement already satisfied: starlette>=0.46.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from fastapi>=0.110->universal-trading-bot==0.1.0) (1.6.0)
Requirement already satisfied: typing-inspection>=0.4.2 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from fastapi>=0.110->universal-trading-bot==0.1.0) (0.4.4)
Requirement already satisfied: annotated-doc>=0.0.2 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from fastapi>=0.110->universal-trading-bot==0.1.0) (0.0.5)
Requirement already satisfied: python-dateutil>=2.8.2 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from pandas>=2.0->universal-trading-bot==0.1.0) (2.9.0.post0)
Requirement already satisfied: pytz>=2020.1 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from pandas>=2.0->universal-trading-bot==0.1.0) (2026.3.post1)
Requirement already satisfied: tzdata>=2022.7 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from pandas>=2.0->universal-trading-bot==0.1.0) (2026.3)
Requirement already satisfied: annotated-types>=0.6.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from pydantic>=2.0->universal-trading-bot==0.1.0) (0.8.0)
Requirement already satisfied: pydantic-core==2.46.4 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from pydantic>=2.0->universal-trading-bot==0.1.0) (2.46.4)
Requirement already satisfied: six>=1.5 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from python-dateutil>=2.8.2->pandas>=2.0->universal-trading-bot==0.1.0) (1.17.0)
Requirement already satisfied: anyio<5,>=3.6.2 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from starlette>=0.46.0->fastapi>=0.110->universal-trading-bot==0.1.0) (4.14.2)
Requirement already satisfied: exceptiongroup>=1.0.2 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from anyio<5,>=3.6.2->starlette>=0.46.0->fastapi>=0.110->universal-trading-bot==0.1.0) (1.3.1)
Requirement already satisfied: click>=7.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from uvicorn>=0.29->universal-trading-bot==0.1.0) (8.4.2)
Requirement already satisfied: h11>=0.8 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from uvicorn>=0.29->universal-trading-bot==0.1.0) (0.16.0)
Requirement already satisfied: beautifulsoup4>=4.11.1 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (4.15.0)
Requirement already satisfied: curl_cffi>=0.15 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (0.16.1)
Requirement already satisfied: lxml>=4.9.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (6.1.2)
Requirement already satisfied: multitasking>=0.0.7 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (0.0.13)
Requirement already satisfied: peewee>=3.16.2 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (4.3.0)
Requirement already satisfied: platformdirs>=2.0.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (4.11.3)
Requirement already satisfied: protobuf>=3.19.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (7.36.0)
Requirement already satisfied: websockets>=13.0 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (16.1.1)
Requirement already satisfied: soupsieve>=1.6.1 in /home/kpj3669/.cache/universal-trading-bot-dashboard-venv/lib/python3.10/site-packages (from beautifulsoup4>=4.11.1->yfinance>=0.2.40->universal-trading-bot==0.1.0) (2.9.2)
Building wheels for collected packages: universal-trading-bot
  Building editable for universal-trading-bot (pyproject.toml): started
  Building editable for universal-trading-bot (pyproject.toml): finished with status 'done'
  Created wheel for universal-trading-bot: filename=universal_trading_bot-0.1.0-0.editable-py3-none-any.whl size=3413 sha256=3b6c3f7f23b23499536c1aba6af1cbc7ae6ec19bc46388b65086431bf22591db
  Stored in directory: /tmp/pip-ephem-wheel-cache-lna1iq0c/wheels/ad/01/ea/fdf70051f0e4728ec463290a7f83b2e73eedb4df406597681f
Successfully built universal-trading-bot
Installing collected packages: universal-trading-bot
  Attempting uninstall: universal-trading-bot
    Found existing installation: universal-trading-bot 0.1.0
    Uninstalling universal-trading-bot-0.1.0:
      Successfully uninstalled universal-trading-bot-0.1.0
Successfully installed universal-trading-bot-0.1.0
{"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":[]}
Dashboard started in PAPER mode.
Local:  http://127.0.0.1:8000/
Tunnel: http://127.0.0.1:8000/ via Termius Local Forwarding
PID:    32742
Log:    /home/kpj3669/.cache/universal-trading-bot-dashboard.log
```

## HTTP checks
```text
http://127.0.0.1:8000/health 200 {"status":"ok","strategy":"Volume Strategy FINAL Universal v15","symbols":1,"errors":[],"live_halted":[]}
http://127.0.0.1:8000/api/state 200 {"strategy":"Volume Strategy FINAL Universal v15","symbols":[{"symbol":"ETH/USDT:USDT","timeframe":"5m","timestamp":"2026-08-24T12:40:00+00:00","position":{"side":null,"size":0.0,"entry":null,"tp":null,"sl":null,"entries":0},"signal":null,"signal_reason":"NO_SIGNAL","values":{"strategy":"Volume Strategy FINAL Universal v15","version":"v15","volume_ratio":0.0,"volume_break":false,"one_bar_volatility":0.051651858465916516,"one_bar_min":0.1,"one_bar_max":1.0,"one_bar_ok":false,"nbar_range":5.069197774948059,"nbar_bars":288,"nbar_block_range":3.5237309120924523,"nbar_block_bars":200,"nbar_max_allowed":5.0,"nbar_ok":true,"nbar_blocked":false,"adx":28.968623194629632,"adx_min":20.0,"adx_max":100.0
http://127.0.0.1:8000/ 200 <!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1480px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;paddin
```

## Socket
```text
LISTEN 0      2048         0.0.0.0:8000       0.0.0.0:*    users:(("python",pid=32742,fd=13))
```

## App log
```text
```
