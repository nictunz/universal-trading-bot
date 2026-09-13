import json
import sqlite3

import pytest

from universal_bot.chart_quality import EXCHANGES, quality_page


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "candles.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE ohlcv(asset_class,exchange,symbol,timeframe,timestamp,open,high,low,close,volume)")
        for ex in EXCHANGES:
            for ts in (0, 900000, 1800000, 2700000):
                db.execute("INSERT INTO ohlcv VALUES(?,?,?,?,?,?,?,?,?,?)", ("crypto", ex, "BTC", "15m", ts, 100, 102, 98, 101, 10))
    return path


def report(path, last=2700000):
    return json.loads(quality_page(str(path), "bitget", "BTC", "15m", 0, last, 900000))


def test_quality_readonly_and_complete(database):
    before = database.read_bytes()
    value = report(database)
    assert value["bars"] == value["four_exchange_complete"] == 4
    assert value["rows"] == []
    assert database.read_bytes() == before


def test_quality_distinguishes_missing_duplicate_zero_and_invalid(database):
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM ohlcv WHERE exchange='okx' AND timestamp=900000")
        db.execute("INSERT INTO ohlcv SELECT * FROM ohlcv WHERE exchange='bybit' AND timestamp=1800000")
        db.execute("UPDATE ohlcv SET volume=0 WHERE exchange='binance' AND timestamp=0")
        db.execute("UPDATE ohlcv SET close=NULL,volume=-1 WHERE exchange='bitget' AND timestamp=2700000")
    value = report(database)
    assert value["four_exchange_complete"] == 1
    assert value["exchanges"]["binance"]["zero_volume"] == 1
    assert value["exchanges"]["okx"]["missing"] == 1
    assert value["exchanges"]["bybit"]["duplicate"] == 1
    assert value["invalid_ohlc"] == value["invalid_volume"] == 1


def test_quality_detects_gap_without_inspecting_replay_future(database):
    prefix = report(database, 900000)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM ohlcv WHERE exchange='bitget' AND timestamp=1800000")
        db.execute("UPDATE ohlcv SET volume=-10 WHERE timestamp=2700000")
    assert report(database, 900000) == prefix
    assert report(database)["missing_bars"] == 1


def test_quality_bounds_expensive_queries(database):
    with pytest.raises(ValueError):
        quality_page(str(database), "bitget", "BTC", "15m", 0, 10**15, 900000)
