from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_background_service_is_registered_and_persistent():
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    service = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java").read_text(encoding="utf-8")
    assert ".BacktestForegroundService" in manifest
    assert 'android:stopWithTask="false"' in manifest
    assert 'android:foregroundServiceType="specialUse"' in manifest
    assert "START_STICKY" in service
    assert "PARTIAL_WAKE_LOCK" in service
    assert "startForeground(" in service


def test_background_service_has_pause_resume_stop_and_checkpoint_semantics():
    service = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java").read_text(encoding="utf-8")
    bridge = (ROOT / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    core = (ROOT / "universal_bot/local_cache_core.py").read_text(encoding="utf-8")
    activity = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    for action in ("ACTION_PAUSE", "ACTION_RESUME", "ACTION_STOP"):
        assert action in service
        assert action in activity
    assert "set_optimization_paused" in bridge
    assert "request_optimization_stop" in bridge
    assert "_wait_for_optimization_control()" in bridge
    assert "control_check()" in core
    assert "완료된 체크포인트는 보존됩니다" in bridge


def test_activity_delegates_work_instead_of_owning_long_python_call():
    activity = (ROOT / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    run_method = activity.split("private void runBacktest()", 1)[1].split("private void controlBacktest", 1)[0]
    assert "BacktestForegroundService.ACTION_START" in run_method
    assert "startForegroundService" in run_method
    assert 'bridge.callAttr(\n                        "run_backtest"' not in run_method
