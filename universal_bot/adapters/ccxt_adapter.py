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
        self.exchange_id = exchange_id
        self.exchange = exchange_class(params)

    @staticmethod
    def _candidates(symbol: str) -> list[str]:
        if "/" not in symbol:
            return [symbol]
        if ":" in symbol:
            return [symbol, symbol.split(":")[0]]
        base, quote = symbol.split("/", 1)
        return [symbol, f"{base}/{quote}:{quote}"]

    def _fetch(self, exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        last_error = None
        for candidate in self._candidates(symbol):
            try:
                rows = exchange.fetch_ohlcv(candidate, timeframe=timeframe, limit=limit)
                df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
                if df.empty:
                    continue
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                return df.set_index("timestamp")
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        return self._fetch(self.exchange, symbol, timeframe, limit)

    def fetch_volume_sources(self, symbol: str, timeframe: str, limit: int = 1000) -> dict[str, pd.Series]:
        # v15: average normalized volume ratio from Binance, Bitget, OKX, Bybit.
        out: dict[str, pd.Series] = {}
        for exchange_id in ("binance", "bitget", "okx", "bybit"):
            try:
                ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
                df = self._fetch(ex, symbol, timeframe, limit)
                if not df.empty:
                    out[exchange_id] = df.volume
            except Exception:
                continue
        return out

    def equity(self) -> float:
        balance = self.exchange.fetch_balance()
        return float(balance.get("USDT", {}).get("free", 0.0))

    def position(self, symbol: str):
        return None

    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False):
        params = {"reduceOnly": True} if reduce_only else {}
        return self.exchange.create_order(symbol, "market", side.lower(), amount, None, params)
