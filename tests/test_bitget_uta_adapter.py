from universal_bot.adapters.bitget_uta_runtime import BitgetUtaAdapter


def _adapter():
    return BitgetUtaAdapter("key", "secret", "pass")


def test_uta_contract_uses_v3_instruments(monkeypatch):
    adapter = _adapter()
    seen = {}

    def fake_public(path, params):
        seen["path"] = path
        seen["params"] = params
        return [{
            "symbol": "BTCUSDT",
            "status": "online",
            "quantityPrecision": "4",
            "quantityMultiplier": "0.0001",
            "minOrderQty": "0.0001",
            "maxMarketOrderQty": "220",
            "pricePrecision": "1",
            "priceMultiplier": "0.1",
            "maxLeverage": "150",
        }]

    monkeypatch.setattr(adapter, "_public_get", fake_public)
    contract = adapter._contract("BTC/USDT:USDT")
    assert contract["symbol"] == "BTCUSDT"
    assert seen == {
        "path": "/api/v3/market/instruments",
        "params": {"category": "USDT-FUTURES", "symbol": "BTCUSDT"},
    }


def test_uta_market_order_payload_one_way(monkeypatch):
    adapter = _adapter()
    calls = []
    monkeypatch.setattr(adapter, "_qty", lambda symbol, amount: "0.001")
    monkeypatch.setattr(adapter, "_position_mode", lambda symbol: "one_way_mode")

    def fake_request(method, path, params=None, body=None):
        calls.append((method, path, params, body))
        if path == "/api/v3/trade/place-order":
            return {"orderId": "123", "clientOid": body["clientOid"]}
        if path == "/api/v3/trade/order-info":
            return {"orderStatus": "filled", "cumExecQty": "0.001", "avgPrice": "100000"}
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    out = adapter.market_order("BTC/USDT:USDT", "buy", 0.001)
    place = next(x for x in calls if x[1] == "/api/v3/trade/place-order")
    body = place[3]
    assert body["category"] == "USDT-FUTURES"
    assert body["symbol"] == "BTCUSDT"
    assert body["qty"] == "0.001"
    assert body["side"] == "buy"
    assert "productType" not in body
    assert "marginCoin" not in body
    assert "marginMode" not in body
    assert "posSide" not in body
    assert out["status"] == "filled"


def test_uta_reduce_only_one_way(monkeypatch):
    adapter = _adapter()
    monkeypatch.setattr(adapter, "_qty", lambda symbol, amount: "0.001")
    monkeypatch.setattr(adapter, "_position_mode", lambda symbol: "one_way_mode")
    placed = {}

    def fake_request(method, path, params=None, body=None):
        if path == "/api/v3/trade/place-order":
            placed.update(body)
            return {"orderId": "123"}
        if path == "/api/v3/trade/order-info":
            return {"orderStatus": "filled", "cumExecQty": "0.001", "avgPrice": "100000"}
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    adapter.market_order("BTC/USDT:USDT", "sell", 0.001, reduce_only=True)
    assert placed["reduceOnly"] == "yes"
    assert placed["side"] == "sell"


def test_uta_tpsl_is_single_strategy_with_two_logical_legs(monkeypatch):
    adapter = _adapter()
    monkeypatch.setattr(adapter, "_position_mode", lambda symbol: "one_way_mode")
    monkeypatch.setattr(adapter, "_price", lambda symbol, price: str(price))
    captured = {}

    def fake_request(method, path, params=None, body=None):
        assert path == "/api/v3/trade/place-strategy-order"
        captured.update(body)
        return {"orderId": "tpsl-1", "clientOid": body["clientOid"]}

    monkeypatch.setattr(adapter, "_request", fake_request)
    legs = adapter._place_protection("BTC/USDT:USDT", "long", "0.001", 101000.0, 99000.0)
    assert captured["type"] == "tpsl"
    assert captured["tpslMode"] == "partial"
    assert captured["takeProfit"] == "101000.0"
    assert captured["stopLoss"] == "99000.0"
    assert captured["reduceOnly"] == "yes"
    assert len(legs) == 2


def test_uta_account_info_aliases_symbol_configuration(monkeypatch):
    adapter = _adapter()

    def fake_request(method, path, params=None, body=None):
        assert path == "/api/v3/account/settings"
        return {
            "accountMode": "unified",
            "accountLevel": "basic",
            "holdMode": "one_way_mode",
            "symbolConfigList": [{
                "category": "USDT-FUTURES",
                "symbol": "BTCUSDT",
                "marginMode": "crossed",
                "leverage": "15",
            }],
        }

    monkeypatch.setattr(adapter, "_request", fake_request)
    info = adapter.account_info("BTC/USDT:USDT")
    assert info["posMode"] == "one_way_mode"
    assert info["marginMode"] == "crossed"
    assert info["leverage"] == "15"


def test_uta_position_mapping(monkeypatch):
    adapter = _adapter()

    def fake_request(method, path, params=None, body=None):
        assert path == "/api/v3/position/current-position"
        return {"list": [{
            "symbol": "BTCUSDT",
            "posSide": "long",
            "holdMode": "one_way_mode",
            "marginMode": "crossed",
            "total": "0.01",
            "avgPrice": "100000",
            "markPrice": "101000",
            "leverage": "15",
            "unrealisedPnl": "10",
        }]}

    monkeypatch.setattr(adapter, "_request", fake_request)
    pos = adapter.position("BTC/USDT:USDT")
    assert pos["side"] == "LONG"
    assert pos["size"] == 0.01
    assert pos["entry_price"] == 100000.0
    assert pos["position_mode"] == "one_way_mode"
