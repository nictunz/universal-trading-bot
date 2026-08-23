from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests


class CoinAPIMarketData:
    """Read-only CoinAPI OHLCV provider used when venue public APIs are unavailable.

    This provider never places orders. It maps perpetual crypto contracts to
    CoinAPI's normalized symbol identifiers and returns exchange-native OHLCV.
    """

    EXCHANGE_IDS = {
        "binance": "BINANCEFTS",
        "bybit": "BYBIT",
        "bitget": "BITGET",
        "okx": "OKEX",
    }
    PERIOD_IDS = {
        "1m": "1MIN",
        "2m": "2MIN",
        "3m": "3MIN",
        "4m": "4MIN",
        "5m": "5MIN",
        "6m": "6MIN",
        "10m": "10MIN",
        "15m": "15MIN",
        "20m": "20MIN",
        "30m": "30MIN",
        "1h": "1HRS",
        "2h": "2HRS",
        "3h": "3HRS",
        "4h": "4HRS",
        "6h": "6HRS",
        "8h": "8HRS",
        "12h": "12HRS",
        "1d": "1DAY",
        "1w": "7DAY",
        "1M": "1MTH",
    }

    def __init__(self, api_key: str, base_url: str = "https://rest.coinapi.io") -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _base_quote(symbol: str) -> tuple[str, str]:
        clean = symbol.split(":", 1)[0].strip().upper()
        if "/" not in clean:
            for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
                if clean.endswith(quote) and len(clean) > len(quote):
                    return clean[: -len(quote)], quote
            raise ValueError(f"cannot infer base/quote from symbol: {symbol}")
        base, quote = clean.split("/", 1)
        return base, quote

    def symbol_id(self, exchange_id: str, symbol: str) -> str:
        venue = self.EXCHANGE_IDS.get(exchange_id.lower())
        if not venue:
            raise ValueError(f"unsupported CoinAPI exchange mapping: {exchange_id}")
        base, quote = self._base_quote(symbol)
        return f"{venue}_PERP_{base}_{quote}"

    def _period_id(self, timeframe: str) -> str:
        period = self.PERIOD_IDS.get(timeframe)
        if not period:
            raise ValueError(f"unsupported CoinAPI timeframe: {timeframe}")
        return period

    def _get(self, path: str, params: dict[str, object]) -> list[dict]:
        if not self.enabled:
            raise RuntimeError("CoinAPI fallback is not configured; COINAPI_API_KEY is empty")
        response = requests.get(
            f"{self.base_url}{path}",
            headers={"X-CoinAPI-Key": self.api_key},
            params=params,
            timeout=25,
        )
        if response.status_code != 200:
            body = response.text[:300].replace("\n", " ")
            raise RuntimeError(f"CoinAPI HTTP {response.status_code}: {body}")
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("CoinAPI returned a non-list OHLCV response")
        return payload

    @staticmethod
    def _frame(payload: list[dict]) -> pd.DataFrame:
        if not payload:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(
            {
                "timestamp": [x.get("time_period_start") for x in payload],
                "open": [x.get("price_open") for x in payload],
                "high": [x.get("price_high") for x in payload],
                "low": [x.get("price_low") for x in payload],
                "close": [x.get("price_close") for x in payload],
                "volume": [x.get("volume_traded") for x in payload],
            }
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
        return df.drop_duplicates("timestamp").set_index("timestamp").sort_index()

    def fetch_latest(self, exchange_id: str, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        sid = self.symbol_id(exchange_id, symbol)
        payload = self._get(
            f"/v1/ohlcv/{sid}/latest",
            {"period_id": self._period_id(timeframe), "limit": max(1, min(int(limit), 100000))},
        )
        return self._frame(payload)

    @staticmethod
    def _tf_seconds(timeframe: str) -> int:
        value = int(timeframe[:-1])
        unit = timeframe[-1]
        return value * {"m": 60, "h": 3600, "d": 86400, "w": 604800, "M": 2592000}[unit]

    def fetch_history(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime | None,
    ) -> pd.DataFrame:
        sid = self.symbol_id(exchange_id, symbol)
        period_id = self._period_id(timeframe)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        stop = end or datetime.now(timezone.utc)
        if stop.tzinfo is None:
            stop = stop.replace(tzinfo=timezone.utc)

        # Keep each request comfortably below CoinAPI's 100k-row limit.
        chunk = timedelta(seconds=self._tf_seconds(timeframe) * 40000)
        cursor = start
        frames: list[pd.DataFrame] = []
        while cursor <= stop:
            chunk_end = min(stop, cursor + chunk)
            payload = self._get(
                f"/v1/ohlcv/{sid}/history",
                {
                    "period_id": period_id,
                    "time_start": cursor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "time_end": chunk_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "limit": 50000,
                },
            )
            frame = self._frame(payload)
            if not frame.empty:
                frames.append(frame)
            if chunk_end >= stop:
                break
            cursor = chunk_end + timedelta(seconds=self._tf_seconds(timeframe))
        if not frames:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        out = pd.concat(frames).sort_index()
        out = out.loc[~out.index.duplicated(keep="last")]
        start_ts = pd.Timestamp(start).tz_convert("UTC")
        end_ts = pd.Timestamp(stop).tz_convert("UTC")
        return out[(out.index >= start_ts) & (out.index <= end_ts)]
