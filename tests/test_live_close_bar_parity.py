from types import SimpleNamespace

import pandas as pd
import pytest

import universal_bot.engine as module
from universal_bot.config import Settings
from universal_bot.models import Position
from universal_bot.strategy.v15 import UniversalV15Strategy


class SimulatedEngine(module.TradingEngine):
    def _initialize_live(self):
        pass

    def _reconcile_live(self):
        pass

    def _open(self, side, price, tp_pct, sl_pct):
        self.opens += 1
        self.position = Position(side=side, size=1, entry_price=price, entries=1)
        self.last_entry_bar = self.bar_number


def make_engine(monkeypatch):
    monkeypatch.setattr(module, "TradeHistoryStore", lambda: SimpleNamespace(record_trade=lambda **k: None))
    settings = Settings(bot_mode="LIVE", timeframe="15m", reentry_bars=7,
                        cooldown_bars=3, use_start_date=False,
                        discord_notifications_enabled=False)
    engine = SimulatedEngine(settings, SimpleNamespace(equity=lambda: 1000), UniversalV15Strategy(settings))
    engine.opens = 0
    engine.bar_number = 100
    engine.last_entry_bar = 90
    engine.position = Position(side="LONG", size=1, entry_price=100, tp=102, sl=98, entries=1)
    engine.entry_notional = 100
    return engine


def frame(stamp):
    return pd.DataFrame({"open": 101., "high": 102., "low": 99., "close": 100., "volume": 1.},
                        index=pd.date_range(end=stamp, periods=400, freq="15min"))


FEATURES = {"volume_ratio": 10, "n_range": 1, "block_range": 2, "adx": 20, "rsi": 30}


@pytest.mark.parametrize("heartbeat", [True, False])
def test_verified_fill_on_signal_candle_can_reenter_once(monkeypatch, heartbeat):
    e = make_engine(monkeypatch)
    ts = pd.Timestamp.now(tz="UTC").floor("15min") - pd.Timedelta(minutes=15)
    close = lambda: e._finalize_closed_trade(102, "TP", exit_time=(ts + pd.Timedelta(minutes=5)).isoformat(), metadata={"fill_exact": True})
    if heartbeat:
        close()  # Exchange heartbeat sees it before this candle is processed.
    else:
        e._reconcile_live = close
    e.step(frame(ts), FEATURES)
    assert e.opens == 1
    assert e.last_exit_bar == 101
    e._reconcile_live = lambda: None
    e.step(frame(ts), FEATURES)
    assert e.opens == 1


@pytest.mark.parametrize("exact,reason,offset", [(False,"TP",0),(True,"EMERGENCY",0),(True,"TP",-15)])
def test_unknown_emergency_or_old_exit_cannot_bypass_wait(monkeypatch, exact, reason, offset):
    e = make_engine(monkeypatch)
    ts = pd.Timestamp.now(tz="UTC").floor("15min") - pd.Timedelta(minutes=15)
    e._finalize_closed_trade(102, reason, exit_time=(ts + pd.Timedelta(minutes=offset+5)).isoformat(), metadata={"fill_exact": exact})
    e.step(frame(ts), FEATURES)
    assert e.opens == 0


def test_previous_exit_cooldown_still_blocks_close_bar(monkeypatch):
    e = make_engine(monkeypatch)
    e.last_exit_bar = 98
    ts = pd.Timestamp.now(tz="UTC").floor("15min") - pd.Timedelta(minutes=15)
    e._finalize_closed_trade(102, "TP", exit_time=ts.isoformat(), metadata={"fill_exact": True})
    e.step(frame(ts), FEATURES)
    assert e.opens == 0


def test_next_candles_wait_seven_bars(monkeypatch):
    e = make_engine(monkeypatch)
    ts = pd.Timestamp.now(tz="UTC").floor("15min") - pd.Timedelta(minutes=120)
    e.settings.stale_data_seconds = 20000
    e._finalize_closed_trade(102, "TP", exit_time=ts.isoformat(), metadata={"fill_exact": True})
    # No volume signal on the exit bar; the exception is not carried forward.
    e.step(frame(ts), {**FEATURES,"volume_ratio":0})
    for k in range(1,7):
        e.step(frame(ts+pd.Timedelta(minutes=15*k)), FEATURES)
        assert e.opens == 0
    e.step(frame(ts+pd.Timedelta(minutes=105)), FEATURES)
    assert e.opens == 1
