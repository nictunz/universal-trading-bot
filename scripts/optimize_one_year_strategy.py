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

# Research-only execution assumptions requested by the user.
# order_percent_of_equity is a notional percentage: 500% == 5x account equity.
FIXED = {
    "allow_long": True,
    "allow_short": True,
    "initial_capital": 1_000.0,
    "leverage": 50,
    "backtest_fee_percent": 0.02,
    "backtest_slippage_percent": 0.01,
}


def sample(rng: random.Random, volume_min: float = 1.2, volume_max: float = 15.0) -> dict[str, Any]:
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
    entry_multiplier = round(rng.randrange(10, 31) / 2.0, 1)  # 5.0x .. 15.0x
    return {
        **FIXED,
        "entry_multiplier": entry_multiplier,
        "order_percent_of_equity": entry_multiplier * 100.0,
        "max_pyramiding": rng.randint(1, 3),
        "volume_lookback": rng.randint(20, 160),
        "volume_break_multiplier": round(rng.uniform(volume_min, volume_max), 2),
        "min_one_bar_vol": one_min,
        "max_one_bar_vol": one_max,
        "volatility_bars": rng.choice([12, 24, 36, 48, 72, 96, 144, 200, 288, 432]),
        "tp_vol_multiplier": round(rng.uniform(0.15, 2.5), 2),
        "sl_vol_multiplier": round(rng.uniform(0.20, 3.5), 2),
        "min_tp_percent": tp_min,
        "max_tp_percent": tp_max,
        "min_sl_percent": sl_min,
        "max_sl_percent": sl_max,
        "use_nbar_volatility_block": rng.random() < 0.75,
        "nbar_volatility_bars": rng.choice([12, 24, 36, 48, 72, 96, 144, 200, 288]),
        "max_nbar_volatility": round(rng.uniform(0.8, 10.0), 2),
        "use_adx_filter": rng.random() < 0.65,
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
    # A configuration which exhausts the account is not a viable optimum.
    if trades < 30 or mdd >= 100.0:
        return -1e18 + trades
    return pnl - abs(pnl) * min(mdd, 100) / 200 + min(pfv, 5.0) * 5


def compact(result: dict[str, Any]) -> dict[str, Any]:
    keys = ("trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl",
            "estimated_costs", "fee_percent_per_side", "slippage_percent_per_side",
            "return_percent", "max_drawdown_percent", "data_start", "data_end", "bars")
    return {k: result.get(k) for k in keys}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="ETH/USDT:USDT")
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--trials", type=int, default=300)
    p.add_argument("--seed", type=int, default=50031502)
    p.add_argument("--start-trial", type=int, default=1)
    p.add_argument("--end-trial", type=int, default=0, help="inclusive; 0 means --trials")
    p.add_argument("--replay-trials", default="")
    p.add_argument("--volume-min", type=float, default=1.2)
    p.add_argument("--volume-max", type=float, default=15.0)
    p.add_argument("--output", default="reports/latest-strategy-optimization.json")
    args = p.parse_args()
    if args.volume_min < 0 or args.volume_max <= args.volume_min:
        raise SystemExit("invalid volume multiplier range")
    cache = default_cache_path(args.symbol, args.timeframe)
    if not cache.is_file():
        raise SystemExit(f"cache missing: {cache}")

    rng = random.Random(args.seed)
    candidates = [sample(rng, args.volume_min, args.volume_max) for _ in range(max(1, args.trials))]
    replay = {int(x.strip()) for x in args.replay_trials.split(",") if x.strip()}
    end_trial = args.end_trial if args.end_trial > 0 else args.trials
    selected = [
        (i, params) for i, params in enumerate(candidates, 1)
        if (max(1, args.start_trial) <= i <= min(args.trials, end_trial)) or i in replay
    ]
    ranked: list[dict[str, Any]] = []
    for position, (i, params) in enumerate(selected, 1):
        try:
            engine_params = {k: v for k, v in params.items() if k != "entry_multiplier"}
            result = run_cached_symbol_backtest(
                args.symbol, "crypto", "bitget", args.timeframe,
                overrides=engine_params, database_path=cache,
            )
            fee = float(result.get("fee_percent_per_side") or -1)
            slippage = float(result.get("slippage_percent_per_side") or -1)
            if abs(fee - FIXED["backtest_fee_percent"]) > 1e-12 or abs(slippage - FIXED["backtest_slippage_percent"]) > 1e-12:
                raise RuntimeError(f"fixed cost mismatch: fee={fee} slippage={slippage}")
            ranked.append({"trial": i, "score": score(result), "parameters": params, "result": compact(result)})
            ranked.sort(key=lambda x: x["score"], reverse=True)
            ranked = ranked[:20]
            best = ranked[0]
            print(
                f"{position}/{len(selected)} trial={i}/{len(candidates)} "
                f"entry={best['parameters']['entry_multiplier']}x "
                f"entries={best['parameters']['max_pyramiding']} "
                f"best_pnl={best['result']['pnl']:.4f} "
                f"return={best['result']['return_percent']:.3f}% "
                f"pf={best['result']['profit_factor']} "
                f"mdd={best['result']['max_drawdown_percent']:.3f}% "
                f"trades={best['result']['trades']}",
                flush=True,
            )
        except Exception as exc:
            print(f"{i}/{len(candidates)} failed: {type(exc).__name__}: {exc}", flush=True)

    if not ranked:
        raise SystemExit("no successful optimization trials in selected batch")
    viable = [x for x in ranked if x["score"] > -1e17]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "cache": str(cache),
        "trials_requested": args.trials,
        "trials_executed": len(selected),
        "trial_selection": {"start_trial": args.start_trial, "end_trial": end_trial, "replay_trials": sorted(replay)},
        "trials_ranked": len(ranked),
        "execution_assumptions": {
            "initial_capital_usdt": 1000.0,
            "entry_multiplier_range": [5.0, 15.0],
            "exchange_leverage": 50,
            "max_entries_range": [1, 3],
            "maximum_total_notional_multiplier": 45.0,
            "fee_percent_per_side": 0.02,
            "slippage_percent_per_side": 0.01,
            "volume_break_multiplier_range": [args.volume_min, args.volume_max],
        },
        "objective": "net pnl; reject fewer than 30 trades or MDD >= 100%; drawdown/PF tie-break",
        "warning": "Research only. Results are not automatically applied to PAPER or LIVE.",
        "best": viable[0] if viable else ranked[0],
        "has_viable_candidate": bool(viable),
        "top20": ranked,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["best"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
