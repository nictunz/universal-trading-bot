from __future__ import annotations

import gc
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from universal_bot.archive_historical import OfficialArchiveHistoricalDataManager
from universal_bot.backtest_service import run_symbol_backtest, _validate_crypto_data
from universal_bot.config import Settings
from universal_bot.historical import DataRequest

SYMBOL = os.environ.get("BACKTEST_SYMBOL", "ETH/USDT:USDT")
TIMEFRAME = os.environ.get("BACKTEST_TIMEFRAME", "5m")
START = os.environ.get("BACKTEST_START", "2025-08-19")
END = os.environ.get("BACKTEST_END", "2026-08-18")
EXCHANGES = ("binance", "bitget", "okx", "bybit")


def parse_day(value: str, end: bool = False) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.astimezone(timezone.utc)


def month_chunks(start: datetime, end: datetime):
    cursor = start
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        stop = min(end, next_month - timedelta(microseconds=1))
        yield cursor, stop
        cursor = next_month


def symbol_slug(symbol: str) -> str:
    base = symbol.split(":", 1)[0].split("/", 1)[0].strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug or "asset"


def main() -> None:
    os.environ["CRYPTO_VOLUME_PROVIDER"] = "none"
    os.environ["COINAPI_API_KEY"] = ""
    os.environ["USE_FOUR_CRYPTO_EXCHANGES"] = "true"

    cache_dir = Path.home() / ".cache" / "universal-trading-bot"
    cache_dir.mkdir(parents=True, exist_ok=True)
    slug = symbol_slug(SYMBOL)
    db = Path(os.environ.get("ONE_YEAR_DB", str(cache_dir / f"{slug}-1y-{TIMEFRAME}.db")))
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"

    start = parse_day(START)
    end = parse_day(END, end=True)
    settings = Settings()
    manager = OfficialArchiveHistoricalDataManager(
        settings.database_url,
        coinapi_api_key="",
        fallback_exchanges=[],
    )

    print(f"SYMBOL={SYMBOL}", flush=True)
    print(f"ONE_YEAR_DB={db}", flush=True)
    print(f"WINDOW={start.isoformat()} .. {end.isoformat()}", flush=True)

    for exchange in EXCHANGES:
        print(f"\n===== CACHE {exchange.upper()} =====", flush=True)
        for chunk_start, chunk_end in month_chunks(start, end):
            req = DataRequest(
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                start=chunk_start,
                end=chunk_end,
                asset_class="crypto",
                exchange=exchange,
            )
            inserted, df = manager.sync(req)
            if df.empty:
                raise RuntimeError(f"{exchange} returned no data for {chunk_start.date()}..{chunk_end.date()}")
            _validate_crypto_data(df, TIMEFRAME, label=f"{exchange}:{chunk_start:%Y-%m}")
            print(
                f"{exchange:7s} {chunk_start:%Y-%m-%d}..{chunk_end:%Y-%m-%d} "
                f"bars={len(df)} inserted={inserted} mode={manager.last_fetch_status.get(exchange, {}).get('mode', 'CACHE')}",
                flush=True,
            )
            del df
            gc.collect()

    print("\n===== FULL ONE-YEAR BACKTEST =====", flush=True)
    result = run_symbol_backtest(
        symbol=SYMBOL,
        asset_class="crypto",
        exchange="bitget",
        timeframe=TIMEFRAME,
        start=START,
        end=END,
    )

    keys = (
        "symbol",
        "bars",
        "four_exchange_volume",
        "volume_source_bars",
        "volume_source_status",
        "trades",
        "wins",
        "win_rate",
        "profit_factor",
        "pnl",
        "gross_pnl",
        "estimated_costs",
        "return_percent",
        "max_drawdown_percent",
    )
    summary = {key: result[key] for key in keys}
    summary["requested_start"] = START
    summary["requested_end"] = END
    summary["database"] = str(db)

    out = Path(os.environ.get("ONE_YEAR_RESULT", str(cache_dir / f"latest-{slug}-one-year-backtest.json")))
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = cache_dir / "latest-one-year-backtest.json"
    latest.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"RESULT_FILE={out}", flush=True)
    print("BACKTEST COMPLETE", flush=True)


if __name__ == "__main__":
    main()
