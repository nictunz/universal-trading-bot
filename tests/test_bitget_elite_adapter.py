from __future__ import annotations

from universal_bot.adapters.bitget_elite import BitgetEliteAdapter
from universal_bot.config import Settings


def _fake_adapter(monkeypatch):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    calls = []

    monkeypatch.setattr(adapter, "_qty", lambda symbol, amount: "0.1000")
    monkeypatch.setattr(adapter, "_price", lambda symbol, price: f"{price:.1f}")
    monkeypatch.setattr(adapter, "_client_oid", lambda prefix="utb": f"{prefix}-1")

    def fake_request(method, path, *, params=None, body=None):
        calls.append((method, path, params, body))
        if path == "/api/v3/trade/place-order":
            return {"orderId": "order-1", "clientOid": body["clientOid"]}
        if path == "/api/v3/trade/order-info":
            return {"orderStatus": "filled", "cumExecQty": "0.1000", "avgPrice": "2500.0"}
        if path == "/api/v3/trade/place-strategy-order":
            return {"orderId": "tpsl-1", "clientOid": body["clientOid"]}
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    return adapter, calls


def test_elite_open_uses_hedge_pos_side_and_separate_tpsl(monkeypatch):
    adapter, calls = _fake_adapter(monkeypatch)
    result = adapter.market_order(
        "ETH/USDT:USDT",
        "buy",
        0.1,
        tp_price=2600.0,
        sl_price=2400.0,
    )

    place = next(x for x in calls if x[1] == "/api/v3/trade/place-order")
    assert place[3]["symbol"] == "ETHUSDT"
    assert place[3]["side"] == "buy"
    assert place[3]["posSide"] == "long"
    assert place[3]["marginMode"] == "crossed"
    assert "takeProfit" not in place[3]

    protection = next(x for x in calls if x[1] == "/api/v3/trade/place-strategy-order")
    assert protection[3]["type"] == "tpsl"
    assert protection[3]["tpslMode"] == "full"
    assert protection[3]["posSide"] == "long"
    assert protection[3]["takeProfit"] == "2600.0"
    assert protection[3]["stopLoss"] == "2400.0"
    assert result["filled"] == 0.1
    assert result["average"] == 2500.0


def test_elite_close_long_does_not_create_new_tpsl(monkeypatch):
    adapter, calls = _fake_adapter(monkeypatch)
    adapter.market_order("ETH/USDT:USDT", "sell", 0.1, reduce_only=True)

    place = next(x for x in calls if x[1] == "/api/v3/trade/place-order")
    assert place[3]["side"] == "sell"
    assert place[3]["posSide"] == "long"
    assert not any(x[1] == "/api/v3/trade/place-strategy-order" for x in calls)


def test_bitget_dual_credentials_are_separate():
    s = Settings(
        bitget_standard_api_key="standard-key",
        bitget_standard_api_secret="standard-secret",
        bitget_standard_api_passphrase="standard-pass",
        bitget_elite_api_key="elite-key",
        bitget_elite_api_secret="elite-secret",
        bitget_elite_api_passphrase="elite-pass",
    )
    assert s.bitget_standard_credentials == ("standard-key", "standard-secret", "standard-pass")
    assert s.bitget_elite_credentials == ("elite-key", "elite-secret", "elite-pass")
