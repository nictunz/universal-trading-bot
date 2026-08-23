from datetime import datetime, timezone

import pandas as pd

from universal_bot.live_safety import LiveSafety
from universal_bot.main import completed_candles


def test_reconciliation_halts_on_position_mismatch():
    safety = LiveSafety(enabled=True, protection_ok=True)
    ok = safety.reconcile(
        {"side": "LONG", "size": 1.0},
        {"side": "SHORT", "size": 1.0},
    )
    assert not ok
    assert safety.halted
    assert "POSITION_MISMATCH" in safety.reason


def test_reconciliation_accepts_matching_flat():
    safety = LiveSafety(enabled=True, protection_ok=True)
    assert safety.reconcile({"side": "FLAT", "size": 0}, {"side": "FLAT", "size": 0})
    assert not safety.halted


def test_completed_candles_drops_open_current_bar():
    now = pd.Timestamp.now(tz="UTC")
    current_start = now.floor("5min")
    index = pd.DatetimeIndex([current_start - pd.Timedelta(minutes=5), current_start])
    df = pd.DataFrame({"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2], "volume": [1, 1]}, index=index)
    out = completed_candles(df, "5m")
    assert len(out) == 1
    assert out.index[-1] == current_start - pd.Timedelta(minutes=5)
