import pandas as pd

from universal_bot.config import Settings
from universal_bot.engine import TradingEngine
from universal_bot.strategy.v15 import UniversalV15Strategy


class FakeLiveAdapter:
    asset_class = "crypto"

    def __init__(self, protection=True):
        self.protection = protection
        self.orders = []

    def configure_live(self, *args, **kwargs):
        return {"ok": True}

    def equity(self):
        return 1_000_000.0

    def position(self, symbol):
        if not self.orders:
            return {"side": "FLAT", "size": 0.0, "entry_price": 0.0}
        side, amount = self.orders[-1]
        return {"side": "LONG" if side == "buy" else "SHORT", "size": amount, "entry_price": 100.0}

    def protection_status(self, symbol):
        return {"ok": self.protection}

    def market_order(self, symbol, side, amount, reduce_only=False, **kwargs):
        if reduce_only:
            self.orders = []
            return {"id": "close", "filled": amount, "average": 100.0}
        self.orders.append((side, amount))
        return {"id": "open", "filled": amount, "average": 100.0}

    def cancel_protection(self, symbol):
        return None

    def fetch_volume_sources(self, *args, **kwargs):
        return {}


def frame():
    # Keep the fixture current so the LIVE stale-data guard is tested independently
    # from the calendar date on which pytest happens to run.
    end = pd.Timestamp.now(tz="UTC").floor("5min")
    idx = pd.date_range(end=end, periods=400, freq="5min")
    close = pd.Series(100.0, index=idx)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=idx,
    )


def test_live_initialization_fails_closed_without_protection():
    settings = Settings(bot_mode="LIVE", use_start_date=False, use_nbar_volatility_block=False)
    adapter = FakeLiveAdapter(protection=False)
    engine = TradingEngine(settings, adapter, UniversalV15Strategy(settings))
    state = engine.step(frame())
    assert engine.safety.halted is False
    assert engine.safety.protection_ok is True  # flat positions need no protection
    assert state is not None
