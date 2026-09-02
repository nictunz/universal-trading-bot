# Latest light self-hosted verification

- Generated UTC: 2026-09-02T22:35:47Z
- Source commit: 10fbdda9ed16e61915837a3e3fb0bc4bdae2f654
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | failure |
| Dashboard HTTP smoke | cancelled |
| Provider mapping | skipped |

## Pytest
```text
........FF.............................................................. [ 96%]
...                                                                      [100%]
=================================== FAILURES ===================================
________________ test_signal_close_preserves_legacy_entry_price ________________

    def test_signal_close_preserves_legacy_entry_price():
        df, ratios = _execution_fixture()
        result = run_backtest(df, _settings("signal_close"), ratios)
>       assert result.trades == 1
E       AssertionError: assert 0 == 1
E        +  where 0 = BacktestResult(trades=0, wins=0, win_rate=0.0, profit_factor=None, pnl=0, gross_pnl=0.0, estimated_costs=0.0, return_p..., liquidations=0, trades_log=[], equity_curve=[{'bar': 1, 'timestamp': '2025-01-01T19:55:00+00:00', 'equity': 1000.0}]).trades

tests/test_backtest_execution_models.py:66: AssertionError
_____________ test_next_open_enters_only_on_following_candle_open ______________

    def test_next_open_enters_only_on_following_candle_open():
        df, ratios = _execution_fixture()
        result = run_backtest(df, _settings("next_open"), ratios)
>       assert result.trades == 1
E       AssertionError: assert 0 == 1
E        +  where 0 = BacktestResult(trades=0, wins=0, win_rate=0.0, profit_factor=None, pnl=0, gross_pnl=0.0, estimated_costs=0.0, return_p..., liquidations=0, trades_log=[], equity_curve=[{'bar': 1, 'timestamp': '2025-01-01T19:55:00+00:00', 'equity': 1000.0}]).trades

tests/test_backtest_execution_models.py:73: AssertionError
=========================== short test summary info ============================
FAILED tests/test_backtest_execution_models.py::test_signal_close_preserves_legacy_entry_price - AssertionError: assert 0 == 1
 +  where 0 = BacktestResult(trades=0, wins=0, win_rate=0.0, profit_factor=None, pnl=0, gross_pnl=0.0, estimated_costs=0.0, return_p..., liquidations=0, trades_log=[], equity_curve=[{'bar': 1, 'timestamp': '2025-01-01T19:55:00+00:00', 'equity': 1000.0}]).trades
FAILED tests/test_backtest_execution_models.py::test_next_open_enters_only_on_following_candle_open - AssertionError: assert 0 == 1
 +  where 0 = BacktestResult(trades=0, wins=0, win_rate=0.0, profit_factor=None, pnl=0, gross_pnl=0.0, estimated_costs=0.0, return_p..., liquidations=0, trades_log=[], equity_curve=[{'bar': 1, 'timestamp': '2025-01-01T19:55:00+00:00', 'equity': 1000.0}]).trades
2 failed, 73 passed in 40.49s
```
## Dashboard
```text
```
## Provider
```text
binance_eth= BINANCEFTS_PERP_ETH_USDT
bybit_sol= BYBIT_PERP_SOL_USDT
period_5m= 5MIN
```
