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
    return_percent: float
    max_drawdown_percent: float
    trades_log: list[dict]
    equity_curve: list[dict]


def run_backtest(
    df: pd.DataFrame,
    settings: Settings,
    normalized_volume_ratio: pd.Series | None = None,
) -> BacktestResult:
    """Deterministic bar-by-bar simulation with indicator series vectorized once.

    ``normalized_volume_ratio`` is supplied by the historical service when the
    four-exchange crypto-volume mode is enabled.  This keeps historical signals
    consistent with live v15 instead of silently falling back to chart volume.
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
        return BacktestResult(0, 0, 0.0, None, 0.0, 0.0, 0.0, [], [])

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

    pf = engine.gross_profit / engine.gross_loss if engine.gross_loss else None
    peak = float(settings.initial_capital)
    max_dd = 0.0
    for point in engine.equity_curve:
        equity = float(point["equity"])
        peak = max(peak, equity)
        if peak:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return BacktestResult(
        trades=engine.closed_trades,
        wins=engine.winning_trades,
        win_rate=engine.winning_trades / engine.closed_trades * 100 if engine.closed_trades else 0.0,
        profit_factor=pf,
        pnl=engine.realized_pnl,
        return_percent=engine.realized_pnl / settings.initial_capital * 100 if settings.initial_capital else 0.0,
        max_drawdown_percent=max_dd,
        trades_log=engine.trade_log,
        equity_curve=engine.equity_curve,
    )
