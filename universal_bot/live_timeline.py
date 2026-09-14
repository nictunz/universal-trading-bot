"""Merge immutable backtest candles with an independently stored live tail."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

STEP = 900000
MARKET = ("crypto", "bitget", "BTC/USDT:USDT", "15m")


def initialize(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS candles(timestamp INTEGER PRIMARY KEY,open REAL,high REAL,low REAL,close REAL,volume REAL,confirmed INTEGER NOT NULL)")


def ingest(path, payload, server_time):
    import math
    initialize(path)
    rows = []
    for raw in json.loads(payload):
        ts = int(raw[0]); values = [float(x) for x in raw[1:6]]
        if len(values) != 5 or ts % STEP or ts > int(server_time) or not all(math.isfinite(x) for x in values):
            raise ValueError("잘못된 실시간 캔들")
        o, h, l, c, v = values
        if min(o, h, l, c) <= 0 or not l <= min(o, c) <= max(o, c) <= h or v < 0:
            raise ValueError("잘못된 실시간 OHLCV")
        rows.append((ts, *values, int(ts + STEP <= int(server_time))))
    with sqlite3.connect(path) as db:
        db.executemany("INSERT INTO candles VALUES(?,?,?,?,?,?,?) ON CONFLICT(timestamp) DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume=excluded.volume,confirmed=excluded.confirmed WHERE candles.confirmed=0 OR excluded.confirmed=1", rows)
    return len(rows)


def connect(database, tail):
    initialize(tail)
    db = sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro", uri=True)
    db.execute("ATTACH DATABASE ? AS live", (Path(tail).resolve().as_uri()+"?mode=ro",))
    return db


def base_end(db):
    return db.execute("SELECT max(timestamp) FROM ohlcv WHERE asset_class=? AND exchange=? AND symbol=? AND timeframe=?", MARKET).fetchone()[0]


def gap_before(database, tail):
    with closing(connect(database, tail)) as db:
        end = base_end(db)
        if end is None:
            return 0
        previous = end
        for (ts,) in db.execute("SELECT timestamp FROM live.candles WHERE timestamp>? ORDER BY timestamp", (end,)):
            if ts > previous + STEP:
                return int(ts-1)
            previous = ts
        return 0


def page(database, tail, offset, width, follow=False):
    width = max(30, min(600, int(width)))
    with closing(connect(database, tail)) as db:
        end = base_end(db)
        if end is None:
            raise ValueError("선택 DB에 BITGET BTC 15분봉이 없습니다.")
        query = ("SELECT timestamp,open,high,low,close,volume FROM ohlcv WHERE asset_class=? AND exchange=? AND symbol=? AND timeframe=? AND timestamp<=? "
                 "UNION ALL SELECT timestamp,open,high,low,close,volume FROM live.candles WHERE timestamp>?")
        params = (*MARKET, end, end)
        count = db.execute("SELECT count(*) FROM ("+query+")", params).fetchone()[0]
        offset = max(0, count-width) if follow else max(0, min(int(offset), max(0,count-width)))
        rows = db.execute("SELECT * FROM ("+query+") ORDER BY timestamp LIMIT ? OFFSET ?", (*params,width,offset)).fetchall()
        # The live copy wins at the boundary, but never changes the original DB.
        rows = [db.execute("SELECT timestamp,open,high,low,close,volume FROM live.candles WHERE timestamp=?", (r[0],)).fetchone() or r if r[0]==end else r for r in rows]
        gaps = sum(max(0,(b[0]-a[0])//STEP-1) for a,b in zip(rows,rows[1:]))
    return json.dumps({"rows":rows,"total":count,"offset":offset,"base_end":end,"missing":gaps}, allow_nan=False)


def offset_for_timestamp(database, tail, timestamp):
    with closing(connect(database, tail)) as db:
        end = base_end(db)
        if end is None:
            return 0
        base = db.execute("SELECT count(*) FROM ohlcv WHERE asset_class=? AND exchange=? AND symbol=? AND timeframe=? AND timestamp<?", (*MARKET, timestamp)).fetchone()[0]
        extra = db.execute("SELECT count(*) FROM live.candles WHERE timestamp>? AND timestamp<?", (end, timestamp)).fetchone()[0]
        return base + extra
