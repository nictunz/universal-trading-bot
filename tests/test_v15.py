import numpy as np
import pandas as pd

from universal_bot.config import Settings
from universal_bot.models import Position
from universal_bot.strategy.v15 import UniversalV15Strategy


def test_v15_evaluates_without_tradingview():
    n = 400
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC")
    close = pd.Series(100 + np.sin(np.arange(n) / 10) * 0.5, index=idx)
    df = pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": np.full(n, 1000.0),
    }, index=idx)
    df.iloc[-1, df.columns.get_loc("volume")] = 10000

    settings = Settings(use_start_date=False, excluded_hours="", use_adx_filter=False)
    result = UniversalV15Strategy(settings).evaluate(df, "TEST/USDT", "5m", Position())

    assert result.state.symbol == "TEST/USDT"
    assert "final_tp_percent" in result.state.values
    assert "final_sl_percent" in result.state.values
