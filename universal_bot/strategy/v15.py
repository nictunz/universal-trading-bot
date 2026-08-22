from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

import pandas as pd

from universal_bot.config import Settings
from universal_bot.indicators import dmi_adx, rolling_range_percent, rsi, sma
from universal_bot.models import Position, Signal, StrategyState


@dataclass
class V15Result:
    signal: Signal
    state: StrategyState


class UniversalV15Strategy:
    """TradingView-independent implementation of the supplied Universal v15 logic.

    The engine evaluates only the latest completed candle supplied by the caller.
    It is intentionally provider/exchange independent so the same strategy can be
    used by live trading, paper trading and backtesting.
    """

    name = "Volume Strategy FINAL Universal v15"
    version = "v15"

    def __init__(self, settings: Settings):
        self.s = settings

    def _not_ready(self, symbol: str, timeframe: str, reason: str, df: pd.DataFrame) -> V15Result:
        timestamp = None
        if len(df.index):
            ts = df.index[-1]
            timestamp = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else ts
        signal = Signal(None, reason, False, {})
        return V15Result(
            signal,
            StrategyState(symbol=symbol, timeframe=timeframe, timestamp=timestamp, signal=signal),
        )

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
        required = max(
            self.s.volume_lookback,
            self.s.volatility_bars,
            self.s.nbar_volatility_bars,
            self.s.adx_length * 2,
            self.s.rsi_length + 2,
        )
        if len(df) < required:
            return self._not_ready(symbol, timeframe, "NOT_ENOUGH_DATA", df)

        required_columns = {"open", "high", "low", "close", "volume"}
        if not required_columns.issubset(df.columns):
            return self._not_ready(symbol, timeframe, "MISSING_OHLCV", df)

        d = df.copy().sort_index()
        close = d["close"].astype(float)
        open_ = d["open"].astype(float)
        high = d["high"].astype(float)
        low = d["low"].astype(float)
        volume = d["volume"].astype(float)

        # 1) Volume breakout. For crypto the caller can supply the normalized
        # four-exchange ratio used by the Pine implementation.
        vol_avg = sma(volume, self.s.volume_lookback)
        chart_ratio = volume / vol_avg.replace(0, math.nan)
        ratio = normalized_volume_ratio if normalized_volume_ratio is not None else chart_ratio
        volume_ratio = float(ratio.iloc[-1]) if pd.notna(ratio.iloc[-1]) else math.nan
        volume_break = math.isfinite(volume_ratio) and volume_ratio >= self.s.volume_break_multiplier

        # 2) One-bar absolute body volatility.
        last_open = float(open_.iloc[-1])
        last_close = float(close.iloc[-1])
        one_bar_volatility = abs(last_close - last_open) / last_open * 100 if last_open else 0.0
        one_bar_ok = self.s.min_one_bar_vol <= one_bar_volatility <= self.s.max_one_bar_vol

        # 3) Dynamic TP/SL from the N-bar high/low range, then clamp.
        n_range_series = rolling_range_percent(high, low, self.s.volatility_bars)
        n_range = float(n_range_series.iloc[-1]) if pd.notna(n_range_series.iloc[-1]) else math.nan
        raw_tp = n_range * self.s.tp_vol_multiplier if math.isfinite(n_range) else math.nan
        raw_sl = n_range * self.s.sl_vol_multiplier if math.isfinite(n_range) else math.nan
        final_tp = (
            max(self.s.min_tp_percent, min(self.s.max_tp_percent, raw_tp))
            if math.isfinite(raw_tp) else math.nan
        )
        final_sl = (
            max(self.s.min_sl_percent, min(self.s.max_sl_percent, raw_sl))
            if math.isfinite(raw_sl) else math.nan
        )

        # 4) N-bar extreme-volatility entry block.
        block_range_series = rolling_range_percent(high, low, self.s.nbar_volatility_bars)
        block_range = float(block_range_series.iloc[-1]) if pd.notna(block_range_series.iloc[-1]) else math.nan
        nbar_ok = (
            not self.s.use_nbar_volatility_block
            or (math.isfinite(block_range) and block_range <= self.s.max_nbar_volatility)
        )
        nbar_blocked = self.s.use_nbar_volatility_block and not nbar_ok

        # 5) ADX range filter. Pine ta.dmi(length, length) uses Wilder smoothing.
        _, _, adx_series = dmi_adx(high, low, close, self.s.adx_length)
        adx_value = float(adx_series.iloc[-1]) if pd.notna(adx_series.iloc[-1]) else math.nan
        adx_range_ok = math.isfinite(adx_value) and self.s.adx_min <= adx_value <= self.s.adx_max
        adx_ok = (not self.s.use_adx_filter) or adx_range_ok

        # 6) RSI direction filter.
        rsi_series = rsi(close, self.s.rsi_length)
        rsi_value = float(rsi_series.iloc[-1]) if pd.notna(rsi_series.iloc[-1]) else math.nan
        oversold = math.isfinite(rsi_value) and self.s.rsi_oversold_min <= rsi_value <= self.s.rsi_oversold_max
        overbought = math.isfinite(rsi_value) and self.s.rsi_overbought_min <= rsi_value <= self.s.rsi_overbought_max
        rsi_long_ok = (not self.s.use_rsi_filter) or oversold
        rsi_short_ok = (not self.s.use_rsi_filter) or overbought

        # 7) Date / weekend / excluded-hour filter.
        ts = d.index[-1]
        current_time = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else (
            ts if isinstance(ts, datetime) else datetime.utcnow()
        )
        start_ok = (not self.s.use_start_date) or current_time >= self.s.start_date
        weekend_ok = (not self.s.block_weekend) or current_time.weekday() < 5
        excluded_hours = {x.strip() for x in self.s.excluded_hours.split(",") if x.strip()}
        hour_ok = current_time.strftime("%H") not in excluded_hours
        time_ok = start_ok and weekend_ok and hour_ok

        # 8) Cooldowns are supplied by the execution/backtest layer because the
        # strategy itself must remain stateless across symbols.
        entry_cooldown_ok = bars_since_entry is None or bars_since_entry >= self.s.cooldown_bars
        reentry_cooldown_ok = bars_since_exit is None or bars_since_exit >= self.s.reentry_bars
        cooldown_ok = entry_cooldown_ok and reentry_cooldown_ok

        # TradingView barstate.isconfirmed is represented by the caller providing
        # a completed OHLCV candle. No intrabar signal is generated here.
        base_entry = (
            volume_break
            and one_bar_ok
            and nbar_ok
            and adx_ok
            and time_ok
            and cooldown_ok
        )

        bearish = last_close < last_open
        bullish = last_close > last_open
        long_signal = base_entry and self.s.allow_long and bearish and rsi_long_ok
        short_signal = base_entry and self.s.allow_short and bullish and rsi_short_ok

        side = "LONG" if long_signal else "SHORT" if short_signal else None
        reason = "LONG_SIGNAL" if long_signal else "SHORT_SIGNAL" if short_signal else "NO_SIGNAL"

        # Signal eligibility is separate from position/pyramiding management.
        # The execution layer decides whether this signal may actually open an order.
        position = position or Position()
        position_side_allowed = (
            (side == "LONG" and (position.flat or position.side == "LONG"))
            or (side == "SHORT" and (position.flat or position.side == "SHORT"))
            or side is None
        )
        pyramid_allowed = position.flat or position.entries < self.s.max_pyramiding

        diagnostics: dict[str, object] = {
            "strategy": self.name,
            "version": self.version,
            "volume_ratio": volume_ratio,
            "volume_break": volume_break,
            "one_bar_volatility": one_bar_volatility,
            "one_bar_min": self.s.min_one_bar_vol,
            "one_bar_max": self.s.max_one_bar_vol,
            "one_bar_ok": one_bar_ok,
            "nbar_range": n_range,
            "nbar_bars": self.s.volatility_bars,
            "nbar_block_range": block_range,
            "nbar_block_bars": self.s.nbar_volatility_bars,
            "nbar_max_allowed": self.s.max_nbar_volatility,
            "nbar_ok": nbar_ok,
            "nbar_blocked": nbar_blocked,
            "adx": adx_value,
            "adx_min": self.s.adx_min,
            "adx_max": self.s.adx_max,
            "adx_ok": adx_ok,
            "rsi": rsi_value,
            "rsi_oversold": oversold,
            "rsi_overbought": overbought,
            "rsi_long_ok": rsi_long_ok,
            "rsi_short_ok": rsi_short_ok,
            "time_ok": time_ok,
            "cooldown_ok": cooldown_ok,
            "bars_since_entry": bars_since_entry,
            "bars_since_exit": bars_since_exit,
            "base_entry_condition": base_entry,
            "bearish_candle": bearish,
            "bullish_candle": bullish,
            "raw_tp_percent": raw_tp,
            "raw_sl_percent": raw_sl,
            "final_tp_percent": final_tp,
            "final_sl_percent": final_sl,
            "entry_price": last_close,
            "position_side_allowed": position_side_allowed,
            "pyramid_allowed": pyramid_allowed,
            "max_pyramiding": self.s.max_pyramiding,
        }

        signal = Signal(side, reason, base_entry, diagnostics)
        state = StrategyState(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=current_time,
            position=position,
            signal=signal,
            values=diagnostics,
        )
        return V15Result(signal, state)
