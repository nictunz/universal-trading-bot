from android.app.src.main.python.mobile_bridge import FIXED_BACKTEST, RISK_PROFILES


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

    safe = RISK_PROFILES["안전형"]
    assert safe == {
        "mdd_limit_percent": 15.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 8,
        "max_entries_values": [1],
    }


def test_mobile_profile_costs_are_fixed():
    assert FIXED_BACKTEST == {
        "leverage": 50,
        "backtest_fee_percent": 0.02,
        "backtest_slippage_percent": 0.01,
    }
