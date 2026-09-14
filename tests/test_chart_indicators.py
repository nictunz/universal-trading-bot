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


def test_page_cache_survives_memory_reset_and_invalidates(tmp_path, monkeypatch):
    import json
    from universal_bot import chart_indicators as module
    identity = {"version": 1}
    calls = []
    monkeypatch.setattr(module, "stamp", lambda path: dict(identity))
    def dataset(*args):
        calls.append(args)
        return pd.DataFrame({"rsi": [12.5, 42.0]}, index=[1000, 2000])
    monkeypatch.setattr(module, "_dataset", dataset)
    args = (str(tmp_path / "candles.db"), "bitget", "BTC/USDT:USDT", "15m", 1000, 2000)
    first = module.indicator_page(*args, 10)
    assert module.indicator_page(*args, 10) == first
    assert len(calls) == 1
    assert json.loads(first)[0] == {"timestamp": 1000, "rsi": 12.5}
    module.indicator_page(*args, 14)
    assert len(calls) == 2
    identity["version"] = 2
    module.indicator_page(*args, 10)
    assert len(calls) == 3
    for item in (tmp_path / "chart-indicator-cache").glob("*.json"):
        item.write_text("broken")
    assert module.indicator_page(*args, 10) == first
    assert len(calls) == 4


def test_custom_ema_and_volume_lines_are_causal():
    import json
    rng = np.random.default_rng(14)
    close = 100 + np.cumsum(rng.normal(size=300))
    frame = pd.DataFrame({"close": close, "high": close+1, "low": close-1, "volume": np.arange(300)+10.})
    options = json.dumps({"ema1": 7, "ema2": 12, "ema3": 55, "volume_length": 20, "volume_multiplier": 3.2})
    result = calculate(frame, 10, options)
    assert_frame_equal(calculate(frame.iloc[:200], 10, options), result.iloc[:200])
    assert np.allclose(result.ema_custom1.iloc[6:], frame.close.ewm(span=7, adjust=False, min_periods=7).mean().iloc[6:])
    assert result.volume_sma.iloc[:19].isna().all()
    assert np.allclose(result.volume_break.iloc[19:], frame.volume.rolling(20).mean().iloc[19:]*3.2)
