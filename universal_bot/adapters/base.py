from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd


class MarketAdapter(ABC):
    asset_class: str = "unknown"

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_volume_sources(self, symbol: str, timeframe: str, limit: int = 1000) -> dict[str, pd.Series]:
        return {}

    @abstractmethod
    def equity(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def position(self, symbol: str):
        raise NotImplementedError

    @abstractmethod
    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False, **kwargs):
        raise NotImplementedError

    def configure_live(self, symbol: str, leverage: int, margin_mode: str, require_one_way: bool = True) -> dict:
        return {"ok": True, "supported": False}

    def protection_status(self, symbol: str) -> dict:
        return {"ok": False, "supported": False, "reason": "protection_status_not_implemented"}

    def cancel_protection(self, symbol: str) -> None:
        return None
