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
    assert captured["tpTriggerBy"] == "market"
    assert captured["slTriggerBy"] == "market"
    assert captured["tpOrderType"] == "market"
    assert captured["slOrderType"] == "market"
    assert captured["reduceOnly"] == "yes"
    assert len(legs) == 2


def test_uta_ambiguous_order_recovers_same_client_oid_without_reposting(monkeypatch):
    adapter = _adapter()
    calls = []
    place_attempts = 0
    monkeypatch.setattr(adapter, "_qty", lambda symbol, amount: "0.001")
    monkeypatch.setattr(adapter, "_price", lambda symbol, price: str(price))
    monkeypatch.setattr(adapter, "_position_mode", lambda symbol: "one_way_mode")
    monkeypatch.setattr(adapter, "_client_oid", lambda prefix="utb": f"{prefix}-1")

    def fake_request(method, path, params=None, body=None):
        nonlocal place_attempts
        calls.append((method, path, params, body))
        if path == "/api/v3/trade/place-order":
            place_attempts += 1
            raise RuntimeError("Bitget UTA API error HTTP 400 45001: request timed out")
        if path == "/api/v3/trade/order-info":
            assert params == {"orderId": None, "clientOid": "utb-uta-1"}
            return {
                "orderId": "recovered-order",
                "clientOid": "utb-uta-1",
                "orderStatus": "filled",
                "cumExecQty": "0.001",
                "avgPrice": "100000",
            }
        if path == "/api/v3/trade/place-strategy-order":
            return {"orderId": "protection-1", "clientOid": body["clientOid"]}
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    result = adapter.market_order(
        "BTC/USDT:USDT",
        "buy",
        0.001,
        tp_price=101000.0,
        sl_price=99000.0,
    )

    assert place_attempts == 1
    assert result["clientOid"] == "utb-uta-1"
    assert result["recovered_by_client_oid"] is True
    assert len([call for call in calls if call[1] == "/api/v3/trade/place-strategy-order"]) == 1


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


def test_uta_ioc_child_uses_v3_hedge_payload(monkeypatch):
    adapter = _adapter()
    calls = []
    monkeypatch.setattr(adapter, "_qty", lambda symbol, amount: "0.001")
    monkeypatch.setattr(adapter, "_price", lambda symbol, price: "100030.0")
    monkeypatch.setattr(adapter, "_position_mode", lambda symbol: "hedge_mode")

    def fake_request(method, path, params=None, body=None):
        calls.append((method, path, params, body))
        if path == "/api/v3/trade/place-order":
            return {"orderId": "ioc-1", "clientOid": body["clientOid"]}
        if path == "/api/v3/trade/order-info":
            return {
                "orderId": "ioc-1",
                "orderStatus": "filled",
                "cumExecQty": "0.001",
                "avgPrice": "100020",
            }
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    out = adapter._ioc_limit_child("BTC/USDT:USDT", "buy", 0.001, 100030.0)
    place = next(x for x in calls if x[1] == "/api/v3/trade/place-order")
    body = place[3]
    assert body["category"] == "USDT-FUTURES"
    assert body["symbol"] == "BTCUSDT"
    assert body["orderType"] == "limit"
    assert body["timeInForce"] == "ioc"
    assert body["qty"] == "0.001"
    assert body["side"] == "buy"
    assert body["posSide"] == "long"
    assert "productType" not in body
    assert "marginCoin" not in body
    assert "tradeSide" not in body
    assert out["filled"] == 0.001
    assert out["average"] == 100020.0


def test_uta_hedge_market_open_and_close_payloads(monkeypatch):
    adapter = _adapter()
    placed = []
    monkeypatch.setattr(adapter, "_qty", lambda symbol, amount: "0.001")
    monkeypatch.setattr(adapter, "_position_mode", lambda symbol: "hedge_mode")

    def fake_request(method, path, params=None, body=None):
        if path == "/api/v3/trade/place-order":
            placed.append(dict(body))
            return {"orderId": str(len(placed)), "clientOid": body["clientOid"]}
        if path == "/api/v3/trade/order-info":
            return {"orderStatus": "filled", "cumExecQty": "0.001", "avgPrice": "100000"}
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    adapter.market_order("BTC/USDT:USDT", "buy", 0.001)
    adapter.market_order("BTC/USDT:USDT", "sell", 0.001, reduce_only=True)
    adapter.market_order("BTC/USDT:USDT", "sell", 0.001)
    adapter.market_order("BTC/USDT:USDT", "buy", 0.001, reduce_only=True)

    assert (placed[0]["side"], placed[0]["posSide"]) == ("buy", "long")
    assert (placed[1]["side"], placed[1]["posSide"]) == ("sell", "long")
    assert (placed[2]["side"], placed[2]["posSide"]) == ("sell", "short")
    assert (placed[3]["side"], placed[3]["posSide"]) == ("buy", "short")
    assert all("tradeSide" not in body for body in placed)
    assert all("reduceOnly" not in body for body in placed)


def test_uta_hedge_position_rejects_dual_active_sides(monkeypatch):
    adapter = _adapter()

    def fake_request(method, path, params=None, body=None):
        assert path == "/api/v3/position/current-position"
        return {"list": [
            {"posSide": "long", "holdMode": "hedge_mode", "total": "0.01", "avgPrice": "100000"},
            {"posSide": "short", "holdMode": "hedge_mode", "total": "0.01", "avgPrice": "100000"},
        ]}

    monkeypatch.setattr(adapter, "_request", fake_request)
    try:
        adapter.position("BTC/USDT:USDT")
    except RuntimeError as exc:
        assert "multiple active hedge positions" in str(exc)
    else:
        raise AssertionError("dual hedge positions must fail closed")
