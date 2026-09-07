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


def _iso_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return pd.Timestamp(int(value), unit="ms", tz="UTC").isoformat()


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
            clauses.append("timestamp>=?")
            params.append(start_ms)
        if end_ms is not None:
            clauses.append("timestamp<=?")
            params.append(end_ms)
        query = "SELECT timestamp,open,high,low,close,volume FROM ohlcv WHERE " + " AND ".join(clauses) + " ORDER BY timestamp"
        try:
            with sqlite3.connect(path, timeout=5) as con:
                return pd.read_sql_query(query, con, params=params)
        except (sqlite3.Error, pd.errors.DatabaseError):
            return pd.DataFrame()

    @staticmethod
    def _read_page_db(
        path: Path,
        *,
        symbol: str,
        exchange: str,
        timeframe: str,
        asset_class: str,
        start_ms: int | None,
        before_ms: int | None,
        limit: int,
    ) -> pd.DataFrame:
        clauses = ["asset_class=?", "exchange=?", "symbol=?", "timeframe=?"]
        params: list[Any] = [asset_class, exchange, symbol, timeframe]
        if start_ms is not None:
            clauses.append("timestamp>=?")
            params.append(start_ms)
        if before_ms is not None:
            clauses.append("timestamp<=?")
            params.append(before_ms)
        query = (
            "SELECT timestamp,open,high,low,close,volume FROM ohlcv WHERE "
            + " AND ".join(clauses)
            + " ORDER BY timestamp DESC LIMIT ?"
        )
        params.append(limit)
        try:
            with sqlite3.connect(path, timeout=5) as con:
                return pd.read_sql_query(query, con, params=params)
        except (sqlite3.Error, pd.errors.DatabaseError):
            return pd.DataFrame()

    def candles(
        self,
        *,
        symbol: str,
        exchange: str = "bitget",
        timeframe: str = "5m",
        asset_class: str = "crypto",
        start: str | None = None,
        end: str | None = None,
        max_points: int = 1800,
    ) -> dict[str, Any]:
        """Legacy whole-range chart endpoint.

        Kept for compatibility. The dashboard uses ``candles_page`` so it never
        has to read or ship an entire one-year series for the first paint.
        """
        start_ms = _ms(start)
        end_ms = _ms(end, end=True)
        frames: list[pd.DataFrame] = []
        sources: list[str] = []
        for path in self._candidate_databases(symbol, timeframe):
            frame = self._read_db(
                path,
                symbol=symbol,
                exchange=exchange.lower(),
                timeframe=timeframe,
                asset_class=asset_class,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            if not frame.empty:
                frames.append(frame)
                sources.append(str(path))
        if not frames:
            return {
                "symbol": symbol,
                "exchange": exchange,
                "timeframe": timeframe,
                "candles": [],
                "source": None,
                "sampled": False,
                "points": 0,
                "raw_points": 0,
            }
        df = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
        raw_points = len(df)
        sampled = False
        max_points = max(100, min(int(max_points), 5000))
        if len(df) > max_points:
            # ceil keeps the rendered result at or below max_points.
            step = max(1, (len(df) + max_points - 1) // max_points)
            df = df.iloc[::step].copy()
            sampled = True
        candles = [
            {
                "timestamp": _iso_ms(int(r.timestamp)),
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            }
            for r in df.itertuples(index=False)
        ]
        return {
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
            "candles": candles,
            "source": sources[0] if len(sources) == 1 else sources,
            "sampled": sampled,
            "points": len(candles),
            "raw_points": raw_points,
        }

    def candles_page(
        self,
        *,
        symbol: str,
        exchange: str = "bitget",
        timeframe: str = "5m",
        asset_class: str = "crypto",
        start: str | None = None,
        before: str | None = None,
        page_size: int = 600,
    ) -> dict[str, Any]:
        """Return one exact, unsampled page of candles, newest data first.

        The response is sorted oldest->newest for drawing, but selection is
        performed DESC with LIMIT so initial dashboard paint reads only the
        latest page. ``next_before`` is an exclusive cursor for the next older
        page. This mirrors TradingView-style progressive history loading.
        """
        start_ms = _ms(start)
        before_ms = _ms(before, end=True) if before else None
        page_size = max(100, min(int(page_size), 2000))
        frames: list[pd.DataFrame] = []
        sources: list[str] = []

        # Ask each candidate for one extra row. After deduplication that row is
        # enough to determine whether older history is available.
        for path in self._candidate_databases(symbol, timeframe):
            frame = self._read_page_db(
                path,
                symbol=symbol,
                exchange=exchange.lower(),
                timeframe=timeframe,
                asset_class=asset_class,
                start_ms=start_ms,
                before_ms=before_ms,
                limit=page_size + 1,
            )
            if not frame.empty:
                frames.append(frame)
                sources.append(str(path))

        if not frames:
            return {
                "symbol": symbol,
                "exchange": exchange,
                "timeframe": timeframe,
                "candles": [],
                "source": None,
                "points": 0,
                "sampled": False,
                "has_more": False,
                "next_before": None,
                "oldest": None,
                "newest": None,
            }

        merged = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates("timestamp", keep="last")
            .sort_values("timestamp", ascending=False)
        )
        has_more = len(merged) > page_size
        page = merged.iloc[:page_size].sort_values("timestamp").copy()
        oldest_ms = int(page.iloc[0]["timestamp"])
        newest_ms = int(page.iloc[-1]["timestamp"])
        next_before_ms = oldest_ms - 1 if has_more else None

        candles = [
            {
                "timestamp": _iso_ms(int(r.timestamp)),
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            }
            for r in page.itertuples(index=False)
        ]
        return {
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
            "candles": candles,
            "source": sources[0] if len(sources) == 1 else sources,
            "points": len(candles),
            "sampled": False,
            "has_more": has_more,
            "next_before": _iso_ms(next_before_ms),
            "oldest": _iso_ms(oldest_ms),
            "newest": _iso_ms(newest_ms),
        }

    def history_payload(
        self,
        *,
        symbol: str,
        mode: str = "ALL",
        run_id: str | None = None,
        timeframe: str | None = None,
        exchange: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 2000,
    ) -> dict[str, Any]:
        normalized_mode = mode.upper()
        runs = self.history.list_backtest_runs(
            symbol=symbol, timeframe=timeframe, exchange=exchange, limit=25,
        )
        selected_run_id = run_id
        if normalized_mode == "BACKTEST" and not selected_run_id and runs:
            selected_run_id = str(runs[0]["run_id"])

        # A selected backtest run is an immutable result. Date inputs control
        # the candle viewport, but must not truncate its trades or metrics.
        run_filter = selected_run_id if normalized_mode == "BACKTEST" else None
        if run_filter:
            start_iso = None
            end_iso = None
        else:
            start_iso = None if not start else datetime.fromtimestamp((_ms(start) or 0) / 1000, timezone.utc).isoformat()
            end_iso = None if not end else datetime.fromtimestamp((_ms(end, end=True) or 0) / 1000, timezone.utc).isoformat()

        trades = self.history.list_trades(
            symbol=symbol, mode=normalized_mode, run_id=run_filter,
            start=start_iso, end=end_iso, limit=limit,
        )
        summary = self.history.summary(
            symbol=symbol, mode=normalized_mode, run_id=run_filter,
            start=start_iso, end=end_iso,
        )
        selected_run = next((item for item in runs if item["run_id"] == selected_run_id), None)
        return {
            "symbol": symbol,
            "mode": normalized_mode,
            "selected_run_id": selected_run_id,
            "selected_run": selected_run,
            "summary": summary,
            "trades": trades,
            "runs": runs,
        }
