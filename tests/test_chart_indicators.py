import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from universal_bot.chart_indicators import calculate


def test_chart_overlays_do_not_use_future_candles():
    rng = np.random.default_rng(33)
    close = 100 + np.cumsum(rng.normal(size=420))
    frame = pd.DataFrame({"close": close, "high": close + 1, "low": close - 1})
    complete = calculate(frame)
    prefix = calculate(frame.iloc[:260])
    assert_frame_equal(prefix, complete.iloc[:260])
    changed = frame.copy()
    changed.loc[260:, ["close", "high", "low"]] *= 100
    assert_frame_equal(prefix, calculate(changed).iloc[:260])


def test_chart_overlay_warmup_and_flat_series_are_explicit():
    frame = pd.DataFrame({"close": [100.] * 250, "high": [101.] * 250, "low": [99.] * 250})
    result = calculate(frame)
    assert result.iloc[:199].ema200.isna().all()
    assert result.iloc[199:].ema200.eq(100).all()
    assert result.iloc[19:].bb_upper.eq(100).all()
    assert result.iloc[19:].bb_lower.eq(100).all()
    assert result.iloc[:14].rsi14.isna().all()
    assert result.iloc[:27].adx14.isna().all()
