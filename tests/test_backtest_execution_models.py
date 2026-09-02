import numpy as np
import pandas as pd

from universal_bot.backtest import run_backtest
from universal_bot.config import Settings


def _execution_fixture():
    n = 240
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame({
        "open": np.full(n, 100.0),
        "high": np.full(n, 100.2),
        "low": np.full(n, 98.8),
        "close": np.full(n, 100.0),
        "volume": np.full(n, 1000.0),
    }, index=idx)
    signal_bar = 210
    df.iloc[signal_bar, df.columns.get_loc("open")] = 100.0
    df.iloc[signal_bar, df.columns.get_loc("close")] = 99.0
    df.iloc[signal_bar + 1, df.columns.get_loc("open")] = 110.0
    df.iloc[signal_bar + 1, df.columns.get_loc("high")] = 112.0
    df.iloc[signal_bar + 1, df.columns.get_loc("low")] = 109.0
    df.iloc[signal_bar + 1, df.columns.get_loc("close")] = 111.0
    ratios = pd.Series(np.zeros(n), index=idx)
    ratios.iloc[signal_bar] = 10.0
    return df, ratios


def _settings(model: str) -> Settings:
    return Settings(
        use_start_date=False,
        excluded_hours="",
        allow_long=True,
        allow_short=False,
        use_adx_filter=False,
        use_rsi_filter=False,
        use_nbar_volatility_block=False,
        volume_lookback=20,
        volume_break_multiplier=3.0,
        min_one_bar_vol=0.5,
        max_one_bar_vol=2.0,
        volatility_bars=20,
        nbar_volatility_bars=20,
        tp_vol_multiplier=1.0,
        sl_vol_multiplier=1.0,
        min_tp_percent=1.0,
        max_tp_percent=1.0,
        min_sl_percent=1.0,
        max_sl_percent=1.0,
        first_entry_consecutive_candles=1,
        order_percent_of_equity=100.0,
        max_pyramiding=1,
        cooldown_bars=0,
        reentry_bars=0,
        initial_capital=1000.0,
        backtest_fee_percent=0.0,
        backtest_slippage_percent=0.0,
        backtest_execution_model=model,
    )


def test_signal_close_preserves_legacy_entry_price():
    df, ratios = _execution_fixture()
    result = run_backtest(df, _settings("signal_close"), ratios)
    assert result.trades == 1
    assert result.trades_log[0]["avg_entry_price"] == 99.0


def test_next_open_enters_only_on_following_candle_open():
    df, ratios = _execution_fixture()
    result = run_backtest(df, _settings("next_open"), ratios)
    assert result.trades == 1
    assert result.trades_log[0]["avg_entry_price"] == 110.0
    assert result.trades_log[0]["entry_time"] == df.index[211].isoformat()
