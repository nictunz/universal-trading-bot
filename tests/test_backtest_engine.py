from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from universal_bot.backtest import run_backtest
from universal_bot.backtest_engine import (
    FourExchangeVolumeCache,
    build_run_identity,
    candidate_signature,
    feature_cache_info,
    parameter_signature,
    verify_candidate_signature,
)
from universal_bot.paper import normalize_exchange_volume


def _frame(rows: int = 900) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="5min", tz="UTC")
    x = np.arange(rows, dtype=float)
    base = 100.0 + np.sin(x / 7.0) * 2.0
    opens = base + np.sin(x) * 0.35
    closes = base - np.sin(x) * 0.35
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + 0.45,
            "low": np.minimum(opens, closes) - 0.45,
            "close": closes,
            "volume": 100.0 + (x % 31) * 10.0,
        },
        index=index,
    )


def _settings(start: pd.Timestamp) -> SimpleNamespace:
    return SimpleNamespace(
        volume_lookback=20,
        volatility_bars=12,
        nbar_volatility_bars=12,
        adx_length=14,
        rsi_length=8,
        regime_lookback_bars=20,
        adaptive_regime_enabled=False,
        excluded_hours="",
        start_date=start.to_pydatetime(),
        use_start_date=True,
        block_weekend=False,
        initial_capital=1000.0,
        backtest_compounding_enabled=True,
        backtest_maintenance_margin_percent=0.5,
        backtest_fee_percent=0.02,
        backtest_slippage_percent=0.01,
        backtest_execution_model="signal_close",
        backtest_margin_mode="crossed",
        backtest_cross_liquidation_buffer_percent=25.0,
        backtest_max_total_multiplier=15.0,
        tp_vol_multiplier=0.4,
        sl_vol_multiplier=0.8,
        min_tp_percent=0.2,
        max_tp_percent=2.0,
        min_sl_percent=0.3,
        max_sl_percent=2.0,
        volume_break_multiplier=1.0,
        min_one_bar_vol=0.0,
        max_one_bar_vol=5.0,
        use_nbar_volatility_block=False,
        max_nbar_volatility=5.0,
        use_adx_filter=False,
        adx_min=0.0,
        adx_max=100.0,
        use_rsi_filter=False,
        rsi_oversold_min=0.0,
        rsi_oversold_max=100.0,
        rsi_overbought_min=0.0,
        rsi_overbought_max=100.0,
        cooldown_bars=0,
        reentry_bars=0,
        first_entry_consecutive_candles=1,
        apply_consecutive_candles_to_all_entries=False,
        allow_long=True,
        allow_short=True,
        regime_trend_threshold_percent=2.0,
        regime_high_volatility_percent=0.8,
        regime_high_volatility_risk_multiplier=0.5,
        order_percent_of_equity=100.0,
        max_pyramiding=1,
    )


@pytest.mark.parametrize("execution_model", ["signal_close", "next_open"])
def test_compact_optimization_result_matches_detailed_result(execution_model):
    frame = _frame()
    settings = _settings(frame.index[0])
    settings.backtest_execution_model = execution_model
    detailed = run_backtest(frame, settings, include_details=True)
    compact = run_backtest(
        frame,
        settings,
        include_details=False,
        feature_cache_key=("engine-test", execution_model, len(frame)),
    )
    repeated = run_backtest(
        frame,
        settings,
        include_details=False,
        feature_cache_key=("engine-test", execution_model, len(frame)),
    )

    for field in (
        "trades",
        "wins",
        "win_rate",
        "profit_factor",
        "pnl",
        "gross_pnl",
        "estimated_costs",
        "return_percent",
        "max_drawdown_percent",
        "liquidations",
    ):
        detailed_value = getattr(detailed, field)
        compact_value = getattr(compact, field)
        if detailed_value is None:
            assert compact_value is None
            assert getattr(repeated, field) is None
        else:
            assert compact_value == pytest.approx(detailed_value)
            assert getattr(repeated, field) == pytest.approx(compact_value)
    assert compact.trades_log == []
    assert compact.equity_curve == []
    assert feature_cache_info()["hits"] >= 5


def test_four_exchange_volume_cache_preserves_existing_formula():
    frame = _frame(300)
    volumes = {
        name: frame["volume"] * multiplier
        for name, multiplier in {
            "binance": 1.0,
            "bitget": 0.7,
            "okx": 1.4,
            "bybit": 0.9,
        }.items()
    }
    expected = normalize_exchange_volume(volumes, 20, required_sources=4).reindex(frame.index)
    actual = FourExchangeVolumeCache(volumes, frame.index).ratio(20)
    np.testing.assert_allclose(actual, expected.to_numpy(dtype=float), equal_nan=True)


def test_run_identity_locks_engine_cache_period_and_settings():
    base = {
        "cache_sha256": "cache-a",
        "symbol": "BTC/USDT:USDT",
        "timeframe": "5m",
        "requested_start": "2025-01-01",
        "requested_end": "2025-12-31",
        "strategy_overrides": {"volume_lookback": 20, "backtest_execution_model": "next_open"},
        "candidate_schema": "schema-v1",
    }
    first = build_run_identity(**base)
    assert first == build_run_identity(**base)
    assert first != build_run_identity(**{**base, "cache_sha256": "cache-b"})
    assert first != build_run_identity(
        **{**base, "strategy_overrides": {**base["strategy_overrides"], "volume_lookback": 21}}
    )


def test_signed_candidate_detects_any_result_or_parameter_change():
    parameters = {"volume_lookback": 20, "max_pyramiding": 2}
    result = {"return_percent": 12.5, "max_drawdown_percent": 8.0, "trades": 20}
    row = {
        "run_identity": "run-1",
        "parameters": parameters,
        "result": result,
        "candidate_signature": candidate_signature(
            run_identity="run-1", parameters=parameters, result=result
        ),
    }
    assert verify_candidate_signature(row, "run-1")
    assert parameter_signature(parameters) == parameter_signature(dict(reversed(list(parameters.items()))))
    row["result"]["return_percent"] = 12.6
    assert not verify_candidate_signature(row, "run-1")


def test_invalid_ohlc_is_rejected_before_simulation():
    frame = _frame()
    frame.iloc[10, frame.columns.get_loc("high")] = frame.iloc[10]["low"] - 1.0
    with pytest.raises(ValueError, match="invalid OHLC"):
        run_backtest(frame, _settings(frame.index[0]))
