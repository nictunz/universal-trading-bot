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
    """Deterministic bar-by-bar v15 simulation using the same engine as paper/live."""
    class BacktestAdapter:
        asset_class = settings.asset_class
        def equity(self) -> float:
            return settings.initial_capital
        def market_order(self, *args, **kwargs):
            return {"mode": "BACKTEST", "args": args}
        def fetch_volume_sources(self, *args, **kwargs):
            return {}

    engine = TradingEngine(settings, BacktestAdapter(), UniversalV15Strategy(settings))
    for end in range(max(1, settings.volume_lookback), len(df) + 1):
        engine.step(df.iloc[:end])

    pf = engine.gross_profit / engine.gross_loss if engine.gross_loss else None
    peak = float(settings.initial_capital)
    max_dd = 0.0
    for point in engine.equity_curve:
        equity = float(point["equity"])
        peak = max(peak, equity)
        if peak:
            max_dd = max(max_dd, (peak - equity) / peak * 100)

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
