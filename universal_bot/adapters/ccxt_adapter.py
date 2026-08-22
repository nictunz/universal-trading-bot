from __future__ import annotations

import pandas as pd
import ccxt

from universal_bot.adapters.base import MarketAdapter


class CCXTAdapter(MarketAdapter):
    asset_class = "crypto"

    def __init__(self, exchange_id: str, api_key: str = "", secret: str = "", password: str = ""):
        exchange_class = getattr(ccxt, exchange_id)
        params = {"enableRateLimit": True}
        if api_key:
            params.update({"apiKey": api_key, "secret": secret})
            if password:
                params["password"] = password
        self.exchange = exchange_class(params)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        rows = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.set_index("timestamp")

    def fetch_volume_sources(self, symbol: str, timeframe: str, limit: int = 1000) -> dict[str, pd.Series]:
        # The caller may instantiate one adapter per exchange. This method is kept
        # separate so the v15 engine can use normalized multi-exchange volume.
        return {"current": self.fetch_ohlcv(symbol, timeframe, limit).volume}

    def equity(self) -> float:
        balance = self.exchange.fetch_balance()
        return float(balance.get("USDT", {}).get("free", 0.0))

    def position(self, symbol: str):
        return None

    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False):
        params = {"reduceOnly": True} if reduce_only else {}
        return self.exchange.create_order(symbol, "market", side.lower(), amount, None, params)
