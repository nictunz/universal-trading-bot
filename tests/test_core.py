from datetime import timezone

import numpy as np
import pandas as pd

from universal_bot.backtest import run_backtest
from universal_bot.backtest_service import _dt
from universal_bot.config import Settings
from universal_bot.engine import TradingEngine
from universal_bot.strategy.v15 import UniversalV15Strategy


class DummyAdapter:
    asset_class = "crypto"

    def market_order(self, *args, **kwargs):
        return None

    def equity(self):
        return 1_000_000.0

    def fetch_volume_sources(self, *args, **kwargs):
        return {}


def make_ohlcv(n=400):
    idx = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    base = 100 + np.linspace(0, 4, n)
    close = base + np.sin(np.arange(n) / 7)
    open_ = close - 0.2
    high = np.maximum(open_, close) + 0.3
    low = np.minimum(open_, close) - 0.3
    volume = np.full(n, 1_000_000.0)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def test_end_date_is_inclusive():
    dt = _dt("2026-08-23", end_of_day=True)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 23 and dt.minute == 59 and dt.second == 59


def test_backtest_empty_safe():
    settings = Settings(use_start_date=False, use_nbar_volatility_block=False)
    result = run_backtest(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), settings)
    assert result.trades == 0
    assert result.pnl == 0.0


def test_pyramiding_pnl_uses_weighted_average_entry():
    settings = Settings(bot_mode="PAPER", order_percent_of_equity=1.0, initial_capital=1_000_000)
    engine = TradingEngine(settings, DummyAdapter(), UniversalV15Strategy(settings))
    engine.bar_number = 1
    engine._open("LONG", 100.0, 1.0, 2.0)
    engine.bar_number = 2
    engine._open("LONG", 110.0, 1.0, 2.0)
    engine.bar_number = 3
    engine._close(110.0, "TP")
    assert engine.closed_trades == 1
    assert engine.trade_log[0]["avg_entry_price"] > 100.0
    assert abs(engine.realized_pnl - 50.0) < 1e-9
