# Latest self-hosted server verification

- Generated UTC: 2026-08-23T06:21:20Z
- Source commit: 4387c26cdcfaa56fda7e2966bd3a228924bc2376
- Runner: trading-bot-new
- Event: push
- BOT_MODE: PAPER

## Outcomes

| Check | Outcome |
|---|---|
| Prepare | success |
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | failure |
| Bitget public capabilities | success |
| ETH/USDT 5m one-year backtest | failure |
| Performance benchmarks | success |

## Runtime
```text
host=trading-bot-new
kernel=Linux trading-bot-new 6.8.0-1053-gcp #56~22.04.1-Ubuntu SMP Mon Mar 23 20:16:54 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
python=Python 3.10.12
commit=4387c26cdcfaa56fda7e2966bd3a228924bc2376
started_utc=2026-08-23T06:06:14Z
database_url=sqlite:////home/kpj3669/.cache/universal-trading-bot/historical.db
```

## Pytest
```text
.................                                                        [100%]
17 passed in 29.25s
```

## Dashboard HTTP smoke
```text
Traceback (most recent call last):
  File "<stdin>", line 22, in <module>
RuntimeError: dashboard smoke failed: <urlopen error [Errno 111] Connection refused>
```

## Bitget public capabilities
```text
{
  "exchange": "bitget",
  "ccxt_version": "4.5.75",
  "symbol": "ETH/USDT:USDT",
  "active": true,
  "swap": true,
  "linear": true,
  "contract": true,
  "contract_size": 1,
  "fetch_positions": true,
  "set_leverage": true,
  "set_margin_mode": true,
  "set_position_mode": true,
  "attached_stop_loss": {
    "triggerPriceType": {
      "last": true,
      "mark": true,
      "index": true
    },
    "price": false
  },
  "attached_take_profit": {
    "triggerPriceType": {
      "last": true,
      "mark": true,
      "index": true
    },
    "price": false
  },
  "ohlcv_rows": 5,
  "ohlcv_last": "2026-08-23T06:10:00+00:00"
}
```

## Backtest
```text
backtest_range=2025-08-23..2026-08-23
Traceback (most recent call last):
  File "/home/kpj3669/actions-runner-trading-bot/_work/universal-trading-bot/universal-trading-bot/scripts/server_verify_backtest.py", line 19, in <module>
    result = run_symbol_backtest(args.symbol, "crypto", args.exchange, args.timeframe, args.start, args.end)
  File "/home/kpj3669/actions-runner-trading-bot/_work/universal-trading-bot/universal-trading-bot/universal_bot/backtest_service.py", line 107, in run_symbol_backtest
    _validate_crypto_data(df, timeframe, label=exchange.lower())
  File "/home/kpj3669/actions-runner-trading-bot/_work/universal-trading-bot/universal-trading-bot/universal_bot/backtest_service.py", line 48, in _validate_crypto_data
    raise ValueError(f"incomplete {label} data: {len(gaps)} gap(s), largest gap {largest:.1f} minutes")
ValueError: incomplete bitget data: 96 gap(s), largest gap 4000.0 minutes
```

## Performance benchmarks
```text
indicator_100k_bars_seconds=1.0021
[BACKTEST] 289/100,000 (0.3%) trades=0
[BACKTEST] 5,000/100,000 (5.0%) trades=0
[BACKTEST] 10,000/100,000 (10.0%) trades=0
[BACKTEST] 15,000/100,000 (15.0%) trades=0
[BACKTEST] 20,000/100,000 (20.0%) trades=0
[BACKTEST] 25,000/100,000 (25.0%) trades=0
[BACKTEST] 30,000/100,000 (30.0%) trades=0
[BACKTEST] 35,000/100,000 (35.0%) trades=0
[BACKTEST] 40,000/100,000 (40.0%) trades=0
[BACKTEST] 45,000/100,000 (45.0%) trades=0
[BACKTEST] 50,000/100,000 (50.0%) trades=0
[BACKTEST] 55,000/100,000 (55.0%) trades=0
[BACKTEST] 60,000/100,000 (60.0%) trades=0
[BACKTEST] 65,000/100,000 (65.0%) trades=0
[BACKTEST] 70,000/100,000 (70.0%) trades=0
[BACKTEST] 75,000/100,000 (75.0%) trades=0
[BACKTEST] 80,000/100,000 (80.0%) trades=0
[BACKTEST] 85,000/100,000 (85.0%) trades=0
[BACKTEST] 90,000/100,000 (90.0%) trades=0
[BACKTEST] 95,000/100,000 (95.0%) trades=0
[BACKTEST] 100,000/100,000 (100.0%) trades=0
cached_strategy_100k_bars_seconds=493.7201
cached_strategy_100k_trades=0
```

## Install/compile diagnostics
```text
Requirement already satisfied: uvicorn>=0.29 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (0.52.4)
Collecting yfinance>=0.2.40 (from universal-trading-bot==0.1.0)
  Using cached yfinance-1.6.0-py3-none-any.whl.metadata (6.7 kB)
Requirement already satisfied: pytest>=8.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (9.1.1)
Requirement already satisfied: ruff>=0.5 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from universal-trading-bot==0.1.0) (0.16.4)
Requirement already satisfied: certifi==2026.6.17 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2026.6.17)
Requirement already satisfied: requests<3,>=2.32 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2.34.2)
Collecting cryptography<51,>=50 (from ccxt>=4.0->universal-trading-bot==0.1.0)
  Using cached cryptography-50.0.0-cp39-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
Requirement already satisfied: typing_extensions==4.16.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (4.16.0)
Collecting aiohttp<3.15,>=3.14.3 (from ccxt>=4.0->universal-trading-bot==0.1.0)
  Using cached aiohttp-3.14.3-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (8.3 kB)
Requirement already satisfied: yarl<2,>=1.20 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.24.5)
Collecting aiohttp-fast-zlib==0.3.0 (from ccxt>=4.0->universal-trading-bot==0.1.0)
  Using cached aiohttp_fast_zlib-0.3.0-py3-none-any.whl.metadata (5.7 kB)
Requirement already satisfied: zlib-ng==1.0.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.0.0)
Requirement already satisfied: uvloop==0.22.1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (0.22.1)
Requirement already satisfied: orjson==3.11.9 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.11.9)
Requirement already satisfied: coincurve==21.0.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (21.0.0)
Requirement already satisfied: aiohappyeyeballs==2.7.1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2.7.1)
Requirement already satisfied: aiosignal==1.4.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.4.0)
Requirement already satisfied: attrs==26.1.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (26.1.0)
Requirement already satisfied: frozenlist==1.8.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (1.8.0)
Requirement already satisfied: multidict==6.7.1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (6.7.1)
Requirement already satisfied: propcache==0.5.2 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (0.5.2)
Requirement already satisfied: cffi==2.0.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2.0.0)
Requirement already satisfied: pycparser==3.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.0)
Requirement already satisfied: charset_normalizer==3.4.7 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.4.7)
Requirement already satisfied: idna==3.18 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (3.18)
Requirement already satisfied: urllib3==2.7.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from ccxt>=4.0->universal-trading-bot==0.1.0) (2.7.0)
Requirement already satisfied: async-timeout<6.0,>=4.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from aiohttp<3.15,>=3.14.3->ccxt>=4.0->universal-trading-bot==0.1.0) (5.0.1)
Collecting starlette>=0.46.0 (from fastapi>=0.110->universal-trading-bot==0.1.0)
  Using cached starlette-1.6.0-py3-none-any.whl.metadata (6.4 kB)
Requirement already satisfied: typing-inspection>=0.4.2 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from fastapi>=0.110->universal-trading-bot==0.1.0) (0.4.4)
Requirement already satisfied: annotated-doc>=0.0.2 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from fastapi>=0.110->universal-trading-bot==0.1.0) (0.0.5)
Requirement already satisfied: python-dateutil>=2.8.2 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pandas>=2.0->universal-trading-bot==0.1.0) (2.9.0.post0)
Requirement already satisfied: pytz>=2020.1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pandas>=2.0->universal-trading-bot==0.1.0) (2026.3.post1)
Requirement already satisfied: tzdata>=2022.7 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pandas>=2.0->universal-trading-bot==0.1.0) (2026.3)
Requirement already satisfied: annotated-types>=0.6.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pydantic>=2.0->universal-trading-bot==0.1.0) (0.8.0)
Requirement already satisfied: pydantic-core==2.46.4 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pydantic>=2.0->universal-trading-bot==0.1.0) (2.46.4)
Requirement already satisfied: exceptiongroup>=1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pytest>=8.0->universal-trading-bot==0.1.0) (1.3.1)
Requirement already satisfied: iniconfig>=1.0.1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pytest>=8.0->universal-trading-bot==0.1.0) (2.3.0)
Requirement already satisfied: packaging>=22 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pytest>=8.0->universal-trading-bot==0.1.0) (26.3)
Requirement already satisfied: pluggy<2,>=1.5 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pytest>=8.0->universal-trading-bot==0.1.0) (1.6.0)
Requirement already satisfied: pygments>=2.7.2 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pytest>=8.0->universal-trading-bot==0.1.0) (2.21.0)
Requirement already satisfied: tomli>=1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from pytest>=8.0->universal-trading-bot==0.1.0) (2.4.1)
Requirement already satisfied: six>=1.5 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from python-dateutil>=2.8.2->pandas>=2.0->universal-trading-bot==0.1.0) (1.17.0)
Collecting anyio<5,>=3.6.2 (from starlette>=0.46.0->fastapi>=0.110->universal-trading-bot==0.1.0)
  Using cached anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
Requirement already satisfied: click>=7.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from uvicorn>=0.29->universal-trading-bot==0.1.0) (8.4.2)
Requirement already satisfied: h11>=0.8 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from uvicorn>=0.29->universal-trading-bot==0.1.0) (0.16.0)
Requirement already satisfied: beautifulsoup4>=4.11.1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (4.15.0)
Collecting curl_cffi>=0.15 (from yfinance>=0.2.40->universal-trading-bot==0.1.0)
  Using cached curl_cffi-0.16.1-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (17 kB)
Requirement already satisfied: lxml>=4.9.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (6.1.2)
Requirement already satisfied: multitasking>=0.0.7 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (0.0.13)
Requirement already satisfied: peewee>=3.16.2 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (4.3.0)
Requirement already satisfied: platformdirs>=2.0.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (4.11.3)
Requirement already satisfied: protobuf>=3.19.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (7.36.0)
Requirement already satisfied: websockets>=13.0 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from yfinance>=0.2.40->universal-trading-bot==0.1.0) (16.1.1)
Requirement already satisfied: soupsieve>=1.6.1 in /home/kpj3669/.cache/universal-trading-bot-ci-venv/lib/python3.10/site-packages (from beautifulsoup4>=4.11.1->yfinance>=0.2.40->universal-trading-bot==0.1.0) (2.9.2)
Using cached ccxt-4.5.75-py3-none-any.whl (6.6 MB)
Using cached aiohttp_fast_zlib-0.3.0-py3-none-any.whl (8.6 kB)
Using cached aiohttp-3.14.3-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (1.7 MB)
Using cached cryptography-50.0.0-cp39-abi3-manylinux_2_34_x86_64.whl (4.8 MB)
Using cached fastapi-0.141.1-py3-none-any.whl (131 kB)
Using cached pydantic_settings-2.15.0-py3-none-any.whl (69 kB)
Using cached starlette-1.6.0-py3-none-any.whl (75 kB)
Using cached anyio-4.14.2-py3-none-any.whl (125 kB)
Using cached yfinance-1.6.0-py3-none-any.whl (148 kB)
Using cached curl_cffi-0.16.1-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (13.5 MB)
Building wheels for collected packages: universal-trading-bot
  Building editable for universal-trading-bot (pyproject.toml): started
  Building editable for universal-trading-bot (pyproject.toml): finished with status 'done'
  Created wheel for universal-trading-bot: filename=universal_trading_bot-0.1.0-0.editable-py3-none-any.whl size=3352 sha256=129ad221e600073ad31b0d3cb129830dc0f3a5458d690d135093a3754e30f765
  Stored in directory: /tmp/pip-ephem-wheel-cache-nrz8je1k/wheels/0c/89/30/94dd659d1b50423860f7174be41fd80f66371554352395eb8a
Successfully built universal-trading-bot
Installing collected packages: curl_cffi, cryptography, anyio, yfinance, starlette, pydantic-settings, aiohttp, fastapi, aiohttp-fast-zlib, ccxt, universal-trading-bot

Successfully installed aiohttp-3.14.3 aiohttp-fast-zlib-0.3.0 anyio-4.14.2 ccxt-4.5.75 cryptography-50.0.0 curl_cffi-0.16.1 fastapi-0.141.1 pydantic-settings-2.15.0 starlette-1.6.0 universal-trading-bot-0.1.0 yfinance-1.6.0
```
