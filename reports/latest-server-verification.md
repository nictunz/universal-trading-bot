# Latest self-hosted server verification

- Generated UTC: 2026-08-23T03:16:29Z
- Source commit: d86851ad6def7b0d6a61e6fe05b1a08b5b670474
- Runner: trading-bot-new
- Event: push
- BOT_MODE: PAPER

## Outcomes

| Check | Outcome |
|---|---|
| Prepare | success |
| Compile | success |
| Pytest | failure |
| ETH/USDT 5m backtest | failure |
| 100k indicator benchmark | success |

## Runtime
```text
host=trading-bot-new
kernel=Linux trading-bot-new 6.8.0-1053-gcp #56~22.04.1-Ubuntu SMP Mon Mar 23 20:16:54 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
python=Python 3.10.12
commit=d86851ad6def7b0d6a61e6fe05b1a08b5b670474
started_utc=2026-08-23T03:06:42Z
```

## Pytest
```text
.....F....                                                               [100%]
=================================== FAILURES ===================================
___________ test_live_initialization_fails_closed_without_protection ___________

    def test_live_initialization_fails_closed_without_protection():
        settings = Settings(bot_mode="LIVE", use_start_date=False, use_nbar_volatility_block=False)
        adapter = FakeLiveAdapter(protection=False)
        engine = TradingEngine(settings, adapter, UniversalV15Strategy(settings))
        state = engine.step(frame())
>       assert engine.safety.halted is False
E       AssertionError: assert True is False
E        +  where True = LiveSafety(enabled=True, halted=True, reason='STALE_MARKET_DATA', consecutive_errors=0, last_reconciliation=datetime.d...T', 'size': 0.0, 'entry_price': 0.0}, internal_position={'side': 'FLAT', 'size': 0.0, 'entry_price': 0.0}, metadata={}).halted
E        +    where LiveSafety(enabled=True, halted=True, reason='STALE_MARKET_DATA', consecutive_errors=0, last_reconciliation=datetime.d...T', 'size': 0.0, 'entry_price': 0.0}, internal_position={'side': 'FLAT', 'size': 0.0, 'entry_price': 0.0}, metadata={}) = <universal_bot.engine.TradingEngine object at 0x79d8f75f6b90>.safety

tests/test_live_engine.py:55: AssertionError
=========================== short test summary info ============================
FAILED tests/test_live_engine.py::test_live_initialization_fails_closed_without_protection - AssertionError: assert True is False
 +  where True = LiveSafety(enabled=True, halted=True, reason='STALE_MARKET_DATA', consecutive_errors=0, last_reconciliation=datetime.d...T', 'size': 0.0, 'entry_price': 0.0}, internal_position={'side': 'FLAT', 'size': 0.0, 'entry_price': 0.0}, metadata={}).halted
 +    where LiveSafety(enabled=True, halted=True, reason='STALE_MARKET_DATA', consecutive_errors=0, last_reconciliation=datetime.d...T', 'size': 0.0, 'entry_price': 0.0}, internal_position={'side': 'FLAT', 'size': 0.0, 'entry_price': 0.0}, metadata={}) = <universal_bot.engine.TradingEngine object at 0x79d8f75f6b90>.safety
1 failed, 9 passed in 33.99s
```

## Backtest
```text
/home/kpj3669/actions-runner-trading-bot/_work/_temp/736f2a39-d26b-4661-9bc7-18628ccb071b.sh: line 3: /usr/bin/time: No such file or directory
```

## Indicator benchmark
```text
indicator_100k_bars_seconds=1.0105
```

## Install/compile diagnostics
```text
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
  Created wheel for universal-trading-bot: filename=universal_trading_bot-0.1.0-0.editable-py3-none-any.whl size=3352 sha256=358724af942aaad17081717ad16444ed9a680b9049896faceaa6978ffe96976c
  Stored in directory: /tmp/pip-ephem-wheel-cache-w2aymvap/wheels/0c/89/30/94dd659d1b50423860f7174be41fd80f66371554352395eb8a
Successfully built universal-trading-bot
Installing collected packages: pytz, multitasking, zlib-ng, websockets, uvloop, urllib3, tzdata, typing_extensions, tomli, soupsieve, six, ruff, python-dotenv, pygments, pycparser, protobuf, propcache, pluggy, platformdirs, peewee, packaging, orjson, numpy, lxml, iniconfig, idna, h11, frozenlist, coincurve, click, charset_normalizer, certifi, attrs, async-timeout, annotated-types, annotated-doc, aiohappyeyeballs, uvicorn, typing-inspection, requests, python-dateutil, pydantic-core, multidict, exceptiongroup, cffi, beautifulsoup4, aiosignal, yarl, pytest, pydantic, pandas, curl_cffi, cryptography, anyio, yfinance, starlette, pydantic-settings, aiohttp, fastapi, aiohttp-fast-zlib, ccxt, universal-trading-bot

Successfully installed aiohappyeyeballs-2.7.1 aiohttp-3.14.3 aiohttp-fast-zlib-0.3.0 aiosignal-1.4.0 annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.14.2 async-timeout-5.0.1 attrs-26.1.0 beautifulsoup4-4.15.0 ccxt-4.5.75 certifi-2026.6.17 cffi-2.0.0 charset_normalizer-3.4.7 click-8.4.2 coincurve-21.0.0 cryptography-50.0.0 curl_cffi-0.16.1 exceptiongroup-1.3.1 fastapi-0.141.1 frozenlist-1.8.0 h11-0.16.0 idna-3.18 iniconfig-2.3.0 lxml-6.1.2 multidict-6.7.1 multitasking-0.0.13 numpy-2.2.6 orjson-3.11.9 packaging-26.3 pandas-2.3.3 peewee-4.3.0 platformdirs-4.11.3 pluggy-1.6.0 propcache-0.5.2 protobuf-7.36.0 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 pydantic-settings-2.15.0 pygments-2.21.0 pytest-9.1.1 python-dateutil-2.9.0.post0 python-dotenv-1.2.3 pytz-2026.3.post1 requests-2.34.2 ruff-0.16.4 six-1.17.0 soupsieve-2.9.2 starlette-1.6.0 tomli-2.4.1 typing-inspection-0.4.4 typing_extensions-4.16.0 tzdata-2026.3 universal-trading-bot-0.1.0 urllib3-2.7.0 uvicorn-0.52.4 uvloop-0.22.1 websockets-16.1.1 yarl-1.24.5 yfinance-1.6.0 zlib-ng-1.0.0
```
