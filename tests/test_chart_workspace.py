import json
import sqlite3
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from universal_bot.backtest import run_backtest
from universal_bot.chart_workspace import V19, apply_strategy, audit_page, export_snapshot
from universal_bot.config import Settings


def candles():
    rng = np.random.default_rng(19)
    close = 100 + np.cumsum(rng.normal(0, .7, 360))
    return pd.DataFrame({"open": np.roll(close, 1), "high": close + 3,
                         "low": close - 3, "close": close, "volume": np.full(360, 100.)},
                        index=pd.date_range("2025-01-01", periods=360, freq="15min", tz="UTC"))


@pytest.mark.parametrize("model", ["signal_close", "next_open"])
def test_observation_preserves_fills_costs_and_dual_touch_priority(model):
    data = candles()
    data["high"] = data[["open", "close"]].max(axis=1) + 3
    data["low"] = data[["open", "close"]].min(axis=1) - 3
    settings = Settings(_env_file=None).model_copy(update={
        **V19, "backtest_execution_model": model, "use_start_date": False,
        "use_rsi_filter": False, "use_nbar_volatility_block": False,
        "volume_break_multiplier": .1, "order_percent_of_equity": 100.0})
    traced = []
    baseline = run_backtest(data, settings)
    observed = run_backtest(data, settings, trace_callback=traced.append)
    assert asdict(observed) == asdict(baseline)
    assert traced and baseline.trades > 0
    dual = [r for r in traced if r["dual_touch"]]
    assert dual and all(r["exit"] in ("SL", "LIQUIDATION") for r in dual)
    assert sum(r.get("exit") is not None for r in traced) == baseline.trades


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "candles.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE ohlcv(asset_class TEXT,exchange TEXT,symbol TEXT,timeframe TEXT,"
                   "timestamp INTEGER,open REAL,high REAL,low REAL,close REAL,volume REAL,"
                   "PRIMARY KEY(asset_class,exchange,symbol,timeframe,timestamp))")
        for ex in ("binance", "bitget", "okx", "bybit"):
            for t, row in candles().iterrows():
                o, c = row.open, row.close
                db.execute("INSERT INTO ohlcv VALUES(?,?,?,?,?,?,?,?,?,?)",
                           ("crypto", ex, "BTC/USDT:USDT", "15m", t.value // 1000000,
                            o, max(o, c)+1, min(o, c)-1, c, row.volume))
    return path


def test_replay_indexes_actual_diagnostics_and_rejects_changed_database(database):
    before = database.read_bytes()
    response = json.loads(apply_strategy(str(database), "BTC/USDT:USDT", "15m", json.dumps(V19)))
    assert database.read_bytes() == before
    result = json.loads(__import__("pathlib").Path(response["result_path"]).read_text())
    first = int(pd.Timestamp("2025-01-03", tz="UTC").value // 1000000)
    page = json.loads(audit_page(response["result_path"], first, first + 3 * 86400000))
    assert page["rows"]
    assert all(row["volume_ratio"] == 1.0 for row in page["rows"])
    assert all(len(row["exchanges"]) == 4 for row in page["rows"])
    assert result["effective_parameters"]["backtest_execution_model"] == "signal_close"
    with sqlite3.connect(database) as db:
        db.execute("UPDATE ohlcv SET volume=volume+1 WHERE exchange='bybit'")
    with pytest.raises(ValueError, match="변경"):
        audit_page(response["result_path"], first, first + 86400000)


def test_missing_exchange_and_cancel_do_not_leave_partial_results(database, tmp_path):
    cancel = tmp_path / "cancel"
    cancel.touch()
    with pytest.raises(ValueError, match="중지"):
        apply_strategy(str(database), "BTC/USDT:USDT", "15m", json.dumps(V19), str(cancel))
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM ohlcv WHERE exchange='okx'")
    with pytest.raises(ValueError, match="missing okx"):
        apply_strategy(str(database), "BTC/USDT:USDT", "15m", json.dumps(V19))
    assert not list(tmp_path.glob("chart-backtest-*"))


def test_export_includes_committed_wal_pages(database, tmp_path):
    source = sqlite3.connect(database)
    try:
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("UPDATE ohlcv SET volume=999 WHERE exchange='bitget'")
        source.commit()
        target = tmp_path / "export.db"
        export_snapshot(str(database), str(target))
        with sqlite3.connect(target) as exported:
            assert exported.execute("SELECT min(volume) FROM ohlcv WHERE exchange='bitget'").fetchone()[0] == 999
    finally:
        source.close()


@pytest.mark.parametrize("update", [
    {"volume_lookback": 0}, {"initial_capital": -1},
    {"backtest_fee_percent": -0.1}, {"order_percent_of_equity": 2000},
    {"rsi_oversold_min": -1}, {"max_tp_percent": float("inf")},
    {"excluded_hours": "24"}, {"min_sl_percent": 10, "max_sl_percent": 1},
])
def test_invalid_editor_values_are_rejected_without_writing_results(database, update):
    before = database.read_bytes()
    with pytest.raises(ValueError):
        apply_strategy(str(database), "BTC/USDT:USDT", "15m", json.dumps({**V19, **update}))
    assert database.read_bytes() == before
    assert not list(database.parent.glob("chart-backtest-*"))
