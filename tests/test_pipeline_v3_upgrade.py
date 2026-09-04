from pathlib import Path

import numpy as np

from universal_bot.backtest import _consecutive_candle_direction_ok
from universal_bot.config import Settings


def test_consecutive_candle_direction_helper():
    opens = np.array([10.0, 9.0, 8.0, 9.0])
    closes = np.array([9.0, 8.0, 7.0, 10.0])
    assert _consecutive_candle_direction_ok(opens, closes, 2, 3, "LONG") is True
    assert _consecutive_candle_direction_ok(opens, closes, 3, 3, "LONG") is False
    assert _consecutive_candle_direction_ok(opens, closes, 3, 1, "SHORT") is True


def test_three_tick_all_entries_setting_defaults_off():
    settings = Settings()
    assert settings.apply_consecutive_candles_to_all_entries is False


def test_android_pipeline_engine_locked_source_contract():
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    main = (root / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    assert '"mdd_limit_percent": 70.0' in bridge
    assert "top10-independent-refine-v4-engine-locked" in bridge
    assert "rolling_6m" in bridge and "rolling_3m" in bridge
    assert "broadOptimizationTrials" in main and "refineOptimizationTrials" in main
    assert "모든 진입 3틱룰" in main
