from __future__ import annotations

import pandas as pd
import pytest

from universal_bot.adapters.bitget_elite import AmbiguousOrderResult
from universal_bot.config import Settings
from universal_bot.models import Position
from universal_bot.runtime_engine import TradingEngine
from universal_bot.strategy.v15 import UniversalV15Strategy


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_async(self, message: str) -> None:
        self.messages.append(message)


class RuntimeAdapter:
    asset_class = "crypto"

    def __init__(self, position: dict, protection: dict | None = None) -> None:
        self.exchange_position = dict(position)
        self.protection = protection or {"ok": True, "count": 2, "orders": []}
        self.protection_calls = 0
        self.cancel_calls = 0
        self.market_order_calls = 0
        self.close_fill: dict | None = None
        self.raise_ambiguous_close = False

    def ensure_leverage(self, *args, **kwargs):
        return {"ok": True}

    def configure_live(self, *args, **kwargs):
        return {"ok": True}

    def equity(self):
        return 1_000.0

    def position(self, symbol):
        return dict(self.exchange_position)

    def protection_status(self, symbol):
        self.protection_calls += 1
        return dict(self.protection)

    def cancel_protection(self, symbol):
        self.cancel_calls += 1

    def recent_close_fill(self, symbol, position_side, *, since_ms=None):
        return dict(self.close_fill) if self.close_fill else None

    def market_order(self, symbol, side, amount, reduce_only=False, **kwargs):
        self.market_order_calls += 1
        if reduce_only and self.raise_ambiguous_close:
            self.exchange_position = {"side": "FLAT", "size": 0.0, "entry_price": 0.0}
            raise AmbiguousOrderResult(
                "response lost",
                client_oid="utb-close-1",
                side=side,
                requested_qty=amount,
                reduce_only=True,
            )
        if reduce_only:
            self.exchange_position = {"side": "FLAT", "size": 0.0, "entry_price": 0.0}
            return {"id": "close-1", "filled": amount, "average": 110.0}
        raise AssertionError("entry is not expected in this fixture")

    def fetch_volume_sources(self, *args, **kwargs):
        return {}


def _settings() -> Settings:
    return Settings(
        bot_mode="LIVE",
        exchange="bitget",
        asset_class="crypto",
        bitget_execution_profile="elite",
        use_four_crypto_exchanges=False,
        use_start_date=False,
        discord_notifications_enabled=False,
    )


def _engine(tmp_path, monkeypatch, adapter: RuntimeAdapter) -> TradingEngine:
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = _settings()
    engine = TradingEngine(settings, adapter, UniversalV15Strategy(settings))
    engine.notifier = FakeNotifier()
    return engine


def _open_long(engine: TradingEngine) -> None:
    engine.position = Position(
        side="LONG",
        size=1.0,
        entry_price=100.0,
        tp=110.0,
        sl=90.0,
        entries=1,
    )
    engine.entry_notional = 100.0
    engine.position_entry_time = "2026-09-07T12:00:00+00:00"


def _frame() -> pd.DataFrame:
    end = pd.Timestamp.now(tz="UTC").floor("15min")
    index = pd.date_range(end=end, periods=240, freq="15min")
    close = pd.Series(100.0, index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )


def test_live_signal_claim_survives_engine_restart(tmp_path, monkeypatch):
    adapter = RuntimeAdapter({"side": "FLAT", "size": 0.0, "entry_price": 0.0})
    first = _engine(tmp_path, monkeypatch, adapter)
    first.current_bar_time = "2026-09-09T09:00:00+00:00"
    claim = first._claim_live_execution("LONG", 0.1, 100_000.0)
    assert claim is not None

    restarted = _engine(tmp_path, monkeypatch, adapter)
    restarted.current_bar_time = first.current_bar_time
    assert restarted._claim_live_execution("LONG", 0.1, 100_000.0) is None
    rows = restarted.trade_history.list_executions(symbol="BTC/USDT:USDT", mode="LIVE")
    assert len(rows) == 1
    assert rows[0]["status"] == "CLAIMED"


def test_flat_live_heartbeat_never_queries_protection_orders(tmp_path, monkeypatch):
    adapter = RuntimeAdapter({"side": "FLAT", "size": 0.0, "entry_price": 0.0})
    engine = _engine(tmp_path, monkeypatch, adapter)

    engine._initialize_live()
    for _ in range(3):
        engine._reconcile_live()

    assert engine.safety.halted is False
    assert engine.safety.protection_ok is True
    assert adapter.protection_calls == 0


def test_restart_restores_protection_and_live_step_tolerates_missing_prices(tmp_path, monkeypatch):
    protection = {
        "ok": True,
        "count": 2,
        "orders": [
            {"clientOid": "utb-tp-1", "triggerPrice": "110"},
            {"clientOid": "utb-sl-1", "triggerPrice": "90"},
        ],
    }
    adapter = RuntimeAdapter(
        {"side": "LONG", "size": 1.0, "entry_price": 100.0},
        protection,
    )
    engine = _engine(tmp_path, monkeypatch, adapter)

    engine._initialize_live()
    assert engine.position.tp == pytest.approx(110.0)
    assert engine.position.sl == pytest.approx(90.0)

    # Some Bitget pending-order responses temporarily omit trigger prices.
    # LIVE must continue relying on verified exchange protection without doing
    # Python comparisons against None.
    engine.position.tp = None
    engine.position.sl = None
    adapter.protection = {"ok": True, "count": 2, "orders": [{}, {}]}
    state = engine.step(_frame())

    assert state is not None
    assert engine.safety.halted is False


def test_exchange_tpsl_fill_syncs_state_journal_and_one_notification(tmp_path, monkeypatch):
    adapter = RuntimeAdapter({"side": "FLAT", "size": 0.0, "entry_price": 0.0})
    adapter.close_fill = {
        "price": 110.0,
        "qty": 1.0,
        "fee": 0.1,
        "realized_pnl": 10.0,
        "time_ms": 1_788_783_600_000,
        "order_id": "tp-order-1",
        "client_oid": "utb-tp-1",
        "source": "bitget-classic-v2-fills",
        "raw": [{"delegateType": "stop_profit_market", "clientOid": "utb-tp-1"}],
    }
    engine = _engine(tmp_path, monkeypatch, adapter)
    _open_long(engine)
    engine._live_initialized = True
    events = []
    engine._record_runtime_event = events.append

    engine._reconcile_live()

    assert engine.position.flat
    assert engine.safety.halted is False
    assert engine.closed_trades == 1
    assert engine.trade_log[0]["reason"] == "TP"
    assert engine.trade_log[0]["exit_price"] == pytest.approx(110.0)
    assert engine.trade_log[0]["pnl"] == pytest.approx(9.9)
    assert engine.trade_log[0]["metadata"]["fill_exact"] is True
    assert len(engine.notifier.messages) == 1
    assert len(events) == 1
    assert adapter.protection_calls == 0
    assert adapter.cancel_calls == 1


def test_exchange_close_is_applied_to_reentry_cooldown_in_same_bar(tmp_path, monkeypatch):
    adapter = RuntimeAdapter({"side": "FLAT", "size": 0.0, "entry_price": 0.0})
    adapter.close_fill = {
        "price": 110.0,
        "qty": 1.0,
        "fee": 0.0,
        "realized_pnl": 10.0,
        "time_ms": 1_788_783_600_000,
        "source": "bitget-classic-v2-fills",
        "raw": [{"delegateType": "stop_profit_market"}],
    }
    engine = _engine(tmp_path, monkeypatch, adapter)
    _open_long(engine)
    engine._live_initialized = True

    state = engine.step(_frame())

    assert engine.position.flat
    assert state.signal.diagnostics["bars_since_exit"] == 0
    assert state.signal.diagnostics["cooldown_ok"] is False
    assert adapter.market_order_calls == 0


def test_normal_runtime_close_emits_exactly_one_exit_notification(tmp_path, monkeypatch):
    adapter = RuntimeAdapter({"side": "LONG", "size": 1.0, "entry_price": 100.0})
    engine = _engine(tmp_path, monkeypatch, adapter)
    _open_long(engine)
    events = []
    engine._record_runtime_event = events.append

    engine._close(110.0, "TP")

    assert engine.position.flat
    assert engine.closed_trades == 1
    assert len(engine.notifier.messages) == 1
    assert len(events) == 1
    assert adapter.market_order_calls == 1
    assert adapter.cancel_calls == 1


def test_ambiguous_emergency_close_is_not_resent_and_is_reconciled(tmp_path, monkeypatch):
    adapter = RuntimeAdapter({"side": "LONG", "size": 1.0, "entry_price": 100.0})
    adapter.raise_ambiguous_close = True
    adapter.close_fill = {
        "price": 99.0,
        "qty": 1.0,
        "fee": 0.05,
        "realized_pnl": -1.0,
        "time_ms": 1_788_783_600_000,
        "order_id": "emergency-close-1",
        "client_oid": "utb-close-1",
        "source": "bitget-classic-v2-fills",
        "raw": [{"clientOid": "utb-close-1", "delegateType": "market"}],
    }
    engine = _engine(tmp_path, monkeypatch, adapter)
    _open_long(engine)

    engine._flatten_full_position_after_protection_failure("LONG", 1.0)

    assert adapter.market_order_calls == 1
    assert engine.position.flat
    assert engine.safety.halted is False
    assert engine.closed_trades == 1
    assert len(engine.notifier.messages) == 1


def test_missing_fill_history_does_not_invent_tp_or_sl_reason(tmp_path, monkeypatch):
    adapter = RuntimeAdapter({"side": "FLAT", "size": 0.0, "entry_price": 0.0})
    engine = _engine(tmp_path, monkeypatch, adapter)
    _open_long(engine)

    assert engine._handle_external_flat(adapter.exchange_position) is True
    assert engine.trade_log[0]["reason"] == "EXCHANGE_EXIT"
    assert engine.trade_log[0]["metadata"]["fill_exact"] is False
