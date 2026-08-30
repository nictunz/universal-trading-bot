from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_allows_five_thousand_trials_and_preserves_prefix():
    java = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    bridge = (ROOT / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    assert "optimizationTrials > 5000" in java
    assert "optimization_trials > 5000" in bridge
    assert '"5000회"' in java
    assert '"3봉 분할형"' in java
    assert 'trial-{position:04d}' in bridge
    assert 'seed_material = f"{symbol}|{timeframe}|{start_text}|{end_text}|{profile_name}|coarse-buckets-v2"' in bridge
    assert "broad_trials = min(1000, optimization_trials)" in bridge
    assert "refine_trials = min(5000, max(1, int(trials)))" in bridge
    assert '"top_candidates": ranked[:30]' in bridge
    assert 'candidates = list(refined.get("top_candidates") or [])[:30]' in bridge


def test_android_shares_result_and_cache_through_file_provider():
    java = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    paths = (ROOT / "android/app/src/main/res/xml/file_paths.xml").read_text(encoding="utf-8")
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert "최신 결과 JSON 공유" in java
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
