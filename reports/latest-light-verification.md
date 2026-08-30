# Latest light self-hosted verification

- Generated UTC: 2026-08-30T11:48:18Z
- Source commit: b761d210442b4490dfa17ae8fd82283204aa0e63
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | failure |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
.....................................................F.............      [100%]
=================================== FAILURES ===================================
_____________________ test_mobile_profile_costs_are_fixed ______________________

    def test_mobile_profile_costs_are_fixed():
>       assert FIXED_BACKTEST == {
            "initial_capital": 1000.0,
            "leverage": 50,
            "backtest_fee_percent": 0.02,
            "backtest_slippage_percent": 0.01,
            "backtest_margin_mode": "crossed",
            "backtest_maintenance_margin_percent": 0.5,
            "backtest_cross_liquidation_buffer_percent": 25.0,
            "backtest_max_total_multiplier": 15.0,
        }
E       AssertionError: assert {'initial_cap...t': 0.01, ...} == {'initial_cap...t': 0.01, ...}
E         
E         Omitting 8 identical items, use -vv to show
E         Left contains 1 more item:
E         {'backtest_compounding_enabled': True}
E         
E         Full diff:
E           {
E               'initial_capital': 1000.0,
E               'leverage': 50,
E               'backtest_fee_percent': 0.02,
E               'backtest_slippage_percent': 0.01,
E               'backtest_margin_mode': 'crossed',
E               'backtest_maintenance_margin_percent': 0.5,
E               'backtest_cross_liquidation_buffer_percent': 25.0,
E               'backtest_max_total_multiplier': 15.0,
E         +     'backtest_compounding_enabled': True,
E           }

tests/test_mobile_risk_profiles.py:47: AssertionError
=========================== short test summary info ============================
FAILED tests/test_mobile_risk_profiles.py::test_mobile_profile_costs_are_fixed - AssertionError: assert {'initial_cap...t': 0.01, ...} == {'initial_cap...t': 0.01, ...}
  
  Omitting 8 identical items, use -vv to show
  Left contains 1 more item:
  {'backtest_compounding_enabled': True}
  
  Full diff:
    {
        'initial_capital': 1000.0,
        'leverage': 50,
        'backtest_fee_percent': 0.02,
        'backtest_slippage_percent': 0.01,
        'backtest_margin_mode': 'crossed',
        'backtest_maintenance_margin_percent': 0.5,
        'backtest_cross_liquidation_buffer_percent': 25.0,
        'backtest_max_total_multiplier': 15.0,
  +     'backtest_compounding_enabled': True,
    }
1 failed, 66 passed in 36.04s
```
## Dashboard
```text
{"health": {"status": "ok", "strategy": "Volume Strategy FINAL Universal v15", "symbols": 1, "errors": [], "live_halted": []}, "state_symbols": 1, "html_bytes": 21203}
```
## Provider
```text
binance_eth= BINANCEFTS_PERP_ETH_USDT
bybit_sol= BYBIT_PERP_SOL_USDT
period_5m= 5MIN
```
