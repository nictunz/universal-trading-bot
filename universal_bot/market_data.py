from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class MarketDataConfig:
    timeframe: str = "5m"
    limit: int = 500

class MarketDataProvider:
    """Exchange-agnostic interface. Concrete adapters can provide crypto, stocks or ETFs."""
    def fetch_ohlcv(self, symbol: str, config: MarketDataConfig) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_volume_ratio(self, symbol: str, config: MarketDataConfig) -> Optional[float]:
        return None

class CCXTMarketDataProvider(MarketDataProvider):
    def __init__(self, exchange):
        self.exchange = exchange

    def fetch_ohlcv(self, symbol: str, config: MarketDataConfig) -> pd.DataFrame:
        rows = self.exchange.fetch_ohlcv(symbol, timeframe=config.timeframe, limit=config.limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
