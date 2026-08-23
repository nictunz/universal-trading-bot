from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd


@dataclass(frozen=True)
class DataRequest:
    symbol: str
    timeframe: str = "5m"
    start: datetime | None = None
    end: datetime | None = None
    asset_class: str = "crypto"
    exchange: str = "bitget"


class HistoricalDataManager:
    def __init__(self, database_url: str = "sqlite:///data/universal_bot.db") -> None:
        path = database_url.removeprefix("sqlite:///")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
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

    def _bounds(self, request: DataRequest) -> tuple[int | None, int | None]:
        start = self._ms(request.start)
        end = self._ms(request.end)
        with self._connect() as con:
            row = con.execute("SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv WHERE asset_class=? AND exchange=? AND symbol=? AND timeframe=?", (request.asset_class, request.exchange, request.symbol, request.timeframe)).fetchone()
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

    def _fetch_crypto(self, request: DataRequest) -> pd.DataFrame:
        import ccxt
        exchange_cls = getattr(ccxt, request.exchange)
        exchange = exchange_cls({"enableRateLimit": True})
        start = self._ms(request.start)
        end = self._ms(request.end) or int(datetime.now(timezone.utc).timestamp() * 1000)
        if start is None:
            raise ValueError("crypto historical requests require a start date")
        rows: list[list[float]] = []
        since = start
        limit = 1000
        while since <= end:
            batch = exchange.fetch_ohlcv(request.symbol, request.timeframe, since=since, limit=limit)
            if not batch:
                break
            rows.extend(batch)
            last = batch[-1][0]
            if last <= since:
                break
            since = last + 1
            if last >= end:
                break
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df.timestamp, unit="ms", utc=True)
        df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
        return df[(df.index >= pd.Timestamp(start, unit="ms", tz="UTC")) & (df.index <= pd.Timestamp(end, unit="ms", tz="UTC"))]

    def _fetch_yfinance(self, request: DataRequest) -> pd.DataFrame:
        import yfinance as yf
        ticker = request.symbol.replace("/", "-").split(":")[0]
        kwargs = {"auto_adjust": False, "progress": False}
        if request.start:
            kwargs["start"] = request.start
        if request.end:
            kwargs["end"] = request.end
        else:
            kwargs["end"] = datetime.now(timezone.utc)
        df = yf.download(ticker, interval=request.timeframe, **kwargs)
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    def fetch_and_store(self, request: DataRequest) -> int:
        if request.asset_class == "crypto":
            df = self._fetch_crypto(request)
        elif request.asset_class in {"stock", "etf"}:
            df = self._fetch_yfinance(request)
        else:
            raise ValueError(f"Unsupported asset class: {request.asset_class}")
        return self._save(request, df)

    def read(self, request: DataRequest) -> pd.DataFrame:
        start = self._ms(request.start)
        end = self._ms(request.end)
        clauses = ["asset_class=?", "exchange=?", "symbol=?", "timeframe=?"]
        params: list[object] = [request.asset_class, request.exchange, request.symbol, request.timeframe]
        if start is not None:
            clauses.append("timestamp>=?"); params.append(start)
        if end is not None:
            clauses.append("timestamp<=?"); params.append(end)
        query = "SELECT timestamp, open, high, low, close, volume FROM ohlcv WHERE " + " AND ".join(clauses) + " ORDER BY timestamp"
        with self._connect() as con:
            df = pd.read_sql_query(query, con, params=params)
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df.timestamp, unit="ms", utc=True)
        return df.set_index("timestamp")

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
        return inserted, self.read(request)
