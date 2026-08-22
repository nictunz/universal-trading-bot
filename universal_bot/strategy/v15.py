from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import pandas as pd

from universal_bot.config import Settings
from universal_bot.indicators import dmi_adx, rolling_range_percent, rsi, sma
from universal_bot.models import Position, Signal, StrategyState


@dataclass
class V15Result:
    signal: Signal
    state: StrategyState


class UniversalV15Strategy:
    """TradingView-independent implementation of the supplied Universal v15 logic."""

    name = "Volume Strategy FINAL Universal v15"

    def __init__(self, settings: Settings):
        self.s = settings

    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        position: Position | None = None,
        bars_since_entry: int | None = None,
        bars_since_exit: int | None = None,
        normalized_volume_ratio: pd.Series | None = None,
    ) -> V15Result:
        if len(df) < max(self.s.volume_lookback, self.s.volatility_bars, self.s.nbar_volatility_bars, self.s.adx_length * 2, self.s.rsi_length + 2):
            sig = Signal(None, "NOT_ENOUGH_DATA", False, {})
            return V15Result(sig, StrategyState(symbol=symbol, timeframe=timeframe, signal=sig))

        d = df.copy().sort_index()
        vol_avg = sma(d.volume, self.s.volume_lookback)
        chart_ratio = d.volume / vol_avg.replace(0, pd.NA)
        ratio = normalized_volume_ratio if normalized_volume_ratio is not None else chart_ratio
        volume_ratio = float(ratio.iloc[-1]) if pd.notna(ratio.iloc[-1]) else float("nan")
        volume_break = pd.notna(ratio.iloc[-1]) and volume_ratio >= self.s.volume_break_multiplier

        one_bar = abs(float(d.close.iloc[-1]) - float(d.open.iloc[-1])) / float(d.open.iloc[-1]) * 100 if d.open.iloc[-1] else 0.0
        one_bar_ok = self.s.min_one_bar_vol <= one_bar <= self.s.max_one_bar_vol

        n_range_series = rolling_range_percent(d.high, d.low, self.s.volatility_bars)
        n_range = float(n_range_series.iloc[-1]) if pd.notna(n_range_series.iloc[-1]) else 0.0
        raw_tp = n_range * self.s.tp_vol_multiplier
        raw_sl = n_range * self.s.sl_vol_multiplier
        final_tp = max(self.s.min_tp_percent, min(self.s.max_tp_percent, raw_tp))
        final_sl = max(self.s.min_sl_percent, min(self.s.max_sl_percent, raw_sl))

        block_range_series = rolling_range_percent(d.high, d.low, self.s.nbar_volatility_bars)
        block_range = float(block_range_series.iloc[-1]) if pd.notna(block_range_series.iloc[-1]) else 0.0
        nbar_ok = (not self.s.use_nbar_volatility_block) or block_range <= self.s.max_nbar_volatility

        _, _, adx_series = dmi_adx(d.high, d.low, d.close, self.s.adx_length)
        adx_value = float(adx_series.iloc[-1]) if pd.notna(adx_series.iloc[-1]) else 0.0
        adx_ok = (not self.s.use_adx_filter) or self.s.adx_min <= adx_value <= self.s.adx_max

        rsi_series = rsi(d.close, self.s.rsi_length)
        rsi_value = float(rsi_series.iloc[-1])
        oversold = self.s.rsi_oversold_min <= rsi_value <= self.s.rsi_oversold_max
        overbought = self.s.rsi_overbought_min <= rsi_value <= self.s.rsi_overbought_max
        rsi_long_ok = (not self.s.use_rsi_filter) or oversold
        rsi_short_ok = (not self.s.use_rsi_filter) or overbought

        ts = d.index[-1]
        if isinstance(ts, pd.Timestamp):
            current_time = ts.to_pydatetime()
        else:
            current_time = ts if isinstance(ts, datetime) else datetime.utcnow()
        start_ok = (not self.s.use_start_date) or current_time >= self.s.start_date
        weekend_ok = (not self.s.block_weekend) or current_time.weekday() < 5
        excluded = {x.strip() for x in self.s.excluded_hours.split(",") if x.strip()}
        hour_ok = current_time.strftime("%H") not in excluded
        time_ok = start_ok and weekend_ok and hour_ok

        entry_cooldown_ok = bars_since_entry is None or bars_since_entry >= self.s.cooldown_bars
        reentry_ok = bars_since_exit is None or bars_since_exit >= self.s.reentry_bars
        cooldown_ok = entry_cooldown_ok and reentry_ok

        base = volume_break and one_bar_ok and nbar_ok and adx_ok and time_ok and cooldown_ok
        bearish = float(d.close.iloc[-1]) < float(d.open.iloc[-1])
        bullish = float(d.close.iloc[-1]) > float(d.open.iloc[-1])
        long_signal = base and self.s.allow_long and bearish and rsi_long_ok
        short_signal = base and self.s.allow_short and bullish and rsi_short_ok

        side = "LONG" if long_signal else "SHORT" if short_signal else None
        reason = "LONG_SIGNAL" if long_signal else "SHORT_SIGNAL" if short_signal else "NO_SIGNAL"
        diagnostics = {
            "volume_ratio": volume_ratio,
            "volume_break": volume_break,
            "one_bar_volatility": one_bar,
            "one_bar_ok": one_bar_ok,
            "nbar_range": n_range,
            "nbar_block_range": block_range,
            "nbar_ok": nbar_ok,
            "adx": adx_value,
            "adx_ok": adx_ok,
            "rsi": rsi_value,
            "rsi_oversold": oversold,
            "rsi_overbought": overbought,
            "time_ok": time_ok,
            "cooldown_ok": cooldown_ok,
            "raw_tp_percent": raw_tp,
            "raw_sl_percent": raw_sl,
            "final_tp_percent": final_tp,
            "final_sl_percent": final_sl,
            "entry_price": float(d.close.iloc[-1]),
        }
        sig = Signal(side, reason, base, diagnostics)
        state = StrategyState(symbol=symbol, timeframe=timeframe, timestamp=current_time, position=position or Position(), signal=sig, values=diagnostics)
        return V15Result(sig, state)
