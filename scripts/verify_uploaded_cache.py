from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from universal_bot.fast_backtest import default_cache_path, run_cached_symbol_backtest


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    args = p.parse_args()

    db = default_cache_path(args.symbol, args.timeframe)
    if not db.exists():
        raise SystemExit(f"CACHE MISSING: {db}")

    result = run_cached_symbol_backtest(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        database_path=db,
    )
    print(json.dumps({
        "status": "ok",
        "database": str(db),
        "size_bytes": db.stat().st_size,
        "sha256": sha256_file(db),
        "bars": result["bars"],
        "volume_source_bars": result["volume_source_bars"],
        "trades": result["trades"],
        "win_rate": result["win_rate"],
        "profit_factor": result["profit_factor"],
        "return_percent": result["return_percent"],
        "max_drawdown_percent": result["max_drawdown_percent"],
        "fast_cache": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
