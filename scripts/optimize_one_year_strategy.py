from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from universal_bot.config import Settings
from universal_bot.fast_backtest import default_cache_path, run_cached_symbol_backtest

FIXED = {
    "allow_long": True,
    "allow_short": True,
    "max_pyramiding": 2,
    "order_percent_of_equity": 5.0,
}


def sample(rng: random.Random) -> dict[str, Any]:
    one_min = round(rng.uniform(0.05, 0.55), 2)
    one_max = round(rng.uniform(max(one_min + 0.15, 0.4), 2.5), 2)
    tp_min = round(rng.uniform(0.10, 0.80), 2)
    tp_max = round(rng.uniform(max(tp_min + 0.10, 0.5), 3.0), 2)
    sl_min = round(rng.uniform(0.15, 1.20), 2)
    sl_max = round(rng.uniform(max(sl_min + 0.15, 0.8), 4.0), 2)
    os_max = round(rng.uniform(18, 42), 1)
    os_min = round(rng.uniform(0, max(1, os_max - 8)), 1)
    ob_min = round(rng.uniform(58, 82), 1)
    ob_max = round(rng.uniform(min(99, ob_min + 8), 100), 1)
    use_adx = rng.random() < 0.65
    use_nbar = rng.random() < 0.75
    return {
        **FIXED,
        "volume_lookback": rng.randint(20, 160),
        "volume_break_multiplier": round(rng.uniform(1.2, 15.0), 2),
        "min_one_bar_vol": one_min,
        "max_one_bar_vol": one_max,
        "volatility_bars": rng.choice([12, 24, 36, 48, 72, 96, 144, 200, 288, 432]),
        "tp_vol_multiplier": round(rng.uniform(0.15, 2.5), 2),
        "sl_vol_multiplier": round(rng.uniform(0.20, 3.5), 2),
        "min_tp_percent": tp_min,
        "max_tp_percent": tp_max,
        "min_sl_percent": sl_min,
        "max_sl_percent": sl_max,
        "use_nbar_volatility_block": use_nbar,
        "nbar_volatility_bars": rng.choice([12, 24, 36, 48, 72, 96, 144, 200, 288]),
        "max_nbar_volatility": round(rng.uniform(0.8, 10.0), 2),
        "use_adx_filter": use_adx,
        "adx_length": rng.randint(5, 30),
        "adx_min": round(rng.uniform(5, 35), 1),
        "adx_max": round(rng.uniform(45, 100), 1),
        "use_rsi_filter": True,
        "rsi_length": rng.randint(3, 24),
        "rsi_oversold_min": os_min,
        "rsi_oversold_max": os_max,
        "rsi_overbought_min": ob_min,
        "rsi_overbought_max": ob_max,
        "cooldown_bars": rng.randint(0, 36),
        "reentry_bars": rng.randint(0, 24),
        "block_weekend": rng.random() < 0.15,
        "excluded_hours": rng.choice(["", "00", "00,13,15,16,17,18,23", "13,15,16,17,18,23"]),
    }


def score(result: dict[str, Any]) -> float:
    pnl = float(result.get("pnl") or 0)
    mdd = float(result.get("max_drawdown_percent") or 0)
    pf = result.get("profit_factor")
    pfv = float(pf) if pf is not None and math.isfinite(float(pf)) else 0.0
    trades = int(result.get("trades") or 0)
    if trades < 30:
        return -1e18 + trades
    return pnl - abs(pnl) * min(mdd, 100) / 200 + min(pfv, 5.0) * 500


def compact(result: dict[str, Any]) -> dict[str, Any]:
    keys = ("trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl",
            "estimated_costs", "return_percent", "max_drawdown_percent",
            "data_start", "data_end", "bars")
    return {k: result.get(k) for k in keys}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="ETH/USDT:USDT")
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--trials", type=int, default=300)
    p.add_argument("--seed", type=int, default=1502)
    p.add_argument("--output", default="reports/latest-strategy-optimization.json")
    args = p.parse_args()
    cache = default_cache_path(args.symbol, args.timeframe)
    if not cache.is_file():
        raise SystemExit(f"cache missing: {cache}")

    rng = random.Random(args.seed)
    defaults = {k: getattr(Settings(), k) for k in sample(random.Random(0))}
    candidates = [defaults]
    candidates.extend(sample(rng) for _ in range(max(1, args.trials - 1)))
    ranked: list[dict[str, Any]] = []
    for i, params in enumerate(candidates, 1):
        try:
            result = run_cached_symbol_backtest(
                args.symbol, "crypto", "bitget", args.timeframe,
                overrides=params, database_path=cache,
            )
            ranked.append({"trial": i, "score": score(result), "parameters": params, "result": compact(result)})
            ranked.sort(key=lambda x: x["score"], reverse=True)
            ranked = ranked[:20]
            best = ranked[0]
            print(f"{i}/{len(candidates)} best_pnl={best['result']['pnl']:.4f} "
                  f"pf={best['result']['profit_factor']} mdd={best['result']['max_drawdown_percent']:.3f} "
                  f"trades={best['result']['trades']}", flush=True)
        except Exception as exc:
            print(f"{i}/{len(candidates)} failed: {type(exc).__name__}: {exc}", flush=True)

    if not ranked:
        raise SystemExit("no successful optimization trials")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "cache": str(cache),
        "trials_requested": args.trials,
        "trials_ranked": len(ranked),
        "live_limits": {"max_entry_multiplier": 15.0, "max_entries": 2, "max_total_multiplier": 30.0},
        "objective": "net pnl with minimum 30 trades and drawdown/PF tie-break adjustment",
        "warning": "Optimization is research output. PAPER forward validation is required before LIVE.",
        "best": ranked[0],
        "top20": ranked,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["best"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
