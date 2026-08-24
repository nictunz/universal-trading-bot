# Latest light self-hosted verification

- Generated UTC: 2026-08-24T16:12:02Z
- Source commit: 96b5110b6e9301720e6df7e0e6e6665794fc6e5b
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | failure |
| Dashboard HTTP smoke | failure |
| Provider mapping | success |

## Pytest
```text
...FF..............................                                      [100%]
=================================== FAILURES ===================================
_______________ test_base_amount_converts_to_contracts_and_back ________________

    def test_base_amount_converts_to_contracts_and_back():
        a = adapter()
>       assert a._to_exchange_amount("ETH/USDT:USDT", 0.25) == 25.0

tests/test_ccxt_amounts.py:22: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
universal_bot/adapters/ccxt_adapter.py:149: in _to_exchange_amount
    market = self._market(symbol)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <universal_bot.adapters.ccxt_adapter.CCXTAdapter object at 0x7d0b876de170>
symbol = 'ETH/USDT:USDT'

    def _market(self, symbol: str) -> dict:
        if not getattr(self.exchange, "markets", None):
>           self.exchange.load_markets()
E           AttributeError: 'FakeExchange' object has no attribute 'load_markets'

universal_bot/adapters/ccxt_adapter.py:142: AttributeError
__________ test_order_filled_amount_is_normalized_back_to_base_units ___________

    def test_order_filled_amount_is_normalized_back_to_base_units():
        a = adapter()
        order = {"amount": 25.0, "filled": 10.0, "remaining": 15.0, "average": 2000.0}
>       normalized = a._normalize_order_amounts("ETH/USDT:USDT", order)

tests/test_ccxt_amounts.py:29: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
universal_bot/adapters/ccxt_adapter.py:174: in _normalize_order_amounts
    result[key] = self._from_exchange_contracts(symbol, float(value))
universal_bot/adapters/ccxt_adapter.py:162: in _from_exchange_contracts
    market = self._market(symbol)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <universal_bot.adapters.ccxt_adapter.CCXTAdapter object at 0x7d0b78c916c0>
symbol = 'ETH/USDT:USDT'

    def _market(self, symbol: str) -> dict:
        if not getattr(self.exchange, "markets", None):
>           self.exchange.load_markets()
E           AttributeError: 'FakeExchange' object has no attribute 'load_markets'

universal_bot/adapters/ccxt_adapter.py:142: AttributeError
=========================== short test summary info ============================
FAILED tests/test_ccxt_amounts.py::test_base_amount_converts_to_contracts_and_back - AttributeError: 'FakeExchange' object has no attribute 'load_markets'
FAILED tests/test_ccxt_amounts.py::test_order_filled_amount_is_normalized_back_to_base_units - AttributeError: 'FakeExchange' object has no attribute 'load_markets'
2 failed, 33 passed in 68.19s (0:01:08)
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
