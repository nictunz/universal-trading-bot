from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from universal_bot.providers.mobile_relay import MobileRelayMarketData


def _payload(generated_at_ms: int) -> dict:
    base = 1_700_000_000_000
    rows = [[base + i * 300_000, float(i + 1)] for i in range(4)]
    return {
        "schema_version": 1,
        "generated_at_ms": generated_at_ms,
        "timeframe": "5m",
        "markets": {
            "BTC/USDT:USDT": {
                "binance": rows,
                "bybit": rows,
            }
        },
    }


def test_mobile_relay_parses_volume_and_common_timestamp(tmp_path):
    path = tmp_path / "relay.json"
    path.write_text(json.dumps(_payload(int(time.time() * 1000))), encoding="utf-8")
    relay = MobileRelayMarketData(path, max_age_seconds=90)

    series = relay.fetch_volume("binance", "BTC/USDT:USDT", "5m", limit=3)
    assert list(series.astype(float)) == [2.0, 3.0, 4.0]
    assert isinstance(series.index, pd.DatetimeIndex)
    assert str(series.index.tz) == "UTC"
    assert relay.latest_common_timestamp("BTC/USDT:USDT", "5m") == series.index[-1]


def test_mobile_relay_fails_closed_when_stale(tmp_path):
    path = tmp_path / "relay.json"
    path.write_text(json.dumps(_payload(int((time.time() - 180) * 1000))), encoding="utf-8")
    relay = MobileRelayMarketData(path, max_age_seconds=90)

    with pytest.raises(RuntimeError, match="stale"):
        relay.fetch_volume("bybit", "BTC/USDT:USDT", "5m")
