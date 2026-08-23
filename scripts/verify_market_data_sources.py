from __future__ import annotations

import argparse
import json

from universal_bot.adapters.ccxt_adapter import CCXTAdapter
from universal_bot.adapters.stock import YFinanceMarketAdapter
from universal_bot.config import Settings


def verify_crypto(symbol: str, timeframe: str, limit: int) -> dict:
    s = Settings(symbol=symbol, timeframe=timeframe, bot_mode="PAPER")
    adapter = CCXTAdapter(
        s.exchange.lower(),
        coinapi_api_key=s.coinapi_api_key if s.crypto_volume_provider.lower() == "coinapi" else "",
        fallback_exchanges=s.crypto_fallback_exchange_list,
    )
    sources = adapter.fetch_volume_sources(symbol, timeframe, limit)
    return {
        "asset_class": "crypto",
        "symbol": symbol,
        "timeframe": timeframe,
        "required": ["binance", "bitget", "okx", "bybit"],
        "available": sorted(sources),
        "all_four_ready": set(sources) == {"binance", "bitget", "okx", "bybit"},
        "status": adapter.volume_source_status(),
        "rows": {name: len(series) for name, series in sources.items()},
        "last_timestamp": {name: str(series.index[-1]) if len(series) else None for name, series in sources.items()},
    }


def verify_traditional(symbol: str, timeframe: str, limit: int, asset_class: str) -> dict:
    adapter = YFinanceMarketAdapter()
    frame = adapter.fetch_ohlcv(symbol, timeframe, limit)
    return {
        "asset_class": asset_class,
        "symbol": symbol,
        "timeframe": timeframe,
        "provider": "yfinance",
        "ready": not frame.empty,
        "rows": len(frame),
        "last_timestamp": str(frame.index[-1]) if not frame.empty else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-class", default="crypto", choices=["crypto", "stock", "etf"])
    parser.add_argument("--symbol", default="ETH/USDT:USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.asset_class == "crypto":
        result = verify_crypto(args.symbol, args.timeframe, args.limit)
    else:
        result = verify_traditional(args.symbol, args.timeframe, args.limit, args.asset_class)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
