from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

from universal_bot.config import Settings
from universal_bot.models import Position
from universal_bot.paper import normalize_exchange_volume
from universal_bot.strategy.v15 import UniversalV15Strategy
from universal_bot.live_safety import LiveSafety


class TradingEngine:
    REQUIRED_VOLUME_SOURCES = {"binance", "bitget", "okx", "bybit"}

    def __init__(self, settings: Settings, adapter, strategy: UniversalV15Strategy):
        self.settings = settings
        self.adapter = adapter
        self.strategy = strategy
        self.position = Position()
        self.last_entry_bar: int | None = None
        self.last_exit_bar: int | None = None
        self.last_processed_timestamp = None
        self.bar_number = 0
        self.last_state = None
        self.realized_pnl = 0.0
        self.closed_trades = 0
        self.winning_trades = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.trade_log: list[dict] = []
        self.equity_curve: list[dict] = []
        self.entry_notional = 0.0
        self.live = settings.bot_mode.upper() == "LIVE"
        self.safety = LiveSafety(enabled=self.live)
        self._live_initialized = False

    def _amount(self, price: float) -> float:
        equity = self.settings.initial_capital if not self.live else self.adapter.equity()
        notional = equity * self.settings.order_percent_of_equity / 100.0
        return notional / price if price > 0 else 0.0

    def _internal_position_dict(self) -> dict:
        return {"side": self.position.side if not self.position.flat else "FLAT", "size": abs(self.position.size), "entry_price": self.position.entry_price or 0.0}

    def _emergency_flatten(self, symbol: str, amount: float, side: str) -> None:
        try:
            self.adapter.market_order(symbol, side, amount, reduce_only=True)
        except Exception as exc:
            self.safety.fail(f"EMERGENCY_FLATTEN_FAILED: {type(exc).__name__}: {exc}")

    def _initialize_live(self) -> None:
        if not self.live or self._live_initialized:
            return
        if self.settings.exchange.lower() != "bitget" or self.settings.asset_class.lower() != "crypto":
            self.safety.fail("LIVE_RESTRICTED_TO_BITGET_CRYPTO")
            return
        try:
            result = self.adapter.configure_live(self.settings.symbol, int(self.settings.leverage), str(self.settings.margin_mode).lower(), bool(self.settings.live_require_one_way_mode))
            if not result.get("ok"):
                self.safety.fail(f"LIVE_CONFIGURATION_FAILED: {result.get('reason', result)}")
                return
            exchange_pos = self.adapter.position(self.settings.symbol)
            if exchange_pos.get("side") != "FLAT":
                self.position = Position(side=exchange_pos["side"], size=exchange_pos["size"] if exchange_pos["side"] == "LONG" else -exchange_pos["size"], entry_price=exchange_pos.get("entry_price") or None, entries=1)
                self.entry_notional = abs(self.position.size) * float(self.position.entry_price or 0.0)
            if not self.safety.reconcile(self._internal_position_dict(), exchange_pos):
                return
            protection = self.adapter.protection_status(self.settings.symbol)
            self.safety.protection_ok = bool(protection.get("ok")) if not self.position.flat else True
            if not self.position.flat and self.settings.require_exchange_protection and not self.safety.protection_ok:
                self.safety.fail("EXISTING_POSITION_HAS_NO_VERIFIED_PROTECTION")
                return
            self._live_initialized = True
        except Exception as exc:
            self.safety.fail(f"LIVE_INITIALIZATION_FAILED: {type(exc).__name__}: {exc}")

    def _reconcile_live(self) -> None:
        if not self.live:
            return
        try:
            exchange_pos = self.adapter.position(self.settings.symbol)
            if not self.safety.reconcile(self._internal_position_dict(), exchange_pos):
                return
            self.safety.clear_error()
            protection = self.adapter.protection_status(self.settings.symbol)
            self.safety.protection_ok = bool(protection.get("ok")) if not self.position.flat else True
            if not self.position.flat and self.settings.require_exchange_protection and not self.safety.protection_ok:
                self.safety.fail("POSITION_LOST_EXCHANGE_PROTECTION")
        except Exception as exc:
            self.safety.record_error(f"LIVE_RECONCILIATION_FAILED: {type(exc).__name__}: {exc}", int(self.settings.max_consecutive_api_errors))

    def _open(self, side: str, price: float, tp_pct: float, sl_pct: float) -> None:
        amount = self._amount(price)
        if amount <= 0:
            return
        equity = self.adapter.equity() if self.live else self.settings.initial_capital
        intended_notional = amount * price
        existing_notional = abs(self.position.size) * price if not self.position.flat else 0.0
        if self.live and existing_notional + intended_notional > equity * float(self.settings.live_max_position_notional_percent) / 100.0:
            self.safety.fail("LIVE_POSITION_SIZE_LIMIT_EXCEEDED")
            return
        tp_price = price * (1 + tp_pct / 100) if side == "LONG" else price * (1 - tp_pct / 100)
        sl_price = price * (1 - sl_pct / 100) if side == "LONG" else price * (1 + sl_pct / 100)
        actual_price = price
        actual_amount = amount
        if self.live:
            if not self.safety.can_open:
                return
            order_side = "buy" if side == "LONG" else "sell"
            order = self.adapter.market_order(self.settings.symbol, order_side, amount, tp_price=tp_price, sl_price=sl_price)
            if not order:
                self.safety.fail("ENTRY_ORDER_EMPTY_RESPONSE")
                return
            actual_price = float(order.get("average") or order.get("price") or price)
            actual_amount = float(order.get("filled") or order.get("amount") or amount)
            protection = self.adapter.protection_status(self.settings.symbol)
            self.safety.protection_ok = bool(protection.get("ok"))
            if self.settings.require_exchange_protection and not self.safety.protection_ok:
                self._emergency_flatten(self.settings.symbol, actual_amount, "sell" if side == "LONG" else "buy")
                self.safety.fail("ENTRY_FILLED_BUT_PROTECTION_NOT_VERIFIED_EMERGENCY_FLATTEN")
                return
        signed_amount = actual_amount if side == "LONG" else -actual_amount
        if self.position.flat:
            self.position = Position(side=side, size=signed_amount, entry_price=actual_price, tp=tp_price, sl=sl_price, entries=1)
            self.entry_notional = actual_amount * actual_price
        else:
            self.position.entries += 1
            self.position.size += signed_amount
            self.entry_notional += actual_amount * actual_price
        self.last_entry_bar = self.bar_number
        if self.live:
            exchange_pos = self.adapter.position(self.settings.symbol)
            if not self.safety.reconcile(self._internal_position_dict(), exchange_pos):
                return

    def _open_pnl(self, price: float) -> float:
        if self.position.flat or not self.position.entry_price:
            return 0.0
        qty = abs(self.position.size)
        avg_entry = self.entry_notional / qty if qty and self.entry_notional else self.position.entry_price
        return (price - avg_entry) * qty if self.position.side == "LONG" else (avg_entry - price) * qty

    def _close(self, price: float, reason: str) -> None:
        if self.position.flat or self.position.entry_price is None:
            return
        qty = abs(self.position.size)
        side = self.position.side
        initial_entry = self.position.entry_price
        avg_entry = self.entry_notional / qty if qty and self.entry_notional else initial_entry
        exit_price = price
        if self.live:
            order = self.adapter.market_order(self.settings.symbol, "sell" if side == "LONG" else "buy", qty, reduce_only=True)
            if not order:
                self.safety.fail("EXIT_ORDER_EMPTY_RESPONSE")
                return
            exit_price = float(order.get("average") or order.get("price") or price)
            self.adapter.cancel_protection(self.settings.symbol)
        pnl = (exit_price - avg_entry) * qty if side == "LONG" else (avg_entry - exit_price) * qty
        self.realized_pnl += pnl
        self.closed_trades += 1
        if pnl >= 0:
            self.winning_trades += 1
            self.gross_profit += pnl
        else:
            self.gross_loss += abs(pnl)
        self.trade_log.append({"trade": self.closed_trades, "side": side, "entry_price": initial_entry, "avg_entry_price": avg_entry, "exit_price": exit_price, "qty": qty, "pnl": pnl, "pnl_percent": pnl / abs(avg_entry * qty) * 100 if avg_entry and qty else 0.0, "reason": reason, "bar": self.bar_number})
        self.position = Position()
        self.entry_notional = 0.0
        self.last_exit_bar = self.bar_number
        if self.live:
            exchange_pos = self.adapter.position(self.settings.symbol)
            if exchange_pos.get("side") != "FLAT" or float(exchange_pos.get("size") or 0) > 1e-9:
                self.safety.fail("EXIT_ORDER_DID_NOT_FLATTEN_POSITION")

    def _normalized_live_volume(self, df) -> pd.Series | None:
        if not (self.settings.use_four_crypto_exchanges and self.adapter.asset_class == "crypto"):
            return None
        try:
            sources = self.adapter.fetch_volume_sources(self.settings.symbol, self.settings.timeframe, len(df))
        except Exception:
            sources = {}
        if set(sources) != self.REQUIRED_VOLUME_SOURCES:
            return pd.Series(math.nan, index=df.index, dtype=float)
        ratio = normalize_exchange_volume(sources, self.settings.volume_lookback, required_sources=4)
        return ratio.reindex(df.index)

    def _live_heartbeat(self, df):
        self._initialize_live()
        self._reconcile_live()
        if len(df.index):
            ts = df.index[-1]
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            self.safety.record_data(ts)
            if self.safety.stale(datetime.now(timezone.utc), int(self.settings.stale_data_seconds)):
                self.safety.fail("STALE_MARKET_DATA")
        if self.safety.halted:
            return self._halted_state(df)
        return self.last_state

    def step(self, df, precomputed: dict[str, float] | None = None):
        if len(df.index) == 0:
            return self.strategy._not_ready(self.settings.symbol, self.settings.timeframe, "NOT_ENOUGH_DATA", df).state

        bar_timestamp = df.index[-1]
        if self.last_processed_timestamp is not None and bar_timestamp == self.last_processed_timestamp:
            # Polling may happen many times during the same 5-minute bar.  Keep
            # live reconciliation running, but never count the same candle as a
            # new bar or allow a duplicate/pyramiding entry from it.
            return self._live_heartbeat(df) if self.live else self.last_state

        self.last_processed_timestamp = bar_timestamp
        self.bar_number += 1
        bars_since_entry = None if self.last_entry_bar is None else self.bar_number - self.last_entry_bar
        bars_since_exit = None if self.last_exit_bar is None else self.bar_number - self.last_exit_bar
        if self.live:
            self._initialize_live()
            self._reconcile_live()
            if self.safety.halted:
                return self._halted_state(df)

        normalized_volume = self._normalized_live_volume(df) if precomputed is None else None
        result = self.strategy.evaluate(df, self.settings.symbol, self.settings.timeframe, self.position, bars_since_entry, bars_since_exit, normalized_volume, precomputed)
        price = float(df.close.iloc[-1])
        if self.live:
            ts = bar_timestamp.to_pydatetime() if hasattr(bar_timestamp, "to_pydatetime") else bar_timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            self.safety.record_data(ts)
            if self.safety.stale(datetime.now(timezone.utc), int(self.settings.stale_data_seconds)):
                self.safety.fail("STALE_MARKET_DATA")
                return self._halted_state(df)
        if not self.position.flat:
            hit_tp = (self.position.side == "LONG" and price >= self.position.tp) or (self.position.side == "SHORT" and price <= self.position.tp)
            hit_sl = (self.position.side == "LONG" and price <= self.position.sl) or (self.position.side == "SHORT" and price >= self.position.sl)
            if hit_tp or hit_sl:
                self._close(price, "TP" if hit_tp else "SL")
        signal = result.signal.side
        can_pyramid = self.position.entries < self.settings.max_pyramiding
        same_direction = self.position.flat or self.position.side == signal
        new_entry_this_bar = self.last_entry_bar != self.bar_number
        if signal and can_pyramid and same_direction and new_entry_this_bar:
            self._open(signal, price, float(result.state.values["final_tp_percent"]), float(result.state.values["final_sl_percent"]))
        open_pnl = self._open_pnl(price)
        result.state.position = self.position
        if self.live:
            display_equity = self.adapter.equity()
        else:
            display_equity = self.settings.initial_capital + self.realized_pnl + open_pnl
        result.state.stats = {"closed_trades": float(self.closed_trades), "win_rate": self.winning_trades / self.closed_trades * 100 if self.closed_trades else 0.0, "profit_factor": self.gross_profit / self.gross_loss if self.gross_loss else math.nan, "realized_pnl": self.realized_pnl, "return_percent": self.realized_pnl / self.settings.initial_capital * 100 if self.settings.initial_capital else 0.0, "open_pnl": open_pnl, "equity": display_equity, "live_halted": self.safety.halted, "live_safety_reason": self.safety.reason, "protection_ok": self.safety.protection_ok}
        self.last_state = result.state
        self.equity_curve.append({"bar": self.bar_number, "timestamp": bar_timestamp.isoformat() if hasattr(bar_timestamp, "isoformat") else str(bar_timestamp), "equity": display_equity})
        return result.state

    def _halted_state(self, df):
        state = self.strategy._not_ready(self.settings.symbol, self.settings.timeframe, f"LIVE_HALTED:{self.safety.reason}", df).state
        state.position = self.position
        state.stats = {"closed_trades": float(self.closed_trades), "win_rate": self.winning_trades / self.closed_trades * 100 if self.closed_trades else 0.0, "profit_factor": self.gross_profit / self.gross_loss if self.gross_loss else math.nan, "realized_pnl": self.realized_pnl, "open_pnl": self._open_pnl(float(df.close.iloc[-1])) if len(df) else 0.0, "equity": self.adapter.equity() if self.live else self.settings.initial_capital + self.realized_pnl, "live_halted": True, "live_safety_reason": self.safety.reason, "protection_ok": self.safety.protection_ok}
        self.last_state = state
        return state
