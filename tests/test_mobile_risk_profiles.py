from android.app.src.main.python.mobile_bridge import (
    FIXED_BACKTEST,
    OPTIMIZED_STRATEGY_FIELDS,
    RISK_PROFILES,
    _append_checkpoint_journal,
    _load_checkpoint_journal,
    _profile_candidates,
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
        "mdd_limit_percent": 40.0,
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
    assert candidate["initial_capital"] == 1000.0
    assert candidate["leverage"] == 50
    assert candidate["backtest_fee_percent"] == 0.02
    assert candidate["backtest_slippage_percent"] == 0.01


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
