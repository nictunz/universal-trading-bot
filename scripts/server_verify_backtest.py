from __future__ import annotations

import argparse
import json
import time

from universal_bot.backtest_service import run_symbol_backtest


parser = argparse.ArgumentParser(description="Server-side Universal Bot backtest verification")
parser.add_argument("--symbol", default="ETH/USDT:USDT")
parser.add_argument("--exchange", default="bitget")
parser.add_argument("--timeframe", default="5m")
parser.add_argument("--start", default="2024-01-01")
parser.add_argument("--end", default=None)
args = parser.parse_args()

started = time.perf_counter()
result = run_symbol_backtest(args.symbol, "crypto", args.exchange, args.timeframe, args.start, args.end)
elapsed = time.perf_counter() - started

summary = {
    "symbol": result["symbol"],
    "timeframe": result["timeframe"],
    "data_start": result["data_start"],
    "data_end": result["data_end"],
    "bars": result["bars"],
    "inserted": result["inserted"],
    "trades": result["trades"],
    "wins": result["wins"],
    "win_rate": result["win_rate"],
    "profit_factor": result["profit_factor"],
    "return_percent": result["return_percent"],
    "max_drawdown_percent": result["max_drawdown_percent"],
    "elapsed_seconds": elapsed,
}
print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
