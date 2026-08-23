from datetime import timezone

import numpy as np
import pandas as pd

from universal_bot.backtest import run_backtest
from universal_bot.backtest_service import _dt
from universal_bot.config import Settings
from universal_bot.engine import TradingEngine
from universal_bot.indicators import dmi_adx, rolling_range_percent, rsi, sma
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
    expected_qty = 10_000 / 100 + 10_000 / 110
    expected_avg = 20_000 / expected_qty
    expected_pnl = (110 - expected_avg) * expected_qty
    assert engine.closed_trades == 1
    assert abs(engine.trade_log[0]["avg_entry_price"] - expected_avg) < 1e-9
    assert abs(engine.realized_pnl - expected_pnl) < 1e-9


def test_precomputed_indicator_path_matches_direct_strategy():
    settings = Settings(use_start_date=False, use_nbar_volatility_block=False, use_adx_filter=True)
    df = make_ohlcv()
    close, high, low, volume = df.close, df.high, df.low, df.volume
    cached = {
        "volume_ratio": float((volume / sma(volume, settings.volume_lookback)).iloc[-1]),
        "n_range": float(rolling_range_percent(high, low, settings.volatility_bars).iloc[-1]),
        "block_range": float(rolling_range_percent(high, low, settings.nbar_volatility_bars).iloc[-1]),
        "adx": float(dmi_adx(high, low, close, settings.adx_length)[2].iloc[-1]),
        "rsi": float(rsi(close, settings.rsi_length).iloc[-1]),
    }
    strategy = UniversalV15Strategy(settings)
    direct = strategy.evaluate(df, "ETH/USDT:USDT", "5m")
    cached_result = strategy.evaluate(df, "ETH/USDT:USDT", "5m", precomputed=cached)
    assert cached_result.signal.side == direct.signal.side
    assert cached_result.signal.reason == direct.signal.reason
    assert abs(cached_result.state.values["adx"] - direct.state.values["adx"]) < 1e-12


def test_default_start_date_is_timezone_aware():
    assert Settings().start_date.tzinfo is not None
