from __future__ import annotations

import argparse
from datetime import datetime, timezone

from universal_bot.config import Settings
from universal_bot.historical import DataRequest, HistoricalDataManager


def parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal Trading Bot historical data backfill")
    parser.add_argument("--symbol", help="Symbol, e.g. BTC/USDT:USDT or SPY")
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--asset-class", choices=["crypto", "stock", "etf"], default=None)
    parser.add_argument("--exchange", default=None, help="CCXT exchange for crypto")
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--start", default=None, help="ISO date/time; overrides START_DATE")
    parser.add_argument("--end", default=None, help="ISO date/time; defaults to now")
    args = parser.parse_args()

    settings = Settings()
    symbols = [x.strip() for x in (args.symbols or args.symbol or settings.symbols).split(",") if x.strip()]
    asset_class = args.asset_class or settings.asset_class
    exchange = args.exchange or settings.exchange
    timeframe = args.timeframe or settings.timeframe
    start = parse_dt(args.start) if args.start else (settings.start_date if settings.use_start_date else None)
    end = parse_dt(args.end) if args.end else datetime.now(timezone.utc)

    manager = HistoricalDataManager(settings.database_url)
    for symbol in symbols:
        request = DataRequest(symbol=symbol, timeframe=timeframe, start=start, end=end,
                              asset_class=asset_class, exchange=exchange)
        inserted, df = manager.sync(request)
        print(f"{symbol} {timeframe}: fetched={inserted}, stored={len(df)}, start={start}, end={end}")


if __name__ == "__main__":
    main()
