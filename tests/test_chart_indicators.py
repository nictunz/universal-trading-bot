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


def test_custom_rsi_length_is_causal_and_changes_values():
    rng = np.random.default_rng(61)
    close = 100 + np.cumsum(rng.normal(size=300))
    frame = pd.DataFrame({"close": close, "high": close + 1, "low": close - 1})
    short = calculate(frame, 10)
    long = calculate(frame, 25)
    assert short.iloc[:10].rsi.isna().all()
    assert long.iloc[:25].rsi.isna().all()
    assert not np.allclose(short.rsi.iloc[25:], long.rsi.iloc[25:])
    assert_frame_equal(calculate(frame.iloc[:200], 10), short.iloc[:200])
    for invalid in (0, 1, 501):
        try:
            calculate(frame, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid RSI length accepted")
