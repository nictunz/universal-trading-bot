from __future__ import annotations

from datetime import datetime, timezone

from universal_bot.providers.bitget_history import BitgetHistoricalMarketData


class _Response:
    status_code = 200
    text = ""

    def __init__(self, data):
        self._data = data

    def json(self):
        return {"code": "00000", "msg": "success", "data": self._data}


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(dict(params))
        end = int(params["endTime"])
        step = 300_000
        # Emulate Bitget returning up to three candles ending at endTime,
        # ascending by timestamp.
        data = []
        for ts in range(end - 2 * step, end + 1, step):
            if ts >= 0:
                data.append([str(ts), "1", "2", "0.5", "1.5", "10", "15"])
        return _Response(data)


def test_backward_pagination_is_gap_free():
    session = _Session()
    p = BitgetHistoricalMarketData(session=session)
    start = datetime.fromtimestamp(0, timezone.utc)
    end = datetime.fromtimestamp(30 * 60, timezone.utc)
    df = p.fetch_history("ETH/USDT:USDT", "5m", start, end)
    assert len(df) == 7
    assert df.index.is_monotonic_increasing
    diffs = df.index.to_series().diff().dropna().dt.total_seconds().tolist()
    assert diffs == [300.0] * 6
    assert len(session.calls) >= 3


def test_symbol_and_granularity_mapping():
    assert BitgetHistoricalMarketData.compact_symbol("SOL/USDT:USDT") == "SOLUSDT"
    assert BitgetHistoricalMarketData.granularity("5m") == "5m"
    assert BitgetHistoricalMarketData.granularity("4h") == "4H"
