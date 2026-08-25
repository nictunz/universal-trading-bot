from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import random
import time
import zipfile

import pandas as pd
import requests


class OfficialArchiveMarketData:
    """Read-only historical market data from exchange-operated public archives.

    Binance USD-M futures are read from data.binance.vision 5m/other kline ZIPs.
    Bybit linear futures are reconstructed from public.bybit.com daily trade
    archives. No API key is used and this provider never places orders.
    """

    BINANCE_BASE = "https://data.binance.vision/data/futures/um"
    BYBIT_BASE = "https://public.bybit.com/trading"

    def __init__(self, session: requests.Session | None = None, timeout: int = 40) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def compact_symbol(symbol: str) -> str:
        clean = symbol.split(":", 1)[0].upper().replace("/", "").replace("-", "")
        if not clean:
            raise ValueError("symbol is empty")
        return clean

    @staticmethod
    def _utc(dt: datetime) -> datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

    @staticmethod
    def _empty() -> pd.DataFrame:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _get_bytes(self, url: str) -> bytes | None:
        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                r = self.session.get(url, timeout=(15, self.timeout))
                if r.status_code == 404:
                    return None
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise requests.HTTPError(f"archive HTTP {r.status_code}: {url}", response=r)
                if r.status_code != 200:
                    raise RuntimeError(f"archive HTTP {r.status_code}: {url}")
                if not r.content:
                    raise requests.ConnectionError(f"empty archive response: {url}")
                return r.content
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                last_error = exc
                if attempt == 4:
                    break
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.0, 0.75))
        raise RuntimeError(f"archive download failed after 4 attempts: {url}") from last_error

    @staticmethod
    def _binance_zip(content: bytes) -> pd.DataFrame:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if not names:
                return OfficialArchiveMarketData._empty()
            raw = pd.read_csv(zf.open(names[0]), header=None)
        if raw.shape[1] < 6:
            raise RuntimeError("unexpected Binance archive schema")
        ts = pd.to_numeric(raw.iloc[:, 0], errors="coerce")
        out = pd.DataFrame({
            "timestamp": pd.to_datetime(ts, unit="ms", utc=True, errors="coerce"),
            "open": pd.to_numeric(raw.iloc[:, 1], errors="coerce"),
            "high": pd.to_numeric(raw.iloc[:, 2], errors="coerce"),
            "low": pd.to_numeric(raw.iloc[:, 3], errors="coerce"),
            "close": pd.to_numeric(raw.iloc[:, 4], errors="coerce"),
            "volume": pd.to_numeric(raw.iloc[:, 5], errors="coerce"),
        }).dropna()
        if out.empty:
            return OfficialArchiveMarketData._empty()
        return out.drop_duplicates("timestamp").set_index("timestamp").sort_index()

    def _binance_month(self, symbol: str, timeframe: str, year: int, month: int) -> pd.DataFrame:
        name = f"{symbol}-{timeframe}-{year:04d}-{month:02d}.zip"
        url = f"{self.BINANCE_BASE}/monthly/klines/{symbol}/{timeframe}/{name}"
        data = self._get_bytes(url)
        return self._binance_zip(data) if data else self._empty()

    def _binance_day(self, symbol: str, timeframe: str, day: datetime) -> pd.DataFrame:
        ds = day.strftime("%Y-%m-%d")
        name = f"{symbol}-{timeframe}-{ds}.zip"
        url = f"{self.BINANCE_BASE}/daily/klines/{symbol}/{timeframe}/{name}"
        data = self._get_bytes(url)
        return self._binance_zip(data) if data else self._empty()

    def fetch_binance(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        sym = self.compact_symbol(symbol)
        start, end = self._utc(start), self._utc(end)
        frames: list[pd.DataFrame] = []
        cursor = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
        while cursor <= end:
            next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = next_month - timedelta(microseconds=1)
            complete_month = cursor >= datetime(start.year, start.month, 1, tzinfo=timezone.utc) and month_end <= end
            frame = self._binance_month(sym, timeframe, cursor.year, cursor.month) if complete_month else self._empty()
            if frame.empty:
                day = max(start, cursor).replace(hour=0, minute=0, second=0, microsecond=0)
                stop = min(end, month_end)
                while day <= stop:
                    d = self._binance_day(sym, timeframe, day)
                    if not d.empty:
                        frames.append(d)
                    day += timedelta(days=1)
            else:
                frames.append(frame)
            cursor = next_month
        if not frames:
            return self._empty()
        out = pd.concat(frames).sort_index()
        out = out.loc[~out.index.duplicated(keep="last")]
        return out[(out.index >= pd.Timestamp(start)) & (out.index <= pd.Timestamp(end))]

    @staticmethod
    def _bybit_trade_chunk(chunk: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        names = {str(c).lower(): c for c in chunk.columns}
        tcol = names.get("timestamp") or names.get("time")
        pcol = names.get("price")
        qcol = names.get("size") or names.get("qty") or names.get("quantity")
        if tcol is None or pcol is None or qcol is None:
            raise RuntimeError(f"unexpected Bybit archive schema: {list(chunk.columns)[:12]}")
        raw_ts = pd.to_numeric(chunk[tcol], errors="coerce")
        numeric = raw_ts.dropna()
        unit = "ms" if (not numeric.empty and float(numeric.abs().median()) > 1e11) else "s"
        idx = pd.to_datetime(raw_ts, unit=unit, utc=True, errors="coerce")
        price = pd.to_numeric(chunk[pcol], errors="coerce")
        qty = pd.to_numeric(chunk[qcol], errors="coerce")
        trades = pd.DataFrame({"price": price.to_numpy(), "volume": qty.to_numpy()}, index=idx).dropna()
        if trades.empty:
            return OfficialArchiveMarketData._empty()
        rule = timeframe.replace("m", "min").replace("h", "h").replace("d", "D")
        price_ohlc = trades["price"].resample(rule).ohlc()
        volume = trades["volume"].resample(rule).sum(min_count=1)
        out = price_ohlc.join(volume.rename("volume")).dropna()
        return out[["open", "high", "low", "close", "volume"]]

    def _bybit_day(self, symbol: str, timeframe: str, day: datetime) -> pd.DataFrame:
        ds = day.strftime("%Y-%m-%d")
        url = f"{self.BYBIT_BASE}/{symbol}/{symbol}{ds}.csv.gz"
        data = self._get_bytes(url)
        if not data:
            return self._empty()
        pieces: list[pd.DataFrame] = []
        for chunk in pd.read_csv(BytesIO(data), compression="gzip", chunksize=250_000):
            frame = self._bybit_trade_chunk(chunk, timeframe)
            if not frame.empty:
                pieces.append(frame)
        if not pieces:
            return self._empty()
        # Chunk boundaries can split a candle, so aggregate the already-aggregated pieces again.
        merged = pd.concat(pieces).sort_index()
        rule = timeframe.replace("m", "min").replace("h", "h").replace("d", "D")
        out = merged.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        return out

    def fetch_bybit(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        sym = self.compact_symbol(symbol)
        start, end = self._utc(start), self._utc(end)
        frames: list[pd.DataFrame] = []
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= end:
            frame = self._bybit_day(sym, timeframe, day)
            if not frame.empty:
                frames.append(frame)
            day += timedelta(days=1)
        if not frames:
            return self._empty()
        out = pd.concat(frames).sort_index()
        out = out.loc[~out.index.duplicated(keep="last")]
        return out[(out.index >= pd.Timestamp(start)) & (out.index <= pd.Timestamp(end))]

    def fetch_history(self, exchange_id: str, symbol: str, timeframe: str, start: datetime, end: datetime | None) -> pd.DataFrame:
        stop = self._utc(end or datetime.now(timezone.utc))
        if exchange_id.lower() == "binance":
            return self.fetch_binance(symbol, timeframe, start, stop)
        if exchange_id.lower() == "bybit":
            return self.fetch_bybit(symbol, timeframe, start, stop)
        raise ValueError(f"official archive fallback unsupported for {exchange_id}")
