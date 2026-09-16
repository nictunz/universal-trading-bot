#!/usr/bin/env python3
"""Read-only 5y Priority 5m+15m parity verifier.

This verifier never imports a LIVE adapter, never contacts an exchange, and never
writes to the source OHLCV database. It uses the offline PaperPriorityRuntime.
The source database must contain the canonical `ohlcv` table for BTC/USDT:USDT
5m data from binance/bitget/okx/bybit. 15m bars are aggregated from complete 5m
triples so both timeframes share exactly the same source history.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from universal_bot.priority_paper_runtime import PaperPriorityRuntime
from universal_bot.priority_signals import EXCHANGES, profile_hash

EXPECTED = {
    "initial_equity": 1000.0,
    "return_percent": 1291264.04,
    "final_equity": 12913640.39,
    "max_drawdown_percent": 55.37,
    "trades": 250,
    "five_minute_trades": 102,
    "fifteen_minute_trades": 148,
    "preemptions": 10,
}
SYMBOL = "BTC/USDT:USDT"
START = pd.Timestamp("2021-09-16T00:00:00Z")
END = pd.Timestamp("2026-09-14T23:55:00Z")


def read_5m(path: Path):
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(ohlcv)")}
        need = {"exchange", "symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"}
        if not need <= cols:
            raise RuntimeError("database does not contain canonical ohlcv schema")
        q = """SELECT exchange,timestamp,open,high,low,close,volume FROM ohlcv
               WHERE symbol=? AND timeframe='5m' AND timestamp BETWEEN ? AND ?
               ORDER BY exchange,timestamp"""
        rows = pd.read_sql_query(q, con, params=[SYMBOL, int(START.timestamp()*1000), int(END.timestamp()*1000)])
    if rows.empty:
        raise RuntimeError("no canonical BTC 5m rows in requested 5y window")
    rows.exchange = rows.exchange.str.lower()
    found = set(rows.exchange.unique())
    if found != set(EXCHANGES):
        raise RuntimeError(f"exact four exchanges required; found={sorted(found)}")
    out = {}
    for ex in sorted(EXCHANGES):
        x = rows[rows.exchange == ex].drop(columns="exchange").copy()
        x["timestamp"] = pd.to_datetime(x.timestamp, unit="ms", utc=True)
        x = x.drop_duplicates("timestamp").set_index("timestamp").sort_index()
        expected = pd.date_range(START, END, freq="5min")
        if len(x) != len(expected) or not x.index.equals(expected):
            missing = expected.difference(x.index)
            raise RuntimeError(f"{ex}: incomplete 5m grid rows={len(x)} expected={len(expected)} missing={len(missing)}")
        out[ex] = x
    return out


def aggregate_15m(frame):
    # Timestamp is candle-open time. origin epoch preserves UTC :00/:15/:30/:45 boundaries.
    agg = frame.resample("15min", origin="epoch", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"))
    counts = frame["close"].resample("15min", origin="epoch", label="left", closed="left").count()
    return agg[counts == 3].dropna()


def run(path: Path):
    source = read_5m(path)
    chart5 = source["bitget"]
    chart15 = aggregate_15m(chart5)
    vols5 = {ex: f.volume for ex, f in source.items()}
    vols15 = {ex: aggregate_15m(f).volume for ex, f in source.items()}

    warmup = 200
    boundaries = pd.date_range(START + pd.Timedelta(minutes=5*warmup), END + pd.Timedelta(minutes=5), freq="5min")
    with tempfile.TemporaryDirectory(prefix="priority-parity-") as td:
        runtime = PaperPriorityRuntime(Path(td) / "paper.sqlite", initial_equity=EXPECTED["initial_equity"])
        equity_curve = [EXPECTED["initial_equity"]]
        try:
            for i, b in enumerate(boundaries, 1):
                end5 = b - pd.Timedelta(minutes=5)
                frames = {"5m": chart5.loc[:end5].tail(500)}
                volumes = {"5m": {ex: s.loc[:end5].tail(500) for ex, s in vols5.items()}}
                if b.minute % 15 == 0:
                    end15 = b - pd.Timedelta(minutes=15)
                    frames["15m"] = chart15.loc[:end15].tail(500)
                    volumes["15m"] = {ex: s.loc[:end15].tail(500) for ex, s in vols15.items()}
                status = runtime.step(frames, volumes, b, b + pd.Timedelta(seconds=1))
                if status == "HALTED":
                    raise RuntimeError("paper runtime HALTED: " + str(runtime.snapshot().get("halted")))
                equity_curve.append(float(runtime.snapshot()["equity"]))
                if i % 25000 == 0:
                    print(json.dumps({"progress": i, "boundaries": len(boundaries), "equity": equity_curve[-1]}), flush=True)
            snap = runtime.snapshot()
        finally:
            runtime.close()

    events = snap["events"]
    opens = [e for e in events if e["kind"] == "PAPER_OPEN"]
    closes = [e for e in events if e["kind"] == "PAPER_CLOSE"]
    owners = [e["owner"] for e in opens]
    final = float(snap["equity"])
    peak = equity_curve[0]
    mdd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            mdd = max(mdd, (peak-value)/peak*100.0)
    result = {
        "profile_hash": profile_hash(), "source_db": str(path), "source_window": [START.isoformat(), END.isoformat()],
        "return_percent": (final/EXPECTED["initial_equity"]-1)*100.0, "final_equity": final,
        "max_drawdown_percent": mdd, "trades": len(closes),
        "five_minute_trades": owners.count("5m"), "fifteen_minute_trades": owners.count("15m"),
        "preemptions": sum(e.get("reason") == "PREEMPTED_BY_5M" for e in closes),
        "open_position_at_end": snap["position"] is not None,
    }
    tolerances = {"return_percent": 0.02, "final_equity": 0.02, "max_drawdown_percent": 0.02}
    mismatches = {}
    for key, expected in EXPECTED.items():
        if key == "initial_equity":
            continue
        actual = result[key]
        tol = tolerances.get(key, 0)
        if abs(actual-expected) > tol:
            mismatches[key] = {"expected": expected, "actual": actual, "tolerance": tol}
    result["expected"] = EXPECTED
    result["mismatches"] = mismatches
    result["parity"] = not mismatches
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["parity"] else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, type=Path)
    args = ap.parse_args()
    if not args.db.is_file():
        raise SystemExit("DB not found: " + str(args.db))
    raise SystemExit(run(args.db))

if __name__ == "__main__":
    main()
