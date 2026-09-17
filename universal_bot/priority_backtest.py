"""Historical simulator for the LIVE 5m/15m Priority Runtime.

The simulator intentionally reuses DualTimeframeSignals, including the exact
LIVE profile constants and 5m-first candidate ordering. One virtual position is
shared by both timeframes: 5m owns priority and may preempt a 15m position.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pandas as pd

from universal_bot.priority_signals import DualTimeframeSignals, DataUnavailable, PROFILES, profile_hash

EXCHANGES = ("binance", "bitget", "okx", "bybit")
FEE = 0.0002
SLIPPAGE = 0.0001
MAX_TOTAL_MULTIPLIER = 15.0


def _utc_day(value: str, end: bool = False) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    if len(str(value).strip()) == 10 and end:
        ts += pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return ts


def _load(con: sqlite3.Connection, symbol: str, timeframe: str, exchange: str,
          start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows = con.execute(
        "SELECT timestamp,open,high,low,close,volume FROM ohlcv "
        "WHERE asset_class='crypto' AND exchange=? AND symbol=? AND timeframe=? "
        "AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
        (exchange, symbol, timeframe, int(start.timestamp()*1000), int(end.timestamp()*1000)),
    ).fetchall()
    if not rows:
        raise ValueError(f"{exchange} {timeframe}: 선택 DB에 데이터가 없습니다")
    frame = pd.DataFrame(rows, columns=("timestamp","open","high","low","close","volume"))
    frame.index = pd.to_datetime(frame.pop("timestamp"), unit="ms", utc=True)
    return frame.astype(float)


def run_priority_backtest(database_path: str, start: str, end: str,
                          initial_capital: float = 1000.0,
                          compounding: bool = True,
                          symbol: str = "BTC/USDT:USDT") -> dict:
    """Replay both LIVE profiles on one position/equity timeline.

    Signal admission is identical to LIVE: at each 5m boundary both due frames
    must be complete, DualTimeframeSignals evaluates 5m before 15m, a 5m owner
    blocks all new entries, and a 5m signal preempts a 15m owner. TP/SL are fixed
    from entry and same-bar TP+SL resolves to SL first.
    """
    if symbol != "BTC/USDT:USDT":
        raise ValueError("LIVE 통합 프로필은 BTC/USDT:USDT 전용입니다")
    db = Path(database_path)
    if not db.is_file():
        raise ValueError("실거래 동등 통합 백테스트는 먼저 저장 DB를 선택해야 합니다")
    capital = float(initial_capital)
    if not math.isfinite(capital) or capital < 10:
        raise ValueError("초기자산은 10 USDT 이상이어야 합니다")
    start_ts, end_ts = _utc_day(start), _utc_day(end, True)
    # LIVE evaluator needs 200 completed warmup bars; load extra history.
    warmup = start_ts - pd.Timedelta(days=4)
    frames, volumes = {}, {}
    with sqlite3.connect(str(db)) as con:
        for tf in ("5m", "15m"):
            frames[tf] = _load(con, symbol, tf, "bitget", warmup, end_ts)
            volumes[tf] = {
                ex: _load(con, symbol, tf, ex, warmup, end_ts)["volume"] for ex in EXCHANGES
            }

    signals = DualTimeframeSignals()
    history: dict[str, dict[str, str]] = {}
    equity = capital
    peak = capital
    max_dd = 0.0
    position = None
    trades = []
    curve = []
    skipped_data = 0

    def close_position(raw_price: float, when: pd.Timestamp, reason: str):
        nonlocal position, equity, peak, max_dd
        p = position
        if p is None:
            return
        adverse = (1.0 - SLIPPAGE) if p["side"] == "LONG" else (1.0 + SLIPPAGE)
        exit_price = float(raw_price) * adverse
        direction = 1.0 if p["side"] == "LONG" else -1.0
        gross = p["notional"] * direction * (exit_price / p["entry_fill"] - 1.0)
        exit_fee = p["notional"] * FEE
        pnl = gross - p["entry_fee"] - exit_fee
        equity += pnl
        row = dict(trade=len(trades)+1, owner=p["owner"], side=p["side"],
                   entry_time=p["entry_time"].isoformat(), exit_time=when.isoformat(),
                   entry_price=p["entry_fill"], exit_price=exit_price, tp=p["tp"], sl=p["sl"],
                   multiplier=p["multiplier"], reason=reason, pnl=pnl,
                   return_on_entry_equity_percent=(pnl/p["equity_before"]*100.0 if p["equity_before"] else 0.0))
        trades.append(row)
        history.setdefault(p["owner"], {})["exit"] = when.isoformat()
        position = None
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak-equity)/peak*100.0)

    boundaries = pd.date_range(start=start_ts.ceil("5min"), end=end_ts.floor("5min"), freq="5min", tz="UTC")
    for boundary in boundaries:
        # The 5m candle whose open is boundary-5m is now complete. Protection
        # touch is processed before a new boundary signal, matching one-position
        # ownership and conservative same-bar SL-first behavior.
        if position is not None:
            bar_open = boundary - pd.Timedelta("5m")
            if bar_open in frames["5m"].index:
                bar = frames["5m"].loc[bar_open]
                if position["side"] == "LONG":
                    sl_hit, tp_hit = bar.low <= position["sl"], bar.high >= position["tp"]
                else:
                    sl_hit, tp_hit = bar.high >= position["sl"], bar.low <= position["tp"]
                if sl_hit:
                    close_position(position["sl"], boundary, "SL")
                elif tp_hit:
                    close_position(position["tp"], boundary, "TP")

        due = signals.due(boundary)
        batch_frames = {tf: frames[tf] for tf in due}
        batch_volumes = {tf: volumes[tf] for tf in due}
        try:
            candidates, _ = signals.evaluate(batch_frames, batch_volumes, boundary, boundary, history)
        except DataUnavailable:
            skipped_data += 1
            curve.append({"time": boundary.isoformat(), "equity": equity})
            continue
        if candidates:
            signal = candidates[0]  # exact LIVE 5m-first ordering
            owner = position["owner"] if position else None
            if owner != "5m" and not (owner and signal.owner == "15m"):
                if owner == "15m" and signal.owner == "5m":
                    close_position(signal.price, boundary, "PREEMPTED_BY_5M")
                if position is None:
                    multiplier = min(float(signal.multiplier), MAX_TOTAL_MULTIPLIER)
                    base_equity = equity if compounding else capital
                    notional = max(0.0, base_equity * multiplier)
                    if notional > 0 and equity > 0:
                        entry_fill = signal.price * ((1.0+SLIPPAGE) if signal.side == "LONG" else (1.0-SLIPPAGE))
                        tp = entry_fill * (1.0 + signal.tp_percent/100.0) if signal.side == "LONG" else entry_fill * (1.0-signal.tp_percent/100.0)
                        sl = entry_fill * (1.0 - signal.sl_percent/100.0) if signal.side == "LONG" else entry_fill * (1.0+signal.sl_percent/100.0)
                        position = dict(owner=signal.owner, side=signal.side, entry_time=boundary,
                                        entry_fill=entry_fill, tp=tp, sl=sl, multiplier=multiplier,
                                        notional=notional, entry_fee=notional*FEE, equity_before=equity)
                        history.setdefault(signal.owner, {})["entry"] = boundary.isoformat()
        curve.append({"time": boundary.isoformat(), "equity": equity})

    if position is not None:
        last = frames["5m"].loc[frames["5m"].index <= end_ts]
        if not last.empty:
            close_position(float(last.close.iloc[-1]), last.index[-1] + pd.Timedelta("5m"), "END_OF_TEST")

    wins = sum(float(t["pnl"]) > 0 for t in trades)
    gross_profit = sum(max(0.0, float(t["pnl"])) for t in trades)
    gross_loss = -sum(min(0.0, float(t["pnl"])) for t in trades)
    return dict(
        strategy="Volume Strategy FINAL Universal v15 · LIVE Priority 5m+15m",
        mode="priority_live_parity", profile_hash=profile_hash(), symbol=symbol,
        profiles={tf: {"multiplier": PROFILES[tf]["live_entry_multiplier"]} for tf in ("5m","15m")},
        priority_rule="5m first; 5m preempts 15m; one shared position",
        execution_model="signal_close", same_bar_policy="SL_FIRST",
        fee_percent_per_side=FEE*100, slippage_percent_per_side=SLIPPAGE*100,
        initial_capital=capital, final_equity=equity, compounding_enabled=bool(compounding),
        trades=len(trades), wins=wins, win_rate=(wins/len(trades)*100 if trades else 0.0),
        profit_factor=(gross_profit/gross_loss if gross_loss else (float("inf") if gross_profit else 0.0)),
        pnl=equity-capital, return_percent=((equity/capital)-1.0)*100.0,
        max_drawdown_percent=max_dd, skipped_data_boundaries=skipped_data,
        trades_log=trades, equity_curve=curve,
    )
