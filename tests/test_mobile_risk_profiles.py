from android.app.src.main.python.mobile_bridge import RISK_PROFILES


def test_mobile_risk_profiles_are_fixed_and_ordered():
    assert RISK_PROFILES["공격형"]["order_percent_of_equity"] == 1500.0
    assert RISK_PROFILES["공격형"]["max_pyramiding"] == 3
    assert RISK_PROFILES["중간형"]["order_percent_of_equity"] == 1000.0
    assert RISK_PROFILES["중간형"]["max_pyramiding"] == 2
    assert RISK_PROFILES["안전형"]["order_percent_of_equity"] == 500.0
    assert RISK_PROFILES["안전형"]["max_pyramiding"] == 1

    for profile in RISK_PROFILES.values():
        assert profile["leverage"] == 50
        assert profile["backtest_fee_percent"] == 0.02
        assert profile["backtest_slippage_percent"] == 0.01
