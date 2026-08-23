from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests


class CoinMetricsCommunityMarketData:
    """No-key read-only 5m/1m/etc market candles from Coin Metrics Community API.

    Community market data is intentionally used only as a fallback for recent
    public market-data reads. It never authenticates to an exchange and never
    places orders. The community API exposes only a limited recent window, so
    this class is not a replacement for long-range historical archives.
    """

    BASE_URL = "https://community-api.coinmetrics.io/v4"
    SUPPORTED = {"1m", "5m", "10m", "15m", "30m", "1h", "4h", "1d"}

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    @staticmethod
    def _base_quote(symbol: str) -> tuple[str, str]:
        clean = symbol.split(":", 1)[0].strip().upper().replace("-", "/")
        if "/" in clean:
            base, quote = clean.split("/", 1)
            return base, quote
        for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
            if clean.endswith(quote) and len(clean) > len(quote):
                return clean[: -len(quote)], quote
        raise ValueError(f"cannot infer base/quote from symbol: {symbol}")

    def market_id(self, exchange_id: str, symbol: str) -> str:
        exchange = exchange_id.strip().lower()
        if exchange not in {"binance", "bybit", "bitget", "okx"}:
            raise ValueError(f"unsupported Coin Metrics exchange mapping: {exchange_id}")
        base, quote = self._base_quote(symbol)
        return f"{exchange}-{base}{quote}-future"

    def _get(self, path: str, params: dict[str, object]) -> dict:
        response = requests.get(f"{self.base_url}{path}", params=params, timeout=20)
        if response.status_code != 200:
            body = response.text[:300].replace("\n", " ")
            raise RuntimeError(f"Coin Metrics Community HTTP {response.status_code}: {body}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Coin Metrics Community returned a non-object response")
        return payload

    @staticmethod
    def _frame(payload: dict) -> pd.DataFrame:
        rows = payload.get("data") or []
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(
            {
                "timestamp": [x.get("time") for x in rows],
                "open": [x.get("price_open") for x in rows],
                "high": [x.get("price_high") for x in rows],
                "low": [x.get("price_low") for x in rows],
                "close": [x.get("price_close") for x in rows],
                "volume": [x.get("volume") for x in rows],
            }
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
        return df.drop_duplicates("timestamp").set_index("timestamp").sort_index()

    def fetch_latest(self, exchange_id: str, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        if timeframe not in self.SUPPORTED:
            raise ValueError(f"unsupported Coin Metrics Community timeframe: {timeframe}")
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)
        payload = self._get(
            "/timeseries/market-candles",
            {
                "markets": self.market_id(exchange_id, symbol),
                "frequency": timeframe,
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": now.isoformat().replace("+00:00", "Z"),
                "paging_from": "end",
                "page_size": max(1, min(int(limit), 10000)),
                "limit_per_market": max(1, min(int(limit), 10000)),
            },
        )
        return self._frame(payload).tail(limit)

    def fetch_recent_range(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        if timeframe not in self.SUPPORTED:
            raise ValueError(f"unsupported Coin Metrics Community timeframe: {timeframe}")
        stop = end or datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if stop.tzinfo is None:
            stop = stop.replace(tzinfo=timezone.utc)
        if stop - start > timedelta(hours=24, minutes=5):
            raise ValueError("Coin Metrics Community recent-range fallback is limited to about 24 hours")
        payload = self._get(
            "/timeseries/market-candles",
            {
                "markets": self.market_id(exchange_id, symbol),
                "frequency": timeframe,
                "start_time": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "end_time": stop.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "page_size": 10000,
                "limit_per_market": 10000,
            },
        )
        return self._frame(payload)
