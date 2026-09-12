import json
import sqlite3

from android.app.src.main.python.mobile_bridge import (
    FIXED_BACKTEST,
    OPTIMIZED_STRATEGY_FIELDS,
    RISK_PROFILES,
    _append_checkpoint_journal,
    _load_checkpoint_journal,
    _profile_candidates,
    candidate_signature,
    engine_manifest,
    list_top_strategies,
    saved_result_replay_payload,
)


def test_mobile_risk_profiles_use_mdd_and_search_ranges():
    aggressive = RISK_PROFILES["공격형"]
    assert aggressive == {
        "mdd_limit_percent": 40.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 25,
        "max_entries_values": [1, 2],
    }

    balanced = RISK_PROFILES["중간형"]
    assert balanced == {
        "mdd_limit_percent": 25.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 15,
        "max_entries_values": [1, 2],
    }

    split = RISK_PROFILES["3봉 분할형"]
    assert split == {
        "mdd_limit_percent": 70.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 3,
        "max_entries_values": [1, 2, 3, 4, 5],
        "first_entry_consecutive_candles": 3,
    }

    safe = RISK_PROFILES["안전형"]
    assert safe == {
        "mdd_limit_percent": 15.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 8,
        "max_entries_values": [1],
    }


def test_mobile_profile_costs_are_fixed():
    assert FIXED_BACKTEST == {
        "initial_capital": 1000.0,
        "leverage": 50,
        "backtest_fee_percent": 0.02,
        "backtest_slippage_percent": 0.01,
        "backtest_margin_mode": "crossed",
        "backtest_maintenance_margin_percent": 0.5,
        "backtest_cross_liquidation_buffer_percent": 25.0,
        "backtest_max_total_multiplier": 15.0,
        "backtest_compounding_enabled": True,
    }


def test_mobile_trials_are_deterministic_unique_and_incremental():
    first_50 = _profile_candidates("공격형", 50, "same-run")
    first_1000 = _profile_candidates("공격형", 1000, "same-run")
    assert first_1000[:50] == first_50
    assert len({str(sorted(row.items())) for row in first_1000}) == 1000
    assert all(1 <= row["entry_multiplier"] <= 25 for row in first_1000)
    assert all(row["max_pyramiding"] in (1, 2) for row in first_1000)
    assert all(3.0 <= row["volume_break_multiplier"] <= 25.0 for row in first_1000)


def test_trial_ranges_follow_selected_profile():
    safe = _profile_candidates("안전형", 300, "safe-run")
    assert len(safe) == 300
    assert all(1 <= row["entry_multiplier"] <= 8 for row in safe)
    assert all(row["max_pyramiding"] == 1 for row in safe)


def test_every_effective_v15_strategy_field_is_sampled():
    candidate = _profile_candidates("중간형", 1, "coverage")[0]
    assert not (candidate["allow_long"] is False and candidate["allow_short"] is False)
    assert set(OPTIMIZED_STRATEGY_FIELDS).issubset(candidate)
    # Money and execution settings come from the user's authoritative base
    # settings. Candidates must never silently reset them to defaults.
    assert set(FIXED_BACKTEST).isdisjoint(candidate)


def test_saved_replay_keeps_original_cache_fingerprint(tmp_path):
    database = tmp_path / "mutable.db"
    with sqlite3.connect(database) as con:
        con.execute(
            "CREATE TABLE ohlcv (asset_class TEXT, exchange TEXT, symbol TEXT, "
            "timeframe TEXT, timestamp INTEGER, open REAL, high REAL, low REAL, "
            "close REAL, volume REAL)"
        )
        con.execute(
            "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("crypto", "bitget", "BTC/USDT:USDT", "5m", 1735689600000,
             100.0, 101.0, 99.0, 100.5, 42.0),
        )
    result_file = tmp_path / "saved-backtest.json"
    result_file.write_text(json.dumps({
        "database": str(database),
        "cache_sha256": "original-run-cache-sha",
        "engine": engine_manifest(),
        "optimization_run_identity": "original-run-id",
        "optimization_base_overrides": dict(FIXED_BACKTEST),
        "risk_profile_selection": {"parameters": {"volume_lookback": 20}},
        "requested_start": "2025-01-01",
        "requested_end": "2025-01-01",
        "return_percent": 12.5,
        "max_drawdown_percent": 4.0,
        "win_rate": 50.0,
        "profit_factor": 1.5,
        "trades": 2,
    }), encoding="utf-8")

    replay = json.loads(saved_result_replay_payload(str(result_file)))

    assert replay["source_context"]["cache_sha256"] == "original-run-cache-sha"


def test_top10_replay_uses_full_effective_settings_and_signed_result(tmp_path):
    run_identity = "locked-run-id"
    parameters = _profile_candidates("중간형", 1, "signed-top10")[0]
    result = {
        "trades": 12,
        "wins": 7,
        "win_rate": 58.333333,
        "profit_factor": 1.8,
        "pnl": 250.0,
        "gross_pnl": 270.0,
        "estimated_costs": 20.0,
        "return_percent": 10.0,
        "max_drawdown_percent": 8.0,
        "liquidations": 0,
    }
    row = {
        "parameters": parameters,
        "result": result,
        "run_identity": run_identity,
        "candidate_signature": candidate_signature(
            run_identity=run_identity,
            parameters=parameters,
            result=result,
        ),
    }
    checkpoint = tmp_path / "risk.json"
    checkpoint.write_text(json.dumps({
        "run_identity": run_identity,
        "candidate_schema": "test-engine-locked",
        "completed": {"trial-1": row},
    }), encoding="utf-8")
    base = {
        **FIXED_BACKTEST,
        "initial_capital": 2500.0,
        "backtest_compounding_enabled": False,
        "backtest_execution_model": "next_open",
        "adaptive_regime_enabled": True,
    }
    saved = tmp_path / "saved-backtest.json"
    saved.write_text(json.dumps({
        "optimization_run_identity": run_identity,
        "optimization_base_overrides": base,
        "risk_profile_selection": {
            "checkpoint": str(checkpoint),
            "constraints": {"mdd_limit_percent": 25.0},
        },
        "requested_start": "2025-01-01",
        "requested_end": "2025-12-31",
        "data_start": "2025-01-01T00:00:00+00:00",
        "data_end": "2025-12-31T23:55:00+00:00",
        "bars": 105120,
        "cache_sha256": "cache-locked",
        "engine": engine_manifest(),
    }), encoding="utf-8")

    item = json.loads(list_top_strategies(str(saved), 10))["items"][0]
    effective = item["effective_parameters"]

    assert effective["initial_capital"] == 2500.0
    assert effective["backtest_compounding_enabled"] is False
    assert effective["backtest_execution_model"] == "next_open"
    assert item["source_context"]["candidate_signature"] == candidate_signature(
        run_identity=run_identity,
        parameters=effective,
        result=result,
    )


def test_three_candle_split_profile_is_unique_and_capped():
    rows = _profile_candidates("3봉 분할형", 5000, "split-5000")
    assert len(rows) == 5000
    assert len({str(sorted(row.items())) for row in rows}) == 5000
    assert all(1 <= row["entry_multiplier"] <= 3 for row in rows)
    assert all(1 <= row["max_pyramiding"] <= 5 for row in rows)
    assert all(row["first_entry_consecutive_candles"] == 3 for row in rows)
    assert all(row["entry_multiplier"] * row["max_pyramiding"] <= 15 for row in rows)


def test_incremental_trial_journal_recovers_without_full_rewrite(tmp_path):
    journal = tmp_path / "risk.journal.jsonl"
    _append_checkpoint_journal(journal, "fingerprint-a", "trial-1", {"result": {"pnl": 1}})
    _append_checkpoint_journal(journal, "fingerprint-a", "trial-2", {"result": {"pnl": 2}})
    _append_checkpoint_journal(journal, "old-fingerprint", "stale", {"result": {"pnl": 99}})
    completed = {}
    loaded = _load_checkpoint_journal(journal, "fingerprint-a", completed)
    assert loaded == 2
    assert set(completed) == {"trial-1", "trial-2"}


def test_android_exposes_fixed_and_compound_sizing_controls():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    activity = (root / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    service = (root / "android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java").read_text(encoding="utf-8")
    bridge = (root / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    assert 'new String[]{"복리식", "고정식"}' in activity
    assert 'intent.putExtra("compounding_enabled", compoundingEnabled)' in activity
    assert '"sizing_mode", "compounding_enabled"' in activity
    assert 'request.optBoolean("compounding_enabled", true)' in service
    assert 'compounding_enabled: bool = True' in bridge
    assert 'overrides["backtest_compounding_enabled"] = bool(compounding_enabled)' in bridge


def test_android_preserves_saved_optimization_job_protocol():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    activity = (root / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
    service = (root / "android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java").read_text(encoding="utf-8")
    bridge = (root / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    assert 'intent.putExtra("optimization_stage", optimizationStage)' in activity
    assert 'intent.putExtra("broad_optimization_trials", broadOptimizationTrials)' in activity
    assert 'intent.putExtra("refine_optimization_trials", refineOptimizationTrials)' in activity
    assert 'intent.putExtra("all_entries_three_tick", allEntriesThreeTick)' in activity
    assert 'request.optString("optimization_stage", "broad")' in service
    assert 'request.optInt("broad_optimization_trials"' in service
    assert 'request.optInt("refine_optimization_trials"' in service
    assert 'request.optBoolean("all_entries_three_tick", false)' in service
    assert "def _refine_top_candidates(" in bridge
    assert "def _rolling_validate_candidates(" in bridge
    assert '"positive_windows"' in bridge
    assert '"rolling_6m"' in bridge and '"rolling_3m"' in bridge
    assert '"paper_live_applied": False' in bridge
