from universal_bot.adapters.ccxt_adapter import CCXTAdapter


class FakeExchange:
    def market(self, symbol):
        return {"symbol": symbol, "contract": True, "contractSize": 0.01}

    def amount_to_precision(self, symbol, amount):
        return str(round(float(amount), 8))


def adapter():
    obj = object.__new__(CCXTAdapter)
    obj.exchange = FakeExchange()
    obj.exchange_id = "bitget"
    obj._volume_exchanges = {}
    return obj


def test_base_amount_converts_to_contracts_and_back():
    a = adapter()
    assert a._to_exchange_amount("ETH/USDT:USDT", 0.25) == 25.0
    assert a._from_exchange_contracts("ETH/USDT:USDT", 25.0) == 0.25


def test_order_filled_amount_is_normalized_back_to_base_units():
    a = adapter()
    order = {"amount": 25.0, "filled": 10.0, "remaining": 15.0, "average": 2000.0}
    normalized = a._normalize_order_amounts("ETH/USDT:USDT", order)
    assert normalized["amount"] == 0.25
    assert normalized["filled"] == 0.10
    assert normalized["remaining"] == 0.15
    assert normalized["exchange_filled"] == 10.0
