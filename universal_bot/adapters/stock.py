from __future__ import annotations

import pandas as pd
import yfinance as yf

from universal_bot.adapters.base import MarketAdapter


class YFinanceMarketAdapter(MarketAdapter):
    """Market-data adapter for stocks/ETFs. Execution is intentionally delegated to a broker adapter."""
    asset_class = "stock_etf"

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        interval = {"1m":"1m", "5m":"5m", "15m":"15m", "30m":"30m", "1h":"60m", "1d":"1d"}.get(timeframe, timeframe)
        period = "60d" if interval in {"1m", "5m", "15m", "30m", "60m"} else "max"
        raw = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
        if raw.empty:
            return pd.DataFrame(columns=["open","high","low","close","volume"])
        if hasattr(raw.columns, "levels"):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
        return raw[["open","high","low","close","volume"]].tail(limit)

    def equity(self) -> float:
        raise NotImplementedError("Use a broker execution adapter for stock/ETF equity")

    def position(self, symbol: str):
        raise NotImplementedError("Use a broker execution adapter for stock/ETF positions")

    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False):
        raise NotImplementedError("Use a broker execution adapter for stock/ETF orders")
