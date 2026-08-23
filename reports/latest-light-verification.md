# Latest light self-hosted verification

- Generated UTC: 2026-08-23T16:25:23Z
- Source commit: fe664be0a89033b1fc70bc27326338eda58833a7
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | success |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
....F.....................                                               [100%]
=================================== FAILURES ===================================
________________ test_paper_defaults_do_not_require_coinapi_key ________________

    def test_paper_defaults_do_not_require_coinapi_key():
        s = Settings(_env_file=None)
>       assert s.crypto_volume_provider == "community"
E       AssertionError: assert 'none' == 'community'
E         
E         - community
E         + none

tests/test_coinmetrics_provider.py:20: AssertionError
=========================== short test summary info ============================
FAILED tests/test_coinmetrics_provider.py::test_paper_defaults_do_not_require_coinapi_key - AssertionError: assert 'none' == 'community'
  
  - community
  + none
1 failed, 25 passed in 32.51s
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
