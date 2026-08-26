from __future__ import annotations

import argparse
import json
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from universal_bot.fast_backtest import default_cache_path, run_cached_symbol_backtest

FEE = 0.02
SLIPPAGE = 0.01
TARGET_RETURN = 900.0


def _candidate_key(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _windows(start: str, end: str) -> list[tuple[str, str]]:
    first = pd.Timestamp(start).tz_convert("UTC").normalize()
    last = pd.Timestamp(end).tz_convert("UTC").normalize()
    windows: list[tuple[str, str]] = []
    cursor = first
    while True:
        window_end = cursor + pd.DateOffset(months=3) - timedelta(microseconds=1)
        if window_end > last + timedelta(days=1):
            break
        windows.append((cursor.isoformat(), window_end.isoformat()))
        cursor += pd.DateOffset(months=1)
    return windows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--report", action="append", required=True)
    parser.add_argument("--top-per-report", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    candidates: dict[str, dict[str, Any]] = {}
    assumptions: list[dict[str, Any]] = []
    data_start = None
    data_end = None
    for name in args.report:
        payload = json.loads(Path(name).read_text(encoding="utf-8"))
        if payload["symbol"] != args.symbol:
            raise SystemExit(f"symbol mismatch in {name}")
        fixed = payload["execution_assumptions"]
        assert fixed["initial_capital_usdt"] == 1000.0
        assert fixed["fee_percent_per_side"] == FEE
        assert fixed["slippage_percent_per_side"] == SLIPPAGE
        assert fixed["entry_multiplier_range"] == [5.0, 15.0]
        assert fixed["exchange_leverage"] == 50
        assert fixed["max_entries_range"] == [1, 3]
        assert fixed["volume_break_multiplier_range"] == [3.0, 25.0]
        assumptions.append(fixed)
        for row in payload["top20"][: args.top_per_report]:
            candidates.setdefault(_candidate_key(row["parameters"]), row["parameters"])
            result = row["result"]
            data_start = min(x for x in (data_start, result.get("data_start")) if x) if data_start else result.get("data_start")
            data_end = max(x for x in (data_end, result.get("data_end")) if x) if data_end else result.get("data_end")

    if not candidates or not data_start or not data_end:
        raise SystemExit("no candidates or data range")
    windows = _windows(data_start, data_end)
    if len(windows) < 8:
        raise SystemExit(f"insufficient rolling windows: {len(windows)}")

    cache = default_cache_path(args.symbol, args.timeframe)
    evaluated: list[dict[str, Any]] = []
    for number, params in enumerate(candidates.values(), 1):
        engine_params = {k: v for k, v in params.items() if k != "entry_multiplier"}
        rows = []
        for start, end in windows:
            result = run_cached_symbol_backtest(
                args.symbol, "crypto", "bitget", args.timeframe,
                start=start, end=end, overrides=engine_params, database_path=cache,
            )
            if _finite(result.get("fee_percent_per_side"), -1) != FEE or _finite(result.get("slippage_percent_per_side"), -1) != SLIPPAGE:
                raise RuntimeError("fixed cost mismatch")
            rows.append({
                "start": start,
                "end": end,
                "return_percent": _finite(result.get("return_percent")),
                "pnl": _finite(result.get("pnl")),
                "win_rate": _finite(result.get("win_rate")),
                "profit_factor": result.get("profit_factor"),
                "max_drawdown_percent": _finite(result.get("max_drawdown_percent")),
                "trades": int(result.get("trades") or 0),
            })
        returns = [x["return_percent"] for x in rows]
        pfs = [_finite(x["profit_factor"]) for x in rows]
        trades = [x["trades"] for x in rows]
        evaluated.append({
            "parameters": params,
            "summary": {
                "windows": len(rows),
                "target_10x_hits": sum(x >= TARGET_RETURN for x in returns),
                "median_return_percent": float(pd.Series(returns).median()),
                "worst_return_percent": min(returns),
                "best_return_percent": max(returns),
                "median_profit_factor": float(pd.Series(pfs).median()),
                "worst_max_drawdown_percent": max(x["max_drawdown_percent"] for x in rows),
                "median_trades": float(pd.Series(trades).median()),
                "windows_with_30_trades": sum(x >= 30 for x in trades),
            },
            "rolling_windows": rows,
        })
        print(f"{number}/{len(candidates)} rolling candidates complete", flush=True)

    evaluated.sort(key=lambda x: (
        x["summary"]["target_10x_hits"],
        x["summary"]["median_return_percent"],
        x["summary"]["worst_return_percent"],
        -x["summary"]["worst_max_drawdown_percent"],
    ), reverse=True)
    output = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "method": "rolling 3-month windows advanced by one month",
        "target_return_percent": TARGET_RETURN,
        "candidate_source_reports": args.report,
        "candidate_count": len(evaluated),
        "fixed_assumptions": assumptions[0],
        "warning": "Research only. Not automatically applied to PAPER or LIVE.",
        "best_robust_candidate": evaluated[0],
        "candidates": evaluated,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
