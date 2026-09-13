"""Copy matching cached candles into a request DB without changing source DBs."""
import sqlite3
from contextlib import closing
from pathlib import Path


def seed_cache(root, target, symbol, timeframe, first, last, log, check=None):
    target = Path(target).resolve()
    copied = 0
    candidates = sorted(Path(root).rglob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    with closing(sqlite3.connect(target)) as dst:
        for source in candidates:
            if source.resolve() == target or any("trash" in part.lower() for part in source.parts):
                continue
            if check:
                check()
            try:
                with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
                    cursor = src.execute("SELECT asset_class,exchange,symbol,timeframe,timestamp,open,high,low,close,volume FROM ohlcv WHERE asset_class='crypto' AND symbol=? AND timeframe=? AND timestamp BETWEEN ? AND ? AND exchange IN ('binance','bitget','okx','bybit')", (symbol, timeframe, first, last))
                    while True:
                        if check:
                            check()
                        rows = cursor.fetchmany(2000)
                        if not rows:
                            break
                        before = dst.total_changes
                        with dst:
                            dst.executemany("INSERT OR IGNORE INTO ohlcv(asset_class,exchange,symbol,timeframe,timestamp,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
                        copied += dst.total_changes - before
            except sqlite3.Error as exc:
                log(f"기존 DB 재사용 건너뜀: {source.name} · {exc}")
    log(f"기존 DB에서 {copied}개 캔들 재사용 · 부족한 구간만 확인/다운로드")
    return copied
