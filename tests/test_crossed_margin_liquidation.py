from universal_bot.backtest import crossed_liquidation_hit


def test_crossed_margin_15x_liquidates_near_five_percent_adverse_move():
    common = {
        "side": "LONG",
        "qty": 150.0,
        "avg_entry": 100.0,
        "account_equity_before_open_pnl": 1000.0,
        "initial_capital": 1000.0,
        "maintenance_rate": 0.005,
        "reserve_percent": 25.0,
    }
    assert not crossed_liquidation_hit(worst_mark=95.1, **common)
    assert crossed_liquidation_hit(worst_mark=95.0, **common)


def test_crossed_margin_liquidation_scales_with_actual_exposure():
    assert crossed_liquidation_hit(
        side="LONG",
        qty=30.0,
        avg_entry=100.0,
        worst_mark=75.0,
        account_equity_before_open_pnl=1000.0,
        initial_capital=1000.0,
        maintenance_rate=0.005,
        reserve_percent=25.0,
    )


def test_mobile_optimizer_excludes_liquidated_trials_and_caps_total_exposure():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    bridge = (root / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
    engine = (root / "universal_bot/backtest.py").read_text(encoding="utf-8")
    assert '"backtest_margin_mode": "crossed"' in bridge
    assert '"backtest_max_total_multiplier": 15.0' in bridge
    assert 'int(row["result"].get("liquidations") or 0) == 0' in bridge
    assert "hit_liquidation or hit_tp or hit_sl" in engine
    assert "if hit_liquidation:" in engine
    assert "entry_notional + order_notional <= max_total_notional" in engine


def test_android_compat_settings_include_every_liquidation_field():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    compat = (root / "android/compat/config.py").read_text(encoding="utf-8")
    assert '"backtest_margin_mode": "crossed"' in compat
    assert '"backtest_maintenance_margin_percent": 0.5' in compat
    assert '"backtest_cross_liquidation_buffer_percent": 25.0' in compat
    assert '"backtest_max_total_multiplier": 15.0' in compat
