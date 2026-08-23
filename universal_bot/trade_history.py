from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TradeHistoryStore:
    """Small SQLite journal shared by PAPER, LIVE and backtest dashboard history."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or (Path.home() / ".cache" / "universal-trading-bot" / "trade-history.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                trade_no INTEGER,
                mode TEXT NOT NULL,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                entry_time TEXT,
                exit_time TEXT,
                side TEXT NOT NULL,
                entry_price REAL,
                avg_entry_price REAL,
                exit_price REAL,
                qty REAL,
                gross_pnl REAL,
                cost REAL,
                pnl REAL,
                pnl_percent REAL,
                reason TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
                )"""
            )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_identity ON trades(mode, run_id, symbol, exchange, timeframe, trade_no)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_trade_query ON trades(symbol, mode, exit_time)"
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                trades INTEGER NOT NULL,
                wins INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                profit_factor REAL,
                pnl REAL NOT NULL,
                return_percent REAL NOT NULL,
                max_drawdown_percent REAL NOT NULL,
                params_json TEXT,
                created_at TEXT NOT NULL
                )"""
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_trade(
        self,
        *,
        run_id: str,
        trade_no: int,
        mode: str,
        symbol: str,
        asset_class: str,
        exchange: str,
        timeframe: str,
        trade: dict[str, Any],
        strategy: str = "Volume Strategy FINAL Universal v15",
    ) -> None:
        with self._connect() as con:
            con.execute(
                """INSERT OR REPLACE INTO trades
                (run_id, trade_no, mode, strategy, symbol, asset_class, exchange, timeframe,
                 entry_time, exit_time, side, entry_price, avg_entry_price, exit_price, qty,
                 gross_pnl, cost, pnl, pnl_percent, reason, metadata_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, int(trade_no), mode.upper(), strategy, symbol, asset_class, exchange, timeframe,
                    trade.get("entry_time"), trade.get("exit_time"), str(trade.get("side") or ""),
                    trade.get("entry_price"), trade.get("avg_entry_price"), trade.get("exit_price"), trade.get("qty"),
                    trade.get("gross_pnl", trade.get("pnl")), trade.get("estimated_cost", trade.get("cost", 0.0)),
                    trade.get("pnl"), trade.get("pnl_percent"), trade.get("reason"),
                    json.dumps(trade.get("metadata") or {}, ensure_ascii=False, default=str), self._now(),
                ),
            )

    def record_backtest(self, result: dict[str, Any], *, run_id: str, params: dict[str, Any] | None = None) -> None:
        with self._connect() as con:
            con.execute(
                """INSERT OR REPLACE INTO backtest_runs
                (run_id,strategy,symbol,asset_class,exchange,timeframe,start_time,end_time,trades,wins,
                 win_rate,profit_factor,pnl,return_percent,max_drawdown_percent,params_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, result.get("strategy", "Volume Strategy FINAL Universal v15"), result.get("symbol", ""),
                    result.get("asset_class", "crypto"), result.get("exchange", ""), result.get("timeframe", ""),
                    result.get("requested_start") or result.get("data_start"), result.get("requested_end") or result.get("data_end"),
                    int(result.get("trades") or 0), int(result.get("wins") or 0), float(result.get("win_rate") or 0.0),
                    result.get("profit_factor"), float(result.get("pnl") or 0.0), float(result.get("return_percent") or 0.0),
                    float(result.get("max_drawdown_percent") or 0.0), json.dumps(params or {}, ensure_ascii=False, default=str), self._now(),
                ),
            )
        for i, trade in enumerate(result.get("trades_log") or [], start=1):
            self.record_trade(
                run_id=run_id, trade_no=int(trade.get("trade") or i), mode="BACKTEST",
                symbol=result.get("symbol", ""), asset_class=result.get("asset_class", "crypto"),
                exchange=result.get("exchange", ""), timeframe=result.get("timeframe", ""), trade=trade,
                strategy=result.get("strategy", "Volume Strategy FINAL Universal v15"),
            )

    def list_trades(
        self, *, symbol: str | None = None, mode: str | None = None,
        start: str | None = None, end: str | None = None, limit: int = 2000,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol=?"); params.append(symbol)
        if mode and mode.upper() != "ALL":
            clauses.append("mode=?"); params.append(mode.upper())
        if start:
            clauses.append("COALESCE(exit_time,entry_time,created_at)>=?"); params.append(start)
        if end:
            clauses.append("COALESCE(exit_time,entry_time,created_at)<=?"); params.append(end)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 10000)))
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM trades" + where + " ORDER BY COALESCE(exit_time,entry_time,created_at) DESC LIMIT ?", params
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, **filters: Any) -> dict[str, Any]:
        rows = self.list_trades(limit=10000, **filters)
        if not rows:
            return {"trades": 0, "wins": 0, "win_rate": 0.0, "pnl": 0.0, "profit_factor": None}
        pnl = [float(r.get("pnl") or 0.0) for r in rows]
        wins = sum(v >= 0 for v in pnl)
        gp = sum(v for v in pnl if v >= 0)
        gl = abs(sum(v for v in pnl if v < 0))
        return {
            "trades": len(rows), "wins": wins, "win_rate": wins / len(rows) * 100.0,
            "pnl": sum(pnl), "profit_factor": gp / gl if gl else None,
        }

    def list_backtest_runs(self, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if symbol:
            where = " WHERE symbol=?"; params.append(symbol)
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as con:
            rows = con.execute("SELECT * FROM backtest_runs" + where + " ORDER BY created_at DESC LIMIT ?", params).fetchall()
        return [dict(row) for row in rows]
