from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_allows_five_thousand_trials_per_stage_and_top10_refine():
    java = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    bridge = (ROOT / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    assert "broadOptimizationTrials > 5000" in java
    assert "refineOptimizationTrials > 5000" in java
    assert "broad_optimization_trials <= 5000" in bridge
    assert "refine_optimization_trials <= 5000" in bridge
    assert '"5000회"' in java
    assert '"3봉 분할형"' in java
    assert "top10-independent-refine-v3" in bridge
    assert "bases = top_rows[:10]" in bridge
    assert "trials_per_seed = min(5000" in bridge
    assert "expected_trials = len(top_rows) * trials_per_seed" in bridge
    assert "rolling_6m" in bridge and "rolling_3m" in bridge
    assert '"mdd_limit_percent": 70.0' in bridge
    assert "모든 진입 3틱룰" in java


def test_android_shares_result_and_cache_through_file_provider():
    java = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    paths = (ROOT / "android/app/src/main/res/xml/file_paths.xml").read_text(encoding="utf-8")
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert "최종 백테스트 원본 JSON 공유" in java
    assert "전체 최적화 통합 JSON 공유" in java
    assert "1차 전체 탐색 결과" in java
    assert "2차 정밀 탐색 결과" in java
    assert "3차 6개월 롤링 결과" in java
    assert "4차 3개월 롤링 결과" in java
    assert "5차 최종 선정 결과" in java
    assert "현재 캐시 DB 공유" in java
    assert "FileProvider.getUriForFile" in java
    assert 'files-path name="backtest_cache"' in paths
    assert 'androidx.core.content.FileProvider' in manifest


def test_all_strategy_performance_fields_are_optimized_or_fixed():
    bridge = (ROOT / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    optimized = {
        "allow_long", "allow_short", "order_percent_of_equity", "max_pyramiding",
        "volume_lookback", "volume_break_multiplier", "min_one_bar_vol",
        "max_one_bar_vol", "volatility_bars", "tp_vol_multiplier",
        "sl_vol_multiplier", "min_tp_percent", "max_tp_percent",
        "min_sl_percent", "max_sl_percent", "use_nbar_volatility_block",
        "nbar_volatility_bars", "max_nbar_volatility", "use_adx_filter",
        "adx_length", "adx_min", "adx_max", "use_rsi_filter", "rsi_length",
        "rsi_oversold_min", "rsi_oversold_max", "rsi_overbought_min",
        "rsi_overbought_max", "cooldown_bars", "reentry_bars",
        "block_weekend", "excluded_hours",
    }
    for field in optimized:
        assert f'"{field}"' in bridge
    for field, value in {
        "initial_capital": "1000.0",
        "leverage": "50",
        "backtest_fee_percent": "0.02",
        "backtest_slippage_percent": "0.01",
    }.items():
        assert f'"{field}": {value}' in bridge


def test_android_stop_is_checked_inside_active_backtest_trial():
    backtest = (ROOT / "universal_bot/backtest.py").read_text(encoding="utf-8")
    fast = (ROOT / "universal_bot/fast_backtest.py").read_text(encoding="utf-8")
    bridge = (ROOT / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    cache = (ROOT / "universal_bot/local_cache_core.py").read_text(encoding="utf-8")
    assert "(i - start_idx) % 256 == 0" in backtest
    assert "control_check()" in backtest
    assert "control_check=control_check" in fast
    assert bridge.count("control_check=_wait_for_optimization_control") >= 5
    assert "control_check=control_check" in cache
    service = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java").read_text(encoding="utf-8")
    assert "static volatile boolean stopRequested" in service
    assert "isStopRequested()" in service
    assert "isWorkerRunning()" in service
    assert "_native_stop_requested()" in bridge
    activity = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    assert '"STOPPING".equals(state) && !BacktestForegroundService.isWorkerRunning()' in activity
    assert '.putString("backtest_status", "STOPPED")' in activity
