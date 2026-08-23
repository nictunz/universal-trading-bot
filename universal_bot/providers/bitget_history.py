from __future__ import annotations

from datetime import datetime, timezone
import time

import pandas as pd
import requests


class BitgetHistoricalMarketData:
    """Read-only Bitget USDT-futures historical candles via the official v2 API.

    The CCXT Bitget pagination path can leave large holes on longer 5m ranges.
    This provider paginates backwards with explicit endTime boundaries and a
    maximum 200 candles per request, matching Bitget's documented history API.
    """

    BASE_URL = "https://api.bitget.com/api/v2/mix/market/history-candles"

    def __init__(self, session: requests.Session | None = None, timeout: int = 20) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def compact_symbol(symbol: str) -> str:
        return symbol.split(":", 1)[0].upper().replace("/", "").replace("-", "")

    @staticmethod
    def timeframe_ms(timeframe: str) -> int:
        value = int(timeframe[:-1])
        unit = timeframe[-1]
        seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}.get(unit)
        if seconds is None:
            raise ValueError(f"unsupported Bitget timeframe: {timeframe}")
        return value * seconds * 1000

    @staticmethod
    def granularity(timeframe: str) -> str:
        if timeframe.endswith("m"):
            return timeframe
        if timeframe.endswith("h"):
            return f"{int(timeframe[:-1])}H"
        if timeframe.endswith("d"):
            return f"{int(timeframe[:-1])}D"
        if timeframe.endswith("w"):
            return f"{int(timeframe[:-1])}W"
        raise ValueError(f"unsupported Bitget timeframe: {timeframe}")

    @staticmethod
    def _ms(dt: datetime) -> int:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)

    def fetch_history(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        symbol_id = self.compact_symbol(symbol)
        step = self.timeframe_ms(timeframe)
        start_ms = self._ms(start)
        end_ms = self._ms(end)
        # Align endTime to the candle boundary. The API may otherwise include
        # one extra candle around an interval boundary.
        cursor = (end_ms // step) * step
        rows: dict[int, list[str]] = {}
        calls = 0

        while cursor >= start_ms:
            params = {
                "symbol": symbol_id,
                "productType": "USDT-FUTURES",
                "granularity": self.granularity(timeframe),
                "endTime": str(cursor),
                "limit": "200",
            }
            r = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
            if r.status_code != 200:
                raise RuntimeError(f"Bitget history HTTP {r.status_code}: {r.text[:180]}")
            payload = r.json()
            if payload.get("code") != "00000":
                raise RuntimeError(f"Bitget history API error: {str(payload)[:220]}")
            batch = payload.get("data") or []
            if not batch:
                break

            timestamps: list[int] = []
            for item in batch:
                if len(item) < 6:
                    continue
                ts = int(item[0])
                timestamps.append(ts)
                if start_ms <= ts <= end_ms:
                    rows[ts] = item
            if not timestamps:
                break
            oldest = min(timestamps)
            if oldest <= start_ms:
                break
            next_cursor = oldest - step
            if next_cursor >= cursor:
                break
            cursor = next_cursor
            calls += 1
            # Stay comfortably below Bitget's public endpoint rate limit.
            if calls % 10 == 0:
                time.sleep(0.10)

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        data = []
        for ts in sorted(rows):
            item = rows[ts]
            data.append([ts, item[1], item[2], item[3], item[4], item[5]])
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna().drop_duplicates("timestamp").set_index("timestamp").sort_index()
