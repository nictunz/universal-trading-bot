"""Order-free, confirmed-bar signal boundary for the selected priority profiles.

Explicit settings isolate this evaluator from .env and dashboard edits. Outputs
are signal candidates, not fills or a backtest equity curve.
"""
from dataclasses import dataclass
import hashlib
import json
import math

import pandas as pd

from universal_bot.config import Settings
from universal_bot.models import Position
from universal_bot.paper import normalize_exchange_volume
from universal_bot.strategy.v15 import UniversalV15Strategy

EXCHANGES = frozenset(('binance', 'bitget', 'okx', 'bybit'))
COMMON = dict(use_four_crypto_exchanges=True, use_adx_filter=False, adx_length=7,
    adx_min=11.6, adx_max=80.5, use_rsi_filter=True, allow_long=True, allow_short=True,
    max_pyramiding=1, block_weekend=False, excluded_hours='', use_start_date=False,
    first_entry_consecutive_candles=1, apply_consecutive_candles_to_all_entries=False,
    adaptive_regime_enabled=False, use_nbar_volatility_block=True, nbar_volatility_bars=200)
PROFILES = {
    '5m': dict(volume_lookback=30, volume_break_multiplier=10.8,
        min_one_bar_vol=0.0, max_one_bar_vol=2.1, volatility_bars=144,
        tp_vol_multiplier=9.2, sl_vol_multiplier=0.6, min_tp_percent=0.7,
        max_tp_percent=3.1, min_sl_percent=0.8, max_sl_percent=1.1,
        max_nbar_volatility=5.2, rsi_length=11, rsi_oversold_min=20.6,
        rsi_oversold_max=36.5, rsi_overbought_min=75.1, rsi_overbought_max=80.6,
        cooldown_bars=8, reentry_bars=9, order_percent_of_equity=955.0,
        live_entry_multiplier=9.55),
    '15m': dict(volume_lookback=40, volume_break_multiplier=6.4,
        min_one_bar_vol=0.1, max_one_bar_vol=3.6, volatility_bars=36,
        tp_vol_multiplier=3.8, sl_vol_multiplier=1.0, min_tp_percent=0.3,
        max_tp_percent=2.1, min_sl_percent=0.3, max_sl_percent=1.9,
        max_nbar_volatility=6.3, rsi_length=10, rsi_oversold_min=20.0,
        rsi_oversold_max=42.0, rsi_overbought_min=65.6, rsi_overbought_max=74.7,
        cooldown_bars=3, reentry_bars=5, order_percent_of_equity=500.0,
        live_entry_multiplier=5.0),
}


def profile_settings(tf):
    # Pass every strategy field explicitly so shell environment cannot alter it.
    return Settings(_env_file=None, **COMMON, **PROFILES[tf], timeframe=tf,
        symbol='BTC/USDT:USDT', bot_mode='PAPER', discord_notifications_enabled=False)


def profile_hash():
    return hashlib.sha256(json.dumps({'common': COMMON, 'profiles': PROFILES},
        sort_keys=True).encode()).hexdigest()


def utc(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError('timezone required')
    return ts.tz_convert('UTC')


@dataclass(frozen=True)
class Candidate:
    owner: str
    opened_at: pd.Timestamp
    side: str
    price: float
    tp_percent: float
    sl_percent: float
    multiplier: float


class DataUnavailable(ValueError):
    pass


class DualTimeframeSignals:
    def __init__(self):
        self.settings = {tf: profile_settings(tf) for tf in PROFILES}
        self.strategies = {tf: UniversalV15Strategy(s) for tf, s in self.settings.items()}

    @staticmethod
    def due(boundary):
        b = utc(boundary)
        if b.minute % 5 or b.second or b.microsecond or b.nanosecond:
            raise ValueError('expected 5m close boundary')
        return ('5m', '15m') if b.minute % 15 == 0 else ('5m',)

    def prepare(self, tf, frame, sources, boundary):
        s = self.settings[tf]
        delta = pd.Timedelta(tf)
        count = max(200, s.volume_lookback, s.volatility_bars, s.rsi_length * 10)
        end = boundary - delta
        required = pd.date_range(end=end, periods=count, freq=delta)
        if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
            raise DataUnavailable(tf + ': UTC-indexed OHLCV required')
        if frame.index.has_duplicates:
            raise DataUnavailable(tf + ': duplicate OHLCV')
        if not {'open', 'high', 'low', 'close', 'volume'}.issubset(frame.columns):
            raise DataUnavailable(tf + ': OHLCV columns missing')
        # Remove every unconfirmed/future row, not only the final row.
        closed = frame.loc[(frame.index <= end)].sort_index()
        if not required.isin(closed.index).all():
            raise DataUnavailable(tf + ': missing completed OHLCV bars')
        numeric = closed[['open', 'high', 'low', 'close', 'volume']].astype(float)
        if not numeric.apply(lambda column: column.map(math.isfinite)).all().all():
            raise DataUnavailable(tf + ': nonfinite OHLCV')
        if (numeric[['open', 'high', 'low', 'close']] <= 0).any().any() or (numeric.volume < 0).any():
            raise DataUnavailable(tf + ': invalid price or volume')
        if ((numeric.high < numeric[['open', 'close', 'low']].max(axis=1)) |
                (numeric.low > numeric[['open', 'close', 'high']].min(axis=1))).any():
            raise DataUnavailable(tf + ': inconsistent OHLC')
        if set(sources) != EXCHANGES:
            raise DataUnavailable(tf + ': all four volume sources required')
        volumes = {}
        for exchange, series in sources.items():
            if not isinstance(series.index, pd.DatetimeIndex) or series.index.tz is None or series.index.has_duplicates:
                raise DataUnavailable(tf + ': invalid volume index: ' + exchange)
            v = series.reindex(required).astype(float)
            if not v.map(math.isfinite).all() or (v < 0).any():
                raise DataUnavailable(tf + ': missing/invalid volume: ' + exchange)
            volumes[exchange] = v
        ratio = normalize_exchange_volume(volumes, s.volume_lookback, required_sources=4)
        if not math.isfinite(float(ratio.iloc[-1])):
            raise DataUnavailable(tf + ': undefined volume SMA ratio')
        return closed, ratio.reindex(closed.index)

    def evaluate(self, frames, volumes, boundary, now, history=None):
        b, now = utc(boundary), utc(now)
        due = self.due(b)
        if now < b or now - b > pd.Timedelta(seconds=30):
            raise DataUnavailable('unconfirmed or stale boundary')
        prepared = {}
        # Validate BOTH due timeframes before admitting either signal.
        for tf in due:
            if tf not in frames or tf not in volumes:
                raise DataUnavailable(tf + ': input missing')
            prepared[tf] = self.prepare(tf, frames[tf], volumes[tf], b)
        candidates, diagnostics = [], {}
        history = history or {}
        for tf in due:
            s = self.settings[tf]
            bars = {}
            for key in ('entry', 'exit'):
                last = history.get(tf, {}).get(key)
                if last is None:
                    bars[key] = None
                else:
                    elapsed = b - utc(last)
                    if elapsed < pd.Timedelta(0):
                        raise DataUnavailable('history is ahead of boundary')
                    bars[key] = int(elapsed // pd.Timedelta(tf))
            frame, ratio = prepared[tf]
            result = self.strategies[tf].evaluate(frame, s.symbol, tf, Position(),
                bars['entry'], bars['exit'], ratio)
            diagnostics[tf] = result.signal.reason
            if result.signal.side:
                v = result.signal.diagnostics
                candidates.append(Candidate(tf, b-pd.Timedelta(tf), result.signal.side,
                    float(frame.close.iloc[-1]), float(v['final_tp_percent']),
                    float(v['final_sl_percent']), s.live_entry_multiplier))
        return candidates, diagnostics
