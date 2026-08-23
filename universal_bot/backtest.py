from __future__ import annotations
from dataclasses import dataclass
import math
import pandas as pd
from universal_bot.config import Settings
from universal_bot.engine import TradingEngine
from universal_bot.strategy.v15 import UniversalV15Strategy
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


def run_backtest(
    df: pd.DataFrame,
    settings: Settings,
    normalized_volume_ratio: pd.Series | None = None,
) -> BacktestResult:
    """Deterministic bar-by-bar simulation with indicators vectorized once.

    Historical crypto signals can consume the same four-exchange normalized
    volume ratio as live v15. Reported PnL is net of configurable taker fees
    and slippage; gross PnL is preserved separately for auditability.
    """
    class BacktestAdapter:
        asset_class = settings.asset_class
        def equity(self) -> float:
            return settings.initial_capital
        def market_order(self, *args, **kwargs):
            return {"mode": "BACKTEST", "args": args}
        def fetch_volume_sources(self, *args, **kwargs):
            return {}

    total = len(df)
    if total == 0:
        return BacktestResult(0, 0, 0.0, None, 0.0, 0.0, 0.0, 0.0, 0.0, [], [])

    prepared = df.sort_index().loc[~df.index.duplicated(keep="last")].copy()
    close = prepared["close"].astype(float)
    high = prepared["high"].astype(float)
    low = prepared["low"].astype(float)
    volume = prepared["volume"].astype(float)

    if normalized_volume_ratio is not None:
        prepared["_v15_volume_ratio"] = normalized_volume_ratio.reindex(prepared.index)
    else:
        vol_avg = sma(volume, settings.volume_lookback)
        prepared["_v15_volume_ratio"] = volume / vol_avg.replace(0, math.nan)
    prepared["_v15_n_range"] = rolling_range_percent(high, low, settings.volatility_bars)
    prepared["_v15_block_range"] = rolling_range_percent(high, low, settings.nbar_volatility_bars)
    _, _, adx_series = dmi_adx(high, low, close, settings.adx_length)
    prepared["_v15_adx"] = adx_series
    prepared["_v15_rsi"] = rsi(close, settings.rsi_length)

    strategy = UniversalV15Strategy(settings)
    engine = TradingEngine(settings, BacktestAdapter(), strategy)
    warmup = max(settings.volume_lookback, settings.volatility_bars, settings.nbar_volatility_bars, settings.adx_length * 3, settings.rsi_length + 10, 200)
    start_bar = min(warmup, total - 1)
    history_bars = max(warmup + 50, 300)

    for end in range(start_bar + 1, total + 1):
        start = max(0, end - history_bars)
        window = prepared.iloc[start:end]
        row = prepared.iloc[end - 1]
        cached = {
            "volume_ratio": float(row["_v15_volume_ratio"]) if pd.notna(row["_v15_volume_ratio"]) else math.nan,
            "n_range": float(row["_v15_n_range"]) if pd.notna(row["_v15_n_range"]) else math.nan,
            "block_range": float(row["_v15_block_range"]) if pd.notna(row["_v15_block_range"]) else math.nan,
            "adx": float(row["_v15_adx"]) if pd.notna(row["_v15_adx"]) else math.nan,
            "rsi": float(row["_v15_rsi"]) if pd.notna(row["_v15_rsi"]) else math.nan,
        }
        engine.step(window, precomputed=cached)
        if total >= 5000 and (end == start_bar + 1 or end % 5000 == 0 or end == total):
            print(f"[BACKTEST] {end:,}/{total:,} ({end / total * 100.0:.1f}%) trades={engine.closed_trades}", flush=True)

    adjusted_log, estimated_costs, net_pnl, net_wins, net_pf = _apply_execution_costs(engine.trade_log, settings)
    gross_pnl = float(engine.realized_pnl)

    cost_by_bar: dict[int, float] = {}
    for t in adjusted_log:
        cost_by_bar[int(t.get("bar") or 0)] = cost_by_bar.get(int(t.get("bar") or 0), 0.0) + float(t.get("estimated_cost") or 0.0)
    running_cost = 0.0
    adjusted_curve = []
    peak = float(settings.initial_capital)
    max_dd = 0.0
    for point in engine.equity_curve:
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
        return_percent=net_pnl / settings.initial_capital * 100 if settings.initial_capital else 0.0,
        max_drawdown_percent=max_dd,
        trades_log=adjusted_log,
        equity_curve=adjusted_curve,
    )
