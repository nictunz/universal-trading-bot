from __future__ import annotations

import pytest

from universal_bot.adapters.bitget_elite import AmbiguousOrderResult, BitgetEliteAdapter
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


def test_ambiguous_elite_order_recovers_same_client_oid_without_reposting(monkeypatch):
    adapter, calls = _fake_adapter(monkeypatch, "one_way_mode")
    original_request = adapter._request
    place_attempts = 0

    def ambiguous_once(method, path, *, params=None, body=None):
        nonlocal place_attempts
        if path == "/api/v2/mix/order/place-order":
            place_attempts += 1
            calls.append((method, path, params, body))
            raise RuntimeError("Bitget Elite API error HTTP 400 40010: request timed out")
        if path == "/api/v2/mix/order/detail":
            calls.append((method, path, params, body))
            assert params["clientOid"] == "utb-elite-1"
            assert params["orderId"] is None
            return {
                "orderId": "recovered-order",
                "clientOid": params["clientOid"],
                "state": "filled",
                "baseVolume": "0.1000",
                "priceAvg": "2500.0",
            }
        return original_request(method, path, params=params, body=body)

    monkeypatch.setattr(adapter, "_request", ambiguous_once)
    result = adapter.market_order(
        "ETH/USDT:USDT",
        "buy",
        0.1,
        tp_price=2600.0,
        sl_price=2400.0,
    )

    assert place_attempts == 1
    assert result["clientOid"] == "utb-elite-1"
    assert result["recovered_by_client_oid"] is True
    assert len([call for call in calls if call[1] == "/api/v2/mix/order/place-plan-order"]) == 2


def test_unresolved_ambiguous_elite_order_fails_without_duplicate_post(monkeypatch):
    adapter, calls = _fake_adapter(monkeypatch, "one_way_mode")
    ticks = iter((0.0, 1.0))
    monkeypatch.setattr("universal_bot.adapters.bitget_elite.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("universal_bot.adapters.bitget_elite.time.sleep", lambda _: None)

    def unresolved(method, path, *, params=None, body=None):
        calls.append((method, path, params, body))
        if path == "/api/v2/mix/order/place-order":
            raise RuntimeError("Bitget Elite API error HTTP 400 40010: request timed out")
        if path == "/api/v2/mix/order/detail":
            return {}
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", unresolved)
    with pytest.raises(AmbiguousOrderResult) as caught:
        adapter.market_order("ETH/USDT:USDT", "buy", 0.1)

    assert caught.value.client_oid == "utb-elite-1"
    assert len([call for call in calls if call[1] == "/api/v2/mix/order/place-order"]) == 1


def test_close_fill_summary_prefers_fee_detail_over_duplicate_aggregate():
    summary = BitgetEliteAdapter._summarize_close_fills(
        [
            {
                "symbol": "BTCUSDT",
                "orderId": "close-1",
                "clientOid": "utb-tp-1",
                "side": "sell",
                "createdTime": "2000",
                "sizeQty": "0.4",
                "price": "110",
                "fee": "0.08",
                "feeDetail": [{"fee": "-0.04"}],
                "profit": "4",
            },
            {
                "symbol": "BTCUSDT",
                "orderId": "close-1",
                "clientOid": "utb-tp-1",
                "side": "sell",
                "createdTime": "2001",
                "sizeQty": "0.6",
                "price": "112",
                "fee": "0.12",
                "feeDetail": [{"fee": "-0.06"}],
                "profit": "7.2",
            },
        ],
        symbol_id="BTCUSDT",
        position_side="LONG",
        since_ms=1000,
        source="test",
    )

    assert summary is not None
    assert summary["qty"] == pytest.approx(1.0)
    assert summary["price"] == pytest.approx(111.2)
    assert summary["fee"] == pytest.approx(0.1)
    assert summary["realized_pnl"] == pytest.approx(11.2)


def test_ioc_entry_child_uses_limit_ioc_and_never_market(monkeypatch):
    adapter, calls = _fake_adapter(monkeypatch, "one_way_mode")
    result = adapter._ioc_limit_child(
        "BTC/USDT:USDT",
        "buy",
        0.1,
        100_030.0,
    )

    place = next(x for x in calls if x[1] == "/api/v2/mix/order/place-order")
    assert place[3]["orderType"] == "limit"
    assert place[3]["force"] == "ioc"
    assert place[3]["price"] == "100030.0"
    assert place[3]["reduceOnly"] == "no"
    assert result["filled"] == pytest.approx(0.1)


def test_adaptive_ioc_accepts_price_improvement_and_protects_partial_fill(monkeypatch):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    positions = iter(
        [
            {"side": "FLAT", "size": 0.0, "entry_price": 0.0},
            {"side": "LONG", "size": 0.1, "entry_price": 99_990.0},
            {"side": "LONG", "size": 0.1, "entry_price": 99_990.0},
        ]
    )
    protections = []
    monkeypatch.setattr(adapter, "position", lambda symbol: next(positions))
    monkeypatch.setattr(
        adapter,
        "_public_order_book",
        lambda symbol: {"asks": [(99_990.0, 1.0)], "bids": [(99_980.0, 1.0)]},
    )
    monkeypatch.setattr(
        adapter,
        "_ioc_limit_child",
        lambda symbol, side, amount, limit_price: {
            "id": "ioc-1",
            "clientOid": "utb-ioc-1",
            "filled": amount,
            "average": 99_990.0,
            "status": "filled",
        },
    )

    def protect(symbol, side, qty, tp, sl):
        protections.append((symbol, side, qty, tp, sl))
        return {"ok": True}

    monkeypatch.setattr(adapter, "replace_full_protection", protect)
    result = adapter.adaptive_ioc_entry(
        "BTC/USDT:USDT",
        "buy",
        0.1,
        reference_price=100_000.0,
        tp_pct=1.0,
        sl_pct=1.0,
        max_adverse_slippage_percent=0.03,
        max_child_orders=5,
        execution_window_seconds=3.0,
        depth_participation=0.2,
        child_pause_seconds=0.0,
    )

    assert result["filled"] == pytest.approx(0.1)
    assert result["average"] == pytest.approx(99_990.0)
    assert result["limit_price"] == pytest.approx(100_030.0)
    assert result["status"] == "filled"
    assert result["child_order_count"] == 1
    assert result["elapsed_seconds"] >= 0
    assert result["protected_qty"] == pytest.approx(0.1)
    assert result["protection_updates"][0]["ok"] is True
    assert protections[0][1] == "long"
    assert protections[0][2] == pytest.approx(0.1)
    # Protection prices stay anchored to the signal/reference price even when
    # the actual IOC fill receives price improvement.
    assert protections[0][3] == pytest.approx(101_000.0)
    assert protections[0][4] == pytest.approx(99_000.0)


def test_cancel_protection_never_cancels_manual_plan(monkeypatch):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    pending = [
        {"orderId": "tp-1", "clientOid": "utb-tp-1", "planType": "normal_plan"},
        {"orderId": "sl-1", "clientOid": "utb-sl-1", "planType": "normal_plan"},
        {"orderId": "manual-1", "clientOid": "phone-order", "planType": "normal_plan"},
    ]
    cancelled = []
    monkeypatch.setattr(
        adapter,
        "_pending_plan_orders",
        lambda symbol: pending if not cancelled else [pending[-1]],
    )

    def request(method, path, *, params=None, body=None):
        cancelled.append(body["orderId"])
        return {}

    monkeypatch.setattr(adapter, "_request", request)
    result = adapter.cancel_protection("BTC/USDT:USDT")

    assert result["ok"] is True
    assert cancelled == ["tp-1", "sl-1"]


def test_replace_protection_places_and_verifies_new_pair_before_old_cancel(monkeypatch):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    old = [
        {"orderId": "old-tp", "clientOid": "utb-tp-old", "triggerPrice": "101", "planType": "normal_plan"},
        {"orderId": "old-sl", "clientOid": "utb-sl-old", "triggerPrice": "99", "planType": "normal_plan"},
    ]
    new = [
        {"orderId": "new-tp", "clientOid": "utb-tp-new", "triggerPrice": "102", "size": "1", "side": "sell", "leg": "tp", "planType": "normal_plan"},
        {"orderId": "new-sl", "clientOid": "utb-sl-new", "triggerPrice": "98", "size": "1", "side": "sell", "leg": "sl", "planType": "normal_plan"},
    ]
    # Bitget may briefly omit clientOid/leg in the pending response. The exact
    # returned orderId still proves ownership of this just-created pair.
    for order in new:
        order.update(triggerType="fill_price", orderType="market", reduceOnly="YES")
    pending_new = [
        {k: v for k, v in order.items() if k not in {"clientOid", "leg"}}
        for order in new
    ]
    snapshots = iter([old, old + pending_new, pending_new])
    cancelled = []
    monkeypatch.setattr(adapter, "_pending_plan_orders", lambda symbol: next(snapshots))
    monkeypatch.setattr(adapter, "_qty", lambda symbol, qty: "1")
    monkeypatch.setattr(adapter, "_place_protection", lambda *args: new)

    def cancel(symbol, orders):
        cancelled.extend(order["orderId"] for order in orders)
        return []

    monkeypatch.setattr(adapter, "_cancel_plan_orders", cancel)
    result = adapter.replace_full_protection("BTC/USDT:USDT", "long", 1.0, 102.0, 98.0)

    assert result["ok"] is True
    assert cancelled == ["old-tp", "old-sl"]
    assert adapter._bot_protection_orders(pending_new) == pending_new


def test_private_get_retries_429_but_post_is_never_replayed(monkeypatch):
    class Response:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload
            self.headers = {}

        def json(self):
            return self._payload

    class Session:
        def __init__(self, responses):
            self.responses = iter(responses)
            self.calls = 0

        def request(self, *args, **kwargs):
            self.calls += 1
            return next(self.responses)

    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    adapter.timeout = 1.0
    monkeypatch.setattr(adapter, "_signed_headers", lambda *args: {})
    monkeypatch.setattr(adapter, "_acquire_api_budget", lambda *args: None)
    monkeypatch.setattr("universal_bot.adapters.bitget_elite.time.sleep", lambda _: None)
    monkeypatch.setattr("universal_bot.adapters.bitget_elite.random.uniform", lambda *args: 0.0)

    adapter._session = Session([
        Response(429, {"code": "429", "msg": "too many"}),
        Response(200, {"code": "00000", "data": {"ok": True}}),
    ])
    assert adapter._request("GET", "/private") == {"ok": True}
    assert adapter._session.calls == 2

    adapter._session = Session([Response(429, {"code": "429", "msg": "too many"})])
    with pytest.raises(RuntimeError, match="HTTP 429"):
        adapter._request("POST", "/order", body={"clientOid": "same-id"})
    assert adapter._session.calls == 1
