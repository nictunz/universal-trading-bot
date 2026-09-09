from universal_bot.trade_history import TradeHistoryStore


def test_execution_claim_is_atomic_and_records_quality(tmp_path):
    store = TradeHistoryStore(tmp_path / "history.db")
    claim = {
        "mode": "LIVE",
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m",
        "signal_id": "BTC|15m|2026-09-09T09:00:00Z|LONG|ENTRY",
        "side": "LONG",
        "requested_qty": 0.12,
    }
    assert store.claim_execution_once(**claim) is True
    assert store.claim_execution_once(**claim) is False

    store.update_execution_claim(
        mode="LIVE",
        symbol=claim["symbol"],
        timeframe=claim["timeframe"],
        signal_id=claim["signal_id"],
        status="PROTECTED",
        filled_qty=0.1,
        avg_fill_price=100_010.0,
        slippage_percent=0.01,
        child_orders=2,
        metadata={"fill_ratio": 0.1 / 0.12, "protection_ok": True},
    )
    row = store.list_executions(symbol=claim["symbol"], mode="LIVE")[0]
    assert row["status"] == "PROTECTED"
    assert row["filled_qty"] == 0.1
    assert row["child_orders"] == 2
    assert row["metadata"]["protection_ok"] is True
