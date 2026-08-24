from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time

import pandas as pd
import requests

from universal_bot.providers.bitget_history import BitgetHistoricalMarketData


class _DisabledCoinApi:
    enabled = False

    def fetch_history(self, *args, **kwargs):
        raise RuntimeError("CoinAPI disabled on Android")


@dataclass(frozen=True)
class DataRequest:
    symbol: str
    timeframe: str = "5m"
    start: datetime | None = None
    end: datetime | None = None
    asset_class: str = "crypto"
    exchange: str = "bitget"


class HistoricalDataManager:
    """Android-only history manager.

    Keeps the same SQLite/read/sync contract as the server implementation while
    avoiding ccxt and its compiled Android dependency chain. Bitget uses the
    existing native REST provider, OKX uses the public REST history endpoint,
    and Binance/Bybit intentionally raise here so OfficialArchiveHistoricalDataManager
    can fall back to exchange-owned archives.
    """

    def __init__(self, database_url: str = "sqlite:///data/universal_bot.db", *, coinapi_api_key: str = "", fallback_exchanges: list[str] | None = None) -> None:
        path = database_url.removeprefix("sqlite:///")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._coinapi = _DisabledCoinApi()
        self._bitget_history = BitgetHistoricalMarketData()
        self._fallback_exchanges = {x.lower() for x in (fallback_exchanges or [])}
        self.last_fetch_status: dict[str, dict[str, str]] = {}
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS ohlcv (asset_class TEXT NOT NULL, exchange TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, timestamp INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL, PRIMARY KEY(asset_class, exchange, symbol, timeframe, timestamp))")
            con.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_lookup ON ohlcv(asset_class, exchange, symbol, timeframe, timestamp)")

    @staticmethod
    def _ms(dt: datetime | None) -> int | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _timeframe_ms(timeframe: str) -> int | None:
        try:
            value, unit = int(timeframe[:-1]), timeframe[-1]
        except (TypeError, ValueError, IndexError):
            return None
        seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}.get(unit)
        return value * seconds * 1000 if seconds else None

    def _bounds(self, request: DataRequest) -> tuple[int | None, int | None]:
        with self._connect() as con:
            row = con.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv WHERE asset_class=? AND exchange=? AND symbol=? AND timeframe=?",
                (request.asset_class, request.exchange, request.symbol, request.timeframe),
            ).fetchone()
        return row[0], row[1]

    def _save(self, request: DataRequest, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        rows = []
        for ts, row in df.iterrows():
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            rows.append((request.asset_class, request.exchange, request.symbol, request.timeframe, int(ts.timestamp() * 1000), float(row.open), float(row.high), float(row.low), float(row.close), float(row.volume)))
        with self._connect() as con:
            con.executemany("INSERT OR REPLACE INTO ohlcv (asset_class, exchange, symbol, timeframe, timestamp, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        return len(rows)

    @staticmethod
    def _okx_inst_id(symbol: str) -> str:
        pair = symbol.split(":", 1)[0].upper().replace("/", "-")
        return f"{pair}-SWAP"

    @staticmethod
    def _okx_bar(timeframe: str) -> str:
        if timeframe.endswith("m"):
            return timeframe
        if timeframe.endswith("h"):
            return f"{int(timeframe[:-1])}H"
        if timeframe.endswith("d"):
            return f"{int(timeframe[:-1])}Dutc"
        raise ValueError(f"unsupported OKX timeframe on Android: {timeframe}")

    def _fetch_okx(self, request: DataRequest) -> pd.DataFrame:
        start_ms = self._ms(request.start)
        end_ms = self._ms(request.end) or int(datetime.now(timezone.utc).timestamp() * 1000)
        if start_ms is None:
            raise ValueError("OKX history requires a start date")
        url = "https://www.okx.com/api/v5/market/history-candles"
        rows: dict[int, list[str]] = {}
        cursor = end_ms + 1
        calls = 0
        while cursor > start_ms:
            params = {
                "instId": self._okx_inst_id(request.symbol),
                "bar": self._okx_bar(request.timeframe),
                "after": str(cursor),
                "limit": "300",
            }
            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200:
                raise RuntimeError(f"OKX history HTTP {r.status_code}: {r.text[:180]}")
            payload = r.json()
            if payload.get("code") != "0":
                raise RuntimeError(f"OKX history API error: {str(payload)[:220]}")
            batch = payload.get("data") or []
            if not batch:
                break
            stamps = []
            for item in batch:
                if len(item) < 6:
                    continue
                ts = int(item[0])
                stamps.append(ts)
                if start_ms <= ts <= end_ms:
                    rows[ts] = item
            if not stamps:
                break
            oldest = min(stamps)
            if oldest <= start_ms:
                break
            if oldest >= cursor:
                break
            cursor = oldest
            calls += 1
            if calls % 10 == 0:
                time.sleep(0.10)
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        data = [[ts, item[1], item[2], item[3], item[4], item[5]] for ts, item in sorted(rows.items())]
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna().drop_duplicates("timestamp").set_index("timestamp").sort_index()

    def _fetch_crypto_direct(self, request: DataRequest) -> pd.DataFrame:
        exchange = request.exchange.lower()
        if request.start is None:
            raise ValueError("crypto historical requests require a start date")
        end = request.end or datetime.now(timezone.utc)
        if exchange == "bitget":
            return self._bitget_history.fetch_history(request.symbol, request.timeframe, request.start, end)
        if exchange == "okx":
            return self._fetch_okx(request)
        if exchange in {"binance", "bybit"}:
            raise RuntimeError(f"{exchange} direct disabled on Android; use official archive")
        raise ValueError(f"unsupported crypto exchange on Android: {exchange}")

    def _fetch_crypto(self, request: DataRequest) -> pd.DataFrame:
        df = self._fetch_crypto_direct(request)
        mode = "DIRECT_NATIVE" if request.exchange.lower() == "bitget" else "DIRECT"
        self.last_fetch_status[request.exchange] = {"mode": mode, "status": "OK"}
        return df

    def fetch_and_store(self, request: DataRequest) -> int:
        if request.asset_class != "crypto":
            raise ValueError("Android local backtester currently supports crypto only")
        return self._save(request, self._fetch_crypto(request))

    def read(self, request: DataRequest) -> pd.DataFrame:
        start = self._ms(request.start)
        end = self._ms(request.end)
        clauses = ["asset_class=?", "exchange=?", "symbol=?", "timeframe=?"]
        params: list[object] = [request.asset_class, request.exchange, request.symbol, request.timeframe]
        if start is not None:
            clauses.append("timestamp>=?")
            params.append(start)
        if end is not None:
            clauses.append("timestamp<=?")
            params.append(end)
        query = "SELECT timestamp, open, high, low, close, volume FROM ohlcv WHERE " + " AND ".join(clauses) + " ORDER BY timestamp"
        with self._connect() as con:
            df = pd.read_sql_query(query, con, params=params)
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df.timestamp, unit="ms", utc=True)
        return df.set_index("timestamp")

    def _repair_crypto_gaps(self, request: DataRequest, df: pd.DataFrame, max_gaps: int = 250) -> int:
        interval_ms = self._timeframe_ms(request.timeframe)
        if interval_ms is None or len(df) < 2:
            return 0
        stamps = (df.index.view("int64") // 1_000_000).astype("int64")
        missing_ranges: list[tuple[int, int]] = []
        for left, right in zip(stamps[:-1], stamps[1:]):
            if right - left > int(interval_ms * 1.5):
                gap_start = int(left + interval_ms)
                gap_end = int(right - interval_ms)
                if gap_start <= gap_end:
                    missing_ranges.append((gap_start, gap_end))
                    if len(missing_ranges) >= max_gaps:
                        break
        inserted = 0
        for start_ms, end_ms in missing_ranges:
            sub = DataRequest(request.symbol, request.timeframe, datetime.fromtimestamp(start_ms / 1000, timezone.utc), datetime.fromtimestamp(end_ms / 1000, timezone.utc), request.asset_class, request.exchange)
            inserted += self.fetch_and_store(sub)
        return inserted

    def sync(self, request: DataRequest) -> tuple[int, pd.DataFrame]:
        requested_start = self._ms(request.start)
        requested_end = self._ms(request.end) or int(datetime.now(timezone.utc).timestamp() * 1000)
        min_ts, max_ts = self._bounds(request)
        inserted = 0
        if min_ts is None or (requested_start is not None and min_ts > requested_start):
            left_end = (min_ts - 1) if min_ts is not None else requested_end
            left = DataRequest(request.symbol, request.timeframe, request.start, datetime.fromtimestamp(left_end / 1000, timezone.utc), request.asset_class, request.exchange)
            inserted += self.fetch_and_store(left)
        if max_ts is None or max_ts < requested_end:
            right_start_ms = (max_ts + 1) if max_ts is not None else requested_start
            if right_start_ms is None:
                raise ValueError("historical request requires a start date")
            right = DataRequest(request.symbol, request.timeframe, datetime.fromtimestamp(right_start_ms / 1000, timezone.utc), request.end, request.asset_class, request.exchange)
            inserted += self.fetch_and_store(right)
        df = self.read(request)
        for _ in range(3):
            repaired = self._repair_crypto_gaps(request, df)
            inserted += repaired
            if repaired == 0:
                break
            df = self.read(request)
        return inserted, df
