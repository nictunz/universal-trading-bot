from __future__ import annotations

import sqlite3
from pathlib import Path

from universal_bot.dashboard_data import DashboardDataService
from universal_bot.trade_history import TradeHistoryStore


def test_trade_history_persists_and_filters(tmp_path):
    store = TradeHistoryStore(tmp_path / "trades.db")
    trade = {
        "trade": 1,
        "side": "LONG",
        "entry_time": "2026-08-01T00:00:00+00:00",
        "exit_time": "2026-08-01T01:00:00+00:00",
        "entry_price": 100.0,
        "avg_entry_price": 100.0,
        "exit_price": 102.0,
        "qty": 1.0,
        "gross_pnl": 2.0,
        "estimated_cost": 0.1,
        "pnl": 1.9,
        "pnl_percent": 1.9,
        "reason": "TP",
    }
    store.record_trade(run_id="x", trade_no=1, mode="PAPER", symbol="ETH/USDT:USDT", asset_class="crypto", exchange="bitget", timeframe="5m", trade=trade)
    rows = store.list_trades(symbol="ETH/USDT:USDT", mode="PAPER")
    assert len(rows) == 1
    assert rows[0]["reason"] == "TP"
    assert store.summary(symbol="ETH/USDT:USDT", mode="PAPER")["pnl"] == 1.9


def test_dashboard_candle_service_reads_cached_sqlite(tmp_path, monkeypatch):
    db = tmp_path / "eth-1y-5m.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE ohlcv (asset_class TEXT, exchange TEXT, symbol TEXT, timeframe TEXT, timestamp INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL)")
        con.executemany(
            "INSERT INTO ohlcv VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("crypto", "bitget", "ETH/USDT:USDT", "5m", 1722470400000, 100, 102, 99, 101, 10),
                ("crypto", "bitget", "ETH/USDT:USDT", "5m", 1722470700000, 101, 103, 100, 102, 11),
            ],
        )
    service = DashboardDataService(TradeHistoryStore(tmp_path / "trades.db"))
    monkeypatch.setattr(service, "_candidate_databases", lambda symbol, timeframe: [db])
    out = service.candles(symbol="ETH/USDT:USDT", exchange="bitget", timeframe="5m", asset_class="crypto")
    assert out["points"] == 2
    assert out["candles"][0]["open"] == 100.0
    assert out["candles"][1]["close"] == 102.0
