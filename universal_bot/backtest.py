from __future__ import annotations
from dataclasses import dataclass
import math
import pandas as pd
from universal_bot.config import Settings
from universal_bot.engine import TradingEngine
from universal_bot.strategy.v15 import UniversalV15Strategy
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
def run_backtest(df: pd.DataFrame, settings: Settings) -> BacktestResult:
    """
    Deterministic bar-by-bar v15 simulation.
    Speed optimized:
    all deterministic v15 indicators are calculated ONCE for the
    complete historical DataFrame instead of recalculating ADX/RSI/
    rolling ranges for every single bar.
    """
    from universal_bot.indicators import (
        dmi_adx,
        rolling_range_percent,
        rsi,
        sma,
    )
    class BacktestAdapter:
        asset_class = settings.asset_class
        def equity(self) -> float:
            return settings.initial_capital
        def market_order(self, *args, **kwargs):
            return {
                "mode": "BACKTEST",
                "args": args,
            }
        def fetch_volume_sources(self, *args, **kwargs):
            return {}
    total = len(df)
    if total == 0:
        return BacktestResult(
            trades=0,
            wins=0,
            win_rate=0.0,
            profit_factor=None,
            pnl=0.0,
            return_percent=0.0,
            max_drawdown_percent=0.0,
            trades_log=[],
            equity_curve=[],
        )
    # --------------------------------------------------------
    # Prepare OHLCV once
    # --------------------------------------------------------
    prepared = df.sort_index().copy()
    close = prepared["close"].astype(float)
    open_ = prepared["open"].astype(float)
    high = prepared["high"].astype(float)
    low = prepared["low"].astype(float)
    volume = prepared["volume"].astype(float)
    # --------------------------------------------------------
    # Volume ratio
    # --------------------------------------------------------
    vol_avg = sma(
        volume,
        settings.volume_lookback,
    )
    prepared["_v15_volume_ratio"] = (
        volume
        / vol_avg.replace(0, math.nan)
    )
    # --------------------------------------------------------
    # N-bar range
    # --------------------------------------------------------
    prepared["_v15_n_range"] = rolling_range_percent(
        high,
        low,
        settings.volatility_bars,
    )
    # --------------------------------------------------------
    # N-bar extreme-volatility block
    # --------------------------------------------------------
    prepared["_v15_block_range"] = rolling_range_percent(
        high,
        low,
        settings.nbar_volatility_bars,
    )
    # --------------------------------------------------------
    # ADX
    # --------------------------------------------------------
    _, _, adx_series = dmi_adx(
        high,
        low,
        close,
        settings.adx_length,
    )
    prepared["_v15_adx"] = adx_series
    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------
    prepared["_v15_rsi"] = rsi(
        close,
        settings.rsi_length,
    )
    # --------------------------------------------------------
    # Strategy / engine
    # --------------------------------------------------------
    strategy = UniversalV15Strategy(settings)
    engine = TradingEngine(
        settings,
        BacktestAdapter(),
        strategy,
    )
    # Enough history for strategy readiness.
    warmup = max(
        settings.volume_lookback,
        settings.volatility_bars,
        settings.nbar_volatility_bars,
        settings.adx_length * 3,
        settings.rsi_length + 10,
        200,
    )
    history_bars = max(
        warmup + 50,
        300,
    )
    start_bar = min(
        warmup,
        total - 1,
    )
    # --------------------------------------------------------
    # Main simulation
    # --------------------------------------------------------
    for end in range(
        start_bar + 1,
        total + 1,
    ):
        start = max(
            0,
            end - history_bars,
        )
        window = prepared.iloc[start:end]
        engine.step(window)
        if total >= 5000 and (
            end == start_bar + 1
            or end % 5000 == 0
            or end == total
        ):
            pct = end / total * 100.0
            print(
                f"[BACKTEST] {end:,}/{total:,} "
                f"({pct:.1f}%) "
                f"trades={engine.closed_trades}",
                flush=True,
            )
    pf = (
        engine.gross_profit
        / engine.gross_loss
        if engine.gross_loss
        else None
    )
    peak = float(
        settings.initial_capital
    )
    max_dd = 0.0
    for point in engine.equity_curve:
        equity = float(
            point["equity"]
        )
        peak = max(
            peak,
            equity,
        )
        if peak:
            dd = (
                (peak - equity)
                / peak
                * 100.0
            )
            max_dd = max(
                max_dd,
                dd,
            )
    return BacktestResult(
        trades=engine.closed_trades,
        wins=engine.winning_trades,
        win_rate=(
            engine.winning_trades
            / engine.closed_trades
            * 100
            if engine.closed_trades
            else 0.0
        ),
        profit_factor=pf,
        pnl=engine.realized_pnl,
        return_percent=(
            engine.realized_pnl
            / settings.initial_capital
            * 100
            if settings.initial_capital
            else 0.0
        ),
        max_drawdown_percent=max_dd,
        trades_log=engine.trade_log,
        equity_curve=engine.equity_curve,
    )
