from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import math
import pandas as pd
import numpy as np

@dataclass
class V15Signal:
    side: Optional[str]
    reason: str
    volume_ratio: float = math.nan
    one_bar_volatility: float = math.nan
    nbar_range: float = math.nan
    tp_percent: float = math.nan
    sl_percent: float = math.nan
    rsi: float = math.nan
    adx: float = math.nan

class UniversalV15Strategy:
    """TradingView v15 logic reproduced locally. No TradingView dependency."""
    def __init__(self, settings):
        self.s = settings

    @staticmethod
    def _rsi(close: pd.Series, length: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
        avg_loss = loss.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _adx(df: pd.DataFrame, length: int) -> pd.Series:
        high, low, close = df.high, df.low, df.close
        up = high.diff()
        down = -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        tr = pd.concat([(high-low), (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
        plus_di = 100 * plus_dm.ewm(alpha=1/length, adjust=False, min_periods=length).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1/length, adjust=False, min_periods=length).mean() / atr
        dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
        return dx.ewm(alpha=1/length, adjust=False, min_periods=length).mean()

    def evaluate(self, df: pd.DataFrame, volume_ratio: Optional[float] = None, now=None) -> V15Signal:
        if len(df) < max(self.s.volume_lookback, self.s.volatility_bars, self.s.nbar_volatility_bars, self.s.rsi_length, self.s.adx_length) + 2:
            return V15Signal(None, "INSUFFICIENT_DATA")
        x = df.iloc[-1]
        close, open_, high, low = float(x.close), float(x.open), float(x.high), float(x.low)
        vr = float(volume_ratio) if volume_ratio is not None else float(x.volume / df.volume.rolling(self.s.volume_lookback).mean().iloc[-1])
        one = abs(close-open_) / open_ * 100 if open_ else 0
        hi = df.high.rolling(self.s.volatility_bars).max().iloc[-1]
        lo = df.low.rolling(self.s.volatility_bars).min().iloc[-1]
        nrange = (hi-lo)/lo*100 if lo > 0 else 0
        raw_tp, raw_sl = nrange*self.s.tp_vol_multiplier, nrange*self.s.sl_vol_multiplier
        tp = max(self.s.min_tp_percent, min(self.s.max_tp_percent, raw_tp))
        sl = max(self.s.min_sl_percent, min(self.s.max_sl_percent, raw_sl))
        bhi = df.high.rolling(self.s.nbar_volatility_bars).max().iloc[-1]
        blo = df.low.rolling(self.s.nbar_volatility_bars).min().iloc[-1]
        block_range = (bhi-blo)/blo*100 if blo > 0 else 0
        rsi = float(self._rsi(df.close, self.s.rsi_length).iloc[-1])
        adx = float(self._adx(df, self.s.adx_length).iloc[-1])
        volume_ok = math.isfinite(vr) and vr >= self.s.volume_break_multiplier
        one_ok = self.s.min_one_bar_vol <= one <= self.s.max_one_bar_vol
        n_ok = (not self.s.use_nbar_volatility_block) or block_range <= self.s.max_nbar_volatility
        adx_ok = (not self.s.use_adx_filter) or (self.s.adx_min <= adx <= self.s.adx_max)
        hour = getattr(now, 'hour', None) if now is not None else None
        excluded = {h.strip() for h in self.s.excluded_hours.split(',') if h.strip()}
        time_ok = (not self.s.use_start_date or (now is not None and now >= self.s.start_date)) and (not self.s.block_weekend or (now is not None and now.weekday() < 5)) and (hour is None or f'{hour:02d}' not in excluded)
        base = volume_ok and one_ok and n_ok and adx_ok and time_ok
        oversold = self.s.rsi_oversold_min <= rsi <= self.s.rsi_oversold_max
        overbought = self.s.rsi_overbought_min <= rsi <= self.s.rsi_overbought_max
        long_ok = (not self.s.use_rsi_filter or oversold) and close < open_ and self.s.allow_long
        short_ok = (not self.s.use_rsi_filter or overbought) and close > open_ and self.s.allow_short
        if base and long_ok:
            return V15Signal('LONG', 'V15 LONG: volume + bearish candle + RSI oversold', vr, one, nrange, tp, sl, rsi, adx)
        if base and short_ok:
            return V15Signal('SHORT', 'V15 SHORT: volume + bullish candle + RSI overbought', vr, one, nrange, tp, sl, rsi, adx)
        reasons=[]
        if not volume_ok: reasons.append('volume')
        if not one_ok: reasons.append('1bar_volatility')
        if not n_ok: reasons.append('nbar_block')
        if not adx_ok: reasons.append('adx')
        if not time_ok: reasons.append('time')
        if not (long_ok or short_ok): reasons.append('rsi/candle/direction')
        return V15Signal(None, 'WAIT: ' + ', '.join(reasons), vr, one, nrange, tp, sl, rsi, adx)
