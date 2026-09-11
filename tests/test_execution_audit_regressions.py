from copy import deepcopy

import pytest

from universal_bot.adapters.bitget_elite import AmbiguousOrderResult, BitgetEliteAdapter


def _ioc(monkeypatch, *, lag_reads=1, final_stale=False):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    sent = []
    reads = [0]
    def position(symbol):
        reads[0] += 1
        stale = not sent or reads[0] <= 1 + lag_reads
        if final_stale and reads[0] >= 3:
            stale = True
        qty = 0.0 if stale else sum(sent)
        return {"side": "LONG" if qty else "FLAT", "size": qty, "entry_price": 100000 if qty else 0}
    def child(symbol, side, amount, limit):
        sent.append(amount)
        return {"id": str(len(sent)), "clientOid": "utb-ioc-1", "filled": amount, "status": "filled"}
    monkeypatch.setattr(adapter, "position", position)
    monkeypatch.setattr(adapter, "_public_order_book", lambda s: {"asks": [(100000, 1)], "bids": [(100000, 1)]})
    monkeypatch.setattr(adapter, "_ioc_limit_child", child)
    monkeypatch.setattr(adapter, "replace_full_protection", lambda *a: {"ok": True})
    monkeypatch.setattr("universal_bot.adapters.bitget_elite.time.sleep", lambda _: None)
    return adapter, sent


@pytest.mark.parametrize("lag_reads", [1, 3, 6])
def test_confirmed_fill_is_not_reordered_when_position_lags(monkeypatch, lag_reads):
    adapter, sent = _ioc(monkeypatch, lag_reads=lag_reads)
    result = adapter.adaptive_ioc_entry("BTC/USDT:USDT", "buy", .1, reference_price=100000, tp_pct=1, sl_pct=1, child_pause_seconds=0)
    assert sent == [.1]
    assert result["filled"] == pytest.approx(.1)


def test_persistently_stale_position_stops_new_children(monkeypatch):
    adapter, sent = _ioc(monkeypatch, lag_reads=100)
    with pytest.raises(AmbiguousOrderResult):
        adapter.adaptive_ioc_entry("BTC/USDT:USDT", "buy", .1, reference_price=100000, tp_pct=1, sl_pct=1)
    assert sent == [.1]


def test_final_stale_position_does_not_report_a_filled_order_as_unfilled(monkeypatch):
    adapter, sent = _ioc(monkeypatch, lag_reads=0, final_stale=True)
    with pytest.raises(AmbiguousOrderResult):
        adapter.adaptive_ioc_entry("BTC/USDT:USDT", "buy", .1, reference_price=100000, tp_pct=1, sl_pct=1, child_pause_seconds=0)
    assert sent == [.1]


def _plans():
    return [{"orderId": leg, "clientOid": "utb-" + leg + "-1", "triggerPrice": price,
             "size": "0.1", "side": "sell", "triggerType": "fill_price", "orderType": "market", "reduceOnly": "YES"}
            for leg, price in [("tp", "101000"), ("sl", "99000")]]


@pytest.mark.parametrize("field,bad", [("triggerType", "mark_price"), ("orderType", "limit"), ("reduceOnly", "NO"),
                                      ("triggerType", None), ("orderType", None), ("reduceOnly", None)])
def test_protection_verification_rejects_wrong_or_missing_semantics(monkeypatch, field, bad):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    plans = _plans()
    expected = deepcopy(plans)
    plans[0][field] = bad
    monkeypatch.setattr(adapter, "_pending_plan_orders", lambda s: plans)
    monkeypatch.setattr("universal_bot.adapters.bitget_elite.time.sleep", lambda _: None)
    assert adapter.protection_status("BTC/USDT:USDT", expected_orders=expected)["ok"] is False


def test_complete_exchange_semantics_are_verified(monkeypatch):
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    monkeypatch.setattr(adapter, "_pending_plan_orders", lambda s: _plans())
    assert adapter.protection_status("BTC/USDT:USDT")["ok"] is True


def test_hedge_protection_requires_explicit_close_mode():
    order = _plans()[0]
    order.update(reduceOnly="NO", posMode="hedge_mode", tradeSide="close")
    assert BitgetEliteAdapter._safe_protection_semantics(order)
    order["tradeSide"] = "open"
    assert not BitgetEliteAdapter._safe_protection_semantics(order)
