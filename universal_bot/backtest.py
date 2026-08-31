from __future__ import annotations
from dataclasses import dataclass
from datetime import timezone
import math
from typing import Callable
import numpy as np
import pandas as pd
from universal_bot.config import Settings
from universal_bot.indicators import dmi_adx, rolling_range_percent, rsi, sma


@dataclass
class BacktestResult:
    trades: int
    wins: int
    win_rate: float
    profit_factor: float | None
    pnl: float
    gross_pnl: float
    estimated_costs: float
    return_percent: float
    max_drawdown_percent: float
    liquidations: int
    trades_log: list[dict]
    equity_curve: list[dict]


def _apply_execution_costs(trades: list[dict], settings: Settings) -> tuple[list[dict], float, float, int, float | None]:
    fee = max(0.0, float(settings.backtest_fee_percent)) / 100.0
    slip = max(0.0, float(settings.backtest_slippage_percent)) / 100.0
    adjusted: list[dict] = []
    total_cost = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    for raw in trades:
        t = dict(raw)
        qty = abs(float(t.get("qty") or 0.0))
        entry = abs(float(t.get("avg_entry_price") or t.get("entry_price") or 0.0))
        exit_ = abs(float(t.get("exit_price") or 0.0))
        round_trip_notional = qty * (entry + exit_)
        cost = round_trip_notional * (fee + slip)
        gross = float(t.get("pnl") or 0.0)
        net = gross - cost
        total_cost += cost
        if net >= 0:
            wins += 1
            gross_profit += net
        else:
            gross_loss += abs(net)
        t["gross_pnl"] = gross
        t["estimated_cost"] = cost
        t["pnl"] = net
        t["pnl_percent"] = net / (entry * qty) * 100 if entry and qty else 0.0
        adjusted.append(t)
    pf = gross_profit / gross_loss if gross_loss else None
    return adjusted, total_cost, sum(float(t["pnl"]) for t in adjusted), wins, pf


def crossed_liquidation_hit(
    *,
    side: str,
    qty: float,
    avg_entry: float,
    worst_mark: float,
    account_equity_before_open_pnl: float,
    initial_capital: float,
    maintenance_rate: float,
    reserve_percent: float,
) -> bool:
    """Conservative crossed-margin liquidation check at an intrabar worst mark."""
    open_pnl = (
        (worst_mark - avg_entry) * qty
        if side == "LONG"
        else (avg_entry - worst_mark) * qty
    )
    account_equity = account_equity_before_open_pnl + open_pnl
    maintenance = abs(worst_mark * qty) * max(0.0, maintenance_rate)
    reserve = initial_capital * max(0.0, reserve_percent) / 100.0
    return account_equity <= max(reserve, maintenance)


def backtest_sizing_equity(
    initial_capital: float,
    realized_net_pnl: float,
    compounding_enabled: bool,
) -> float:
    """Capital base used for the next entry; fixed mode preserves legacy results."""
    if not compounding_enabled:
        return max(0.0, float(initial_capital))
    return max(0.0, float(initial_capital) + float(realized_net_pnl))


def _consecutive_candle_direction_ok(
    opens: np.ndarray,
    closes: np.ndarray,
    index: int,
    candles: int,
    side: str,
) -> bool:
    count = max(1, int(candles))
    start = index - count + 1
    if start < 0:
        return False
    recent_open = opens[start:index + 1]
    recent_close = closes[start:index + 1]
    if side == "LONG":
        return bool(np.all(recent_close < recent_open))
    if side == "SHORT":
        return bool(np.all(recent_close > recent_open))
    return False


def run_backtest(
    df: pd.DataFrame,
    settings: Settings,
    normalized_volume_ratio: pd.Series | None = None,
    control_check: Callable[[], None] | None = None,
) -> BacktestResult:
    """Fast deterministic v15 bar simulation."""
    if len(df) == 0:
        return BacktestResult(0, 0, 0.0, None, 0.0, 0.0, 0.0, 0.0, 0.0, 0, [], [])

    prepared = df.sort_index().loc[~df.index.duplicated(keep="last")].copy()
    total = len(prepared)
    close_s = prepared["close"].astype(float)
    high_s = prepared["high"].astype(float)
    low_s = prepared["low"].astype(float)
    volume_s = prepared["volume"].astype(float)

    if normalized_volume_ratio is not None:
        volume_ratio_s = normalized_volume_ratio.reindex(prepared.index)
    else:
        vol_avg = sma(volume_s, settings.volume_lookback)
        volume_ratio_s = volume_s / vol_avg.replace(0, math.nan)
    n_range_s = rolling_range_percent(high_s, low_s, settings.volatility_bars)
    block_range_s = rolling_range_percent(high_s, low_s, settings.nbar_volatility_bars)
    _, _, adx_s = dmi_adx(high_s, low_s, close_s, settings.adx_length)
    rsi_s = rsi(close_s, settings.rsi_length)

    opens = prepared["open"].to_numpy(dtype=float, copy=False)
    highs = high_s.to_numpy(dtype=float, copy=False)
    lows = low_s.to_numpy(dtype=float, copy=False)
    closes = close_s.to_numpy(dtype=float, copy=False)
    volume_ratio = volume_ratio_s.to_numpy(dtype=float, copy=False)
    n_range = n_range_s.to_numpy(dtype=float, copy=False)
    block_range = block_range_s.to_numpy(dtype=float, copy=False)
    adx = adx_s.to_numpy(dtype=float, copy=False)
    rsi_values = rsi_s.to_numpy(dtype=float, copy=False)
    index = prepared.index

    warmup = max(settings.volume_lookback, settings.volatility_bars, settings.nbar_volatility_bars, settings.adx_length * 3, settings.rsi_length + 10, 200)
    start_idx = min(warmup, total - 1)
    excluded_hours = {x.strip() for x in settings.excluded_hours.split(",") if x.strip()}
    start_date = settings.start_date
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    else:
        start_date = start_date.astimezone(timezone.utc)

    initial_capital = float(settings.initial_capital)
    compounding_enabled = bool(settings.backtest_compounding_enabled)
    maintenance_rate = max(0.0, float(settings.backtest_maintenance_margin_percent)) / 100.0
    execution_cost_rate = (
        max(0.0, float(settings.backtest_fee_percent))
        + max(0.0, float(settings.backtest_slippage_percent))
    ) / 100.0

    position_side: str | None = None
    position_size = 0.0
    initial_entry = 0.0
    entry_notional = 0.0
    position_tp = math.nan
    position_sl = math.nan
    position_entry_time: str | None = None
    entries = 0
    last_entry_bar: int | None = None
    last_exit_bar: int | None = None
    bar_number = 0
    realized_pnl = 0.0
    realized_costs = 0.0
    position_sizing_equity = initial_capital
    liquidations = 0
    account_liquidated = False
    trade_log: list[dict] = []
    equity_curve: list[dict] = []

    for i in range(start_idx, total):
        # Mobile stop/pause must be observed inside a long multi-year trial,
        # not only between trials. Checking every 256 bars keeps overhead tiny.
        if control_check is not None and (i - start_idx) % 256 == 0:
            control_check()
        bar_number += 1
        bars_since_entry = None if last_entry_bar is None else bar_number - last_entry_bar
        bars_since_exit = None if last_exit_bar is None else bar_number - last_exit_bar
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        vr = volume_ratio[i]
        nr = n_range[i]
        br = block_range[i]
        av = adx[i]
        rv = rsi_values[i]

        one_bar_vol = abs(c - o) / o * 100.0 if o else 0.0
        raw_tp = nr * float(settings.tp_vol_multiplier) if np.isfinite(nr) else math.nan
        raw_sl = nr * float(settings.sl_vol_multiplier) if np.isfinite(nr) else math.nan
        final_tp = max(settings.min_tp_percent, min(settings.max_tp_percent, raw_tp)) if np.isfinite(raw_tp) else math.nan
        final_sl = max(settings.min_sl_percent, min(settings.max_sl_percent, raw_sl)) if np.isfinite(raw_sl) else math.nan

        ts = index[i]
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        current_time = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        else:
            current_time = current_time.astimezone(timezone.utc)
        time_ok = ((not settings.use_start_date) or current_time >= start_date)
        time_ok = time_ok and ((not settings.block_weekend) or current_time.weekday() < 5)
        time_ok = time_ok and (current_time.strftime("%H") not in excluded_hours)
        cooldown_ok = (bars_since_entry is None or bars_since_entry >= settings.cooldown_bars) and (bars_since_exit is None or bars_since_exit >= settings.reentry_bars)
        nbar_ok = (not settings.use_nbar_volatility_block) or (np.isfinite(br) and br <= settings.max_nbar_volatility)
        adx_ok = (not settings.use_adx_filter) or (np.isfinite(av) and settings.adx_min <= av <= settings.adx_max)
        base_entry = (
            np.isfinite(vr) and vr >= settings.volume_break_multiplier
            and settings.min_one_bar_vol <= one_bar_vol <= settings.max_one_bar_vol
            and nbar_ok and adx_ok and time_ok and cooldown_ok
        )
        oversold = np.isfinite(rv) and settings.rsi_oversold_min <= rv <= settings.rsi_oversold_max
        overbought = np.isfinite(rv) and settings.rsi_overbought_min <= rv <= settings.rsi_overbought_max
        long_ok = (not settings.use_rsi_filter) or oversold
        short_ok = (not settings.use_rsi_filter) or overbought
        signal: str | None = None
        first_entry_bars = max(1, int(settings.first_entry_consecutive_candles))
        apply_three_tick_to_all = bool(getattr(settings, "apply_consecutive_candles_to_all_entries", False))
        require_consecutive = position_side is None or apply_three_tick_to_all
        long_candle_ok = (
            _consecutive_candle_direction_ok(opens, closes, i, first_entry_bars, "LONG")
            if require_consecutive else c < o
        )
        short_candle_ok = (
            _consecutive_candle_direction_ok(opens, closes, i, first_entry_bars, "SHORT")
            if require_consecutive else c > o
        )
        if base_entry and settings.allow_long and long_candle_ok and long_ok:
            signal = "LONG"
        elif base_entry and settings.allow_short and short_candle_ok and short_ok:
            signal = "SHORT"

        if position_side is not None:
            qty = abs(position_size)
            avg_entry = entry_notional / qty if qty and entry_notional else initial_entry
            worst_mark = l if position_side == "LONG" else h
            # Crossed margin: the whole account supports the position. A 25% equity
            # reserve makes a fully-used 15x position liquidate near a 5% adverse move.
            hit_liquidation = (
                str(settings.backtest_margin_mode).lower() == "crossed"
                and crossed_liquidation_hit(
                    side=position_side,
                    qty=qty,
                    avg_entry=avg_entry,
                    worst_mark=worst_mark,
                    account_equity_before_open_pnl=initial_capital + realized_pnl - realized_costs,
                    initial_capital=initial_capital,
                    maintenance_rate=maintenance_rate,
                    reserve_percent=float(settings.backtest_cross_liquidation_buffer_percent),
                )
            )
            hit_tp = (
                (position_side == "LONG" and h >= position_tp)
                or (position_side == "SHORT" and l <= position_tp)
            )
            hit_sl = (
                (position_side == "LONG" and l <= position_sl)
                or (position_side == "SHORT" and h >= position_sl)
            )
            if hit_liquidation or hit_tp or hit_sl:
                # Intrabar order is deliberately conservative: liquidation first,
                # then SL, then TP when more than one level is touched in one candle.
                if hit_liquidation:
                    reason = "LIQUIDATION"
                    exit_price = worst_mark
                    pnl = -(initial_capital + realized_pnl)
                    liquidations += 1
                    account_liquidated = True
                elif hit_sl:
                    reason = "SL"
                    exit_price = position_sl
                    pnl = (
                        (exit_price - avg_entry) * qty
                        if position_side == "LONG"
                        else (avg_entry - exit_price) * qty
                    )
                else:
                    reason = "TP"
                    exit_price = position_tp
                    pnl = (
                        (exit_price - avg_entry) * qty
                        if position_side == "LONG"
                        else (avg_entry - exit_price) * qty
                    )
                realized_pnl += pnl
                realized_costs += qty * (abs(avg_entry) + abs(exit_price)) * execution_cost_rate
                trade_log.append({
                    "trade": len(trade_log) + 1,
                    "side": position_side,
                    "entry_time": position_entry_time,
                    "exit_time": ts_iso,
                    "entry_price": initial_entry,
                    "avg_entry_price": avg_entry,
                    "exit_price": exit_price,
                    "qty": qty,
                    "pnl": pnl,
                    "pnl_percent": pnl / abs(avg_entry * qty) * 100 if avg_entry and qty else 0.0,
                    "reason": reason,
                    "bar": bar_number,
                    "entries": entries,
                    "total_exposure_multiplier": entry_notional / position_sizing_equity if position_sizing_equity else 0.0,
                    "sizing_equity": position_sizing_equity,
                    "compounding_enabled": compounding_enabled,
                    "cross_margin": str(settings.backtest_margin_mode).lower() == "crossed",
                })
                position_side = None
                position_size = 0.0
                initial_entry = 0.0
                entry_notional = 0.0
                position_tp = math.nan
                position_sl = math.nan
                position_entry_time = None
                entries = 0
                position_sizing_equity = initial_capital
                last_exit_bar = bar_number

        if account_liquidated:
            equity_curve.append({
                "bar": bar_number,
                "timestamp": ts_iso,
                "equity": 0.0,
                "liquidated": True,
            })
            break

        sizing_equity = backtest_sizing_equity(
            initial_capital,
            realized_pnl - realized_costs,
            compounding_enabled,
        )
        order_notional = sizing_equity * float(settings.order_percent_of_equity) / 100.0
        max_total_notional = sizing_equity * float(settings.backtest_max_total_multiplier)
        can_pyramid = (
            sizing_equity > 0.0
            and entries < settings.max_pyramiding
            and entry_notional + order_notional <= max_total_notional + 1e-9
        )
        same_direction = position_side is None or position_side == signal
        if signal and can_pyramid and same_direction and last_entry_bar != bar_number and np.isfinite(final_tp) and np.isfinite(final_sl):
            amount = order_notional / c if c > 0 else 0.0
            if amount > 0:
                signed = amount if signal == "LONG" else -amount
                if position_side is None:
                    position_side = signal
                    position_sizing_equity = sizing_equity
                    position_size = signed
                    initial_entry = c
                    entry_notional = amount * c
                    position_tp = c * (1 + final_tp / 100.0) if signal == "LONG" else c * (1 - final_tp / 100.0)
                    position_sl = c * (1 - final_sl / 100.0) if signal == "LONG" else c * (1 + final_sl / 100.0)
                    position_entry_time = ts_iso
                    entries = 1
                else:
                    entries += 1
                    position_size += signed
                    entry_notional += amount * c
                last_entry_bar = bar_number

        open_pnl = 0.0
        if position_side is not None:
            qty = abs(position_size)
            avg_entry = entry_notional / qty if qty and entry_notional else initial_entry
            open_pnl = (c - avg_entry) * qty if position_side == "LONG" else (avg_entry - c) * qty
        equity_curve.append({"bar": bar_number, "timestamp": ts_iso, "equity": initial_capital + realized_pnl + open_pnl})

    adjusted_log, estimated_costs, net_pnl, net_wins, net_pf = _apply_execution_costs(trade_log, settings)
    gross_pnl = float(realized_pnl)

    cost_by_bar: dict[int, float] = {}
    for t in adjusted_log:
        b = int(t.get("bar") or 0)
        cost_by_bar[b] = cost_by_bar.get(b, 0.0) + float(t.get("estimated_cost") or 0.0)
    running_cost = 0.0
    adjusted_curve = []
    peak = initial_capital
    max_dd = 0.0
    for point in equity_curve:
        running_cost += cost_by_bar.get(int(point.get("bar") or 0), 0.0)
        equity = float(point["equity"]) - running_cost
        adjusted_point = dict(point)
        adjusted_point["equity"] = equity
        adjusted_curve.append(adjusted_point)
        peak = max(peak, equity)
        if peak:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)

    trades = len(adjusted_log)
    return BacktestResult(
        trades=trades,
        wins=net_wins,
        win_rate=net_wins / trades * 100 if trades else 0.0,
        profit_factor=net_pf,
        pnl=net_pnl,
        gross_pnl=gross_pnl,
        estimated_costs=estimated_costs,
        return_percent=net_pnl / initial_capital * 100 if initial_capital else 0.0,
        max_drawdown_percent=max_dd,
        liquidations=liquidations,
        trades_log=adjusted_log,
        equity_curve=adjusted_curve,
    )
