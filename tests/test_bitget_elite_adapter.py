from __future__ import annotations

from universal_bot.adapters.bitget_elite import BitgetEliteAdapter
from universal_bot.config import Settings


def _fake_adapter(monkeypatch, mode="one_way_mode"):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    calls = []

    monkeypatch.setattr(adapter, "_qty", lambda symbol, amount: "0.1000")
    monkeypatch.setattr(adapter, "_price", lambda symbol, price: f"{price:.1f}")
    monkeypatch.setattr(adapter, "_client_oid", lambda prefix="utb": f"{prefix}-1")
    monkeypatch.setattr(adapter, "_position_mode", lambda symbol: mode)

    def fake_request(method, path, *, params=None, body=None):
        calls.append((method, path, params, body))
        if path == "/api/v2/mix/order/place-order":
            return {"orderId": "order-1", "clientOid": body["clientOid"]}
        if path == "/api/v2/mix/order/detail":
            return {"state": "filled", "baseVolume": "0.1000", "priceAvg": "2500.0"}
        if path == "/api/v2/mix/order/place-plan-order":
            return {"orderId": f"plan-{len(calls)}", "clientOid": body["clientOid"]}
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    return adapter, calls


def test_elite_one_way_open_uses_classic_v2_and_separate_tpsl(monkeypatch):
    adapter, calls = _fake_adapter(monkeypatch, "one_way_mode")
    result = adapter.market_order(
        "ETH/USDT:USDT",
        "buy",
        0.1,
        tp_price=2600.0,
        sl_price=2400.0,
    )

    place = next(x for x in calls if x[1] == "/api/v2/mix/order/place-order")
    assert place[3]["symbol"] == "ETHUSDT"
    assert place[3]["side"] == "buy"
    assert place[3]["reduceOnly"] == "no"
    assert place[3]["marginMode"] == "crossed"
    assert "tradeSide" not in place[3]

    plans = [x for x in calls if x[1] == "/api/v2/mix/order/place-plan-order"]
    assert len(plans) == 2
    assert {p[3]["triggerPrice"] for p in plans} == {"2600.0", "2400.0"}
    assert all(p[3]["side"] == "sell" for p in plans)
    assert all(p[3]["reduceOnly"] == "yes" for p in plans)
    assert result["filled"] == 0.1
    assert result["average"] == 2500.0


def test_elite_hedge_open_and_close_follow_classic_trade_side(monkeypatch):
    adapter, calls = _fake_adapter(monkeypatch, "hedge_mode")
    adapter.market_order("ETH/USDT:USDT", "buy", 0.1)
    open_order = next(x for x in calls if x[1] == "/api/v2/mix/order/place-order")
    assert open_order[3]["side"] == "buy"
    assert open_order[3]["tradeSide"] == "open"
    assert "reduceOnly" not in open_order[3]

    calls.clear()
    adapter.market_order("ETH/USDT:USDT", "sell", 0.1, reduce_only=True)
    close_order = next(x for x in calls if x[1] == "/api/v2/mix/order/place-order")
    # Classic hedge mode closes LONG with side=buy + tradeSide=close.
    assert close_order[3]["side"] == "buy"
    assert close_order[3]["tradeSide"] == "close"
    assert "reduceOnly" not in close_order[3]


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
