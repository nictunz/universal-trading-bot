from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from universal_bot.config import Settings
from universal_bot.trade_history import TradeHistoryStore


def _ms(value: str | None, *, end: bool = False) -> int | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 10:
        text += "T23:59:59.999999+00:00" if end else "T00:00:00+00:00"
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def _slug(symbol: str) -> str:
    base = symbol.split(":", 1)[0].split("/", 1)[0].lower()
    return "".join(ch for ch in base if ch.isalnum()) or "market"


class DashboardDataService:
    def __init__(self, history: TradeHistoryStore | None = None) -> None:
        self.settings = Settings()
        self.history = history or TradeHistoryStore()

    def _candidate_databases(self, symbol: str, timeframe: str) -> list[Path]:
        cache = Path.home() / ".cache" / "universal-trading-bot"
        paths = [cache / f"{_slug(symbol)}-1y-{timeframe}.db"]
        default = Path(self.settings.database_url.removeprefix("sqlite:///"))
        if default not in paths:
            paths.append(default)
        return [p for p in paths if p.exists()]

    @staticmethod
    def _read_db(path: Path, *, symbol: str, exchange: str, timeframe: str, asset_class: str, start_ms: int | None, end_ms: int | None) -> pd.DataFrame:
        clauses = ["asset_class=?", "exchange=?", "symbol=?", "timeframe=?"]
        params: list[Any] = [asset_class, exchange, symbol, timeframe]
        if start_ms is not None:
            clauses.append("timestamp>=?"); params.append(start_ms)
        if end_ms is not None:
            clauses.append("timestamp<=?"); params.append(end_ms)
        query = "SELECT timestamp,open,high,low,close,volume FROM ohlcv WHERE " + " AND ".join(clauses) + " ORDER BY timestamp"
        try:
            with sqlite3.connect(path, timeout=5) as con:
                return pd.read_sql_query(query, con, params=params)
        except (sqlite3.Error, pd.errors.DatabaseError):
            return pd.DataFrame()

    def candles(
        self, *, symbol: str, exchange: str = "bitget", timeframe: str = "5m", asset_class: str = "crypto",
        start: str | None = None, end: str | None = None, max_points: int = 1800,
    ) -> dict[str, Any]:
        start_ms = _ms(start)
        end_ms = _ms(end, end=True)
        frames: list[pd.DataFrame] = []
        sources: list[str] = []
        for path in self._candidate_databases(symbol, timeframe):
            frame = self._read_db(path, symbol=symbol, exchange=exchange.lower(), timeframe=timeframe, asset_class=asset_class, start_ms=start_ms, end_ms=end_ms)
            if not frame.empty:
                frames.append(frame)
                sources.append(str(path))
        if not frames:
            return {"symbol": symbol, "exchange": exchange, "timeframe": timeframe, "candles": [], "source": None, "sampled": False}
        df = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
        sampled = False
        max_points = max(100, min(int(max_points), 5000))
        if len(df) > max_points:
            # Preserve the full requested time span while keeping the mobile dashboard responsive.
            step = max(1, len(df) // max_points)
            df = df.iloc[::step].copy()
            sampled = True
        candles = [
            {
                "timestamp": pd.Timestamp(int(r.timestamp), unit="ms", tz="UTC").isoformat(),
                "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close), "volume": float(r.volume),
            }
            for r in df.itertuples(index=False)
        ]
        return {
            "symbol": symbol, "exchange": exchange, "timeframe": timeframe, "candles": candles,
            "source": sources[0] if len(sources) == 1 else sources, "sampled": sampled, "points": len(candles),
        }

    def history_payload(self, *, symbol: str, mode: str = "ALL", start: str | None = None, end: str | None = None, limit: int = 2000) -> dict[str, Any]:
        start_iso = None if not start else datetime.fromtimestamp((_ms(start) or 0) / 1000, timezone.utc).isoformat()
        end_iso = None if not end else datetime.fromtimestamp((_ms(end, end=True) or 0) / 1000, timezone.utc).isoformat()
        trades = self.history.list_trades(symbol=symbol, mode=mode, start=start_iso, end=end_iso, limit=limit)
        summary = self.history.summary(symbol=symbol, mode=mode, start=start_iso, end=end_iso)
        return {"symbol": symbol, "mode": mode.upper(), "summary": summary, "trades": trades, "runs": self.history.list_backtest_runs(symbol=symbol, limit=25)}
