import pandas as pd
from universal_bot.backtest_engine import prepare_engine_arrays
from universal_bot.config import Settings


def test_millisecond_index_is_normalized_for_start_date_filter():
    index = pd.date_range("2026-07-01", periods=240, freq="15min", tz="UTC").as_unit("ms")
    frame = pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.,"volume":1.}, index=index)
    arrays = prepare_engine_arrays(frame, Settings())
    assert arrays.market.timestamp_ns[0] == pd.Timestamp("2026-07-01", tz="UTC").value
