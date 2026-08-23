# Latest self-hosted server verification

- Generated UTC: 2026-08-23T06:02:41Z
- Source commit: a79d8835d4f4cfec1dd936be90c3f57e1e8179d2
- Runner: trading-bot-new
- Event: push
- BOT_MODE: PAPER

## Outcomes

| Check | Outcome |
|---|---|
| Prepare | cancelled |
| Compile | skipped |
| Pytest | skipped |
| Bitget public capabilities | skipped |
| ETH/USDT 5m one-year backtest | skipped |
| Performance benchmarks | skipped |

## Runtime
```text
host=trading-bot-new
kernel=Linux trading-bot-new 6.8.0-1053-gcp #56~22.04.1-Ubuntu SMP Mon Mar 23 20:16:54 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
python=Python 3.10.12
commit=a79d8835d4f4cfec1dd936be90c3f57e1e8179d2
started_utc=2026-08-23T05:55:54Z
database_url=sqlite:////home/kpj3669/.cache/universal-trading-bot/historical.db
```

## Pytest
```text
```

## Bitget public capabilities
```text
```

## Backtest
```text
```

## Performance benchmarks
```text
```

## Install/compile diagnostics
```text
Collecting multitasking>=0.0.7 (from yfinance>=0.2.40->universal-trading-bot==0.1.0)
  Using cached multitasking-0.0.13-py3-none-any.whl.metadata (16 kB)
Collecting peewee>=3.16.2 (from yfinance>=0.2.40->universal-trading-bot==0.1.0)
  Using cached peewee-4.3.0-py3-none-any.whl.metadata (10 kB)
Collecting platformdirs>=2.0.0 (from yfinance>=0.2.40->universal-trading-bot==0.1.0)
  Using cached platformdirs-4.11.3-py3-none-any.whl.metadata (5.5 kB)
Collecting protobuf>=3.19.0 (from yfinance>=0.2.40->universal-trading-bot==0.1.0)
  Using cached protobuf-7.36.0-cp310-abi3-manylinux2014_x86_64.whl.metadata (595 bytes)
Collecting websockets>=13.0 (from yfinance>=0.2.40->universal-trading-bot==0.1.0)
  Using cached websockets-16.1.1-cp310-cp310-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
Collecting soupsieve>=1.6.1 (from beautifulsoup4>=4.11.1->yfinance>=0.2.40->universal-trading-bot==0.1.0)
  Using cached soupsieve-2.9.2-py3-none-any.whl.metadata (4.6 kB)
Using cached ccxt-4.5.75-py3-none-any.whl (6.6 MB)
Using cached aiohappyeyeballs-2.7.1-py3-none-any.whl (15 kB)
Using cached aiohttp_fast_zlib-0.3.0-py3-none-any.whl (8.6 kB)
Using cached aiosignal-1.4.0-py3-none-any.whl (7.5 kB)
Using cached attrs-26.1.0-py3-none-any.whl (67 kB)
Using cached certifi-2026.6.17-py3-none-any.whl (133 kB)
Using cached cffi-2.0.0-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (216 kB)
Using cached charset_normalizer-3.4.7-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (216 kB)
Using cached coincurve-21.0.0-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (1.6 MB)
Using cached frozenlist-1.8.0-cp310-cp310-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (219 kB)
Using cached idna-3.18-py3-none-any.whl (65 kB)
Using cached multidict-6.7.1-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (243 kB)
Using cached orjson-3.11.9-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (134 kB)
Using cached propcache-0.5.2-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (60 kB)
Using cached pycparser-3.0-py3-none-any.whl (48 kB)
Using cached typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Using cached urllib3-2.7.0-py3-none-any.whl (131 kB)
Using cached uvloop-0.22.1-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (3.7 MB)
Using cached zlib_ng-1.0.0-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (132 kB)
Using cached aiohttp-3.14.3-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (1.7 MB)
Using cached async_timeout-5.0.1-py3-none-any.whl (6.2 kB)
Using cached cryptography-50.0.0-cp39-abi3-manylinux_2_34_x86_64.whl (4.8 MB)
Using cached requests-2.34.2-py3-none-any.whl (73 kB)
Using cached yarl-1.24.5-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (110 kB)
Using cached fastapi-0.141.1-py3-none-any.whl (131 kB)
Using cached annotated_doc-0.0.5-py3-none-any.whl (5.3 kB)
Using cached numpy-2.2.6-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (16.8 MB)
Using cached pandas-2.3.3-cp310-cp310-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl (12.8 MB)
Using cached pydantic-2.13.4-py3-none-any.whl (472 kB)
Using cached pydantic_core-2.46.4-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
Using cached annotated_types-0.8.0-py3-none-any.whl (13 kB)
Using cached pydantic_settings-2.15.0-py3-none-any.whl (69 kB)
Using cached pytest-9.1.1-py3-none-any.whl (386 kB)
Using cached pluggy-1.6.0-py3-none-any.whl (20 kB)
Using cached exceptiongroup-1.3.1-py3-none-any.whl (16 kB)
Using cached iniconfig-2.3.0-py3-none-any.whl (7.5 kB)
Using cached packaging-26.3-py3-none-any.whl (129 kB)
Using cached pygments-2.21.0-py3-none-any.whl (1.3 MB)
Using cached python_dateutil-2.9.0.post0-py2.py3-none-any.whl (229 kB)
Using cached python_dotenv-1.2.3-py3-none-any.whl (22 kB)
Using cached pytz-2026.3.post1-py2.py3-none-any.whl (508 kB)
Using cached ruff-0.16.4-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (10.3 MB)
Using cached six-1.17.0-py2.py3-none-any.whl (11 kB)
Using cached starlette-1.6.0-py3-none-any.whl (75 kB)
Using cached anyio-4.14.2-py3-none-any.whl (125 kB)
Using cached tomli-2.4.1-py3-none-any.whl (14 kB)
Using cached typing_inspection-0.4.4-py3-none-any.whl (14 kB)
Using cached tzdata-2026.3-py2.py3-none-any.whl (348 kB)
Using cached uvicorn-0.52.4-py3-none-any.whl (79 kB)
Using cached click-8.4.2-py3-none-any.whl (119 kB)
Using cached h11-0.16.0-py3-none-any.whl (37 kB)
Using cached yfinance-1.6.0-py3-none-any.whl (148 kB)
Using cached beautifulsoup4-4.15.0-py3-none-any.whl (109 kB)
Using cached curl_cffi-0.16.1-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (13.5 MB)
Using cached lxml-6.1.2-cp310-cp310-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl (5.3 MB)
Using cached multitasking-0.0.13-py3-none-any.whl (16 kB)
Using cached peewee-4.3.0-py3-none-any.whl (179 kB)
Using cached platformdirs-4.11.3-py3-none-any.whl (23 kB)
Using cached protobuf-7.36.0-cp310-abi3-manylinux2014_x86_64.whl (340 kB)
Using cached soupsieve-2.9.2-py3-none-any.whl (37 kB)
Using cached websockets-16.1.1-cp310-cp310-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (186 kB)
Building wheels for collected packages: universal-trading-bot
  Building editable for universal-trading-bot (pyproject.toml): started
  Building editable for universal-trading-bot (pyproject.toml): finished with status 'done'
  Created wheel for universal-trading-bot: filename=universal_trading_bot-0.1.0-0.editable-py3-none-any.whl size=3352 sha256=6e5693c48e4c6882cfc3f8a3818c7261b199ddbd1d80e1562f8ff7541d72144a
  Stored in directory: /tmp/pip-ephem-wheel-cache-26mic1li/wheels/0c/89/30/94dd659d1b50423860f7174be41fd80f66371554352395eb8a
Successfully built universal-trading-bot
Installing collected packages: pytz, multitasking, zlib-ng, websockets, uvloop, urllib3, tzdata, typing_extensions, tomli, soupsieve, six, ruff, python-dotenv, pygments, pycparser, protobuf, propcache, pluggy, platformdirs, peewee, packaging, orjson, numpy, lxml, iniconfig, idna, h11, frozenlist, coincurve, click, charset_normalizer, certifi, attrs, async-timeout, annotated-types, annotated-doc, aiohappyeyeballs, uvicorn, typing-inspection, requests, python-dateutil, pydantic-core, multidict, exceptiongroup, cffi, beautifulsoup4, aiosignal, yarl, pytest, pydantic, pandas, curl_cffi, cryptography, anyio, yfinance, starlette, pydantic-settings, aiohttp, fastapi, aiohttp-fast-zlib, ccxt, universal-trading-bot
```
