from __future__ import annotations

from datetime import datetime, timezone

from universal_bot.engine import TradingEngine as _BaseTradingEngine
from universal_bot.models import Position


class TradingEngine(_BaseTradingEngine):
    """Runtime engine with LIVE-only Elite sizing and chart event journaling.

    Backtest/PAPER sizing stays on ORDER_PERCENT_OF_EQUITY. When LIVE execution
    uses the Bitget Elite profile, each entry uses current available USDT times
    LIVE_ENTRY_MULTIPLIER and the position is capped at
    LIVE_MAX_ENTRIES_PER_POSITION. A separate total-multiplier ceiling prevents
    accidental oversizing.
    """

    def __init__(self, settings, adapter, strategy):
        super().__init__(settings, adapter, strategy)
        self._live_entry_equity_basis: float | None = None
        self._event_no = 0

    def _elite_live(self) -> bool:
        return (
            self.live
            and self.settings.exchange.lower() == "bitget"
            and self.settings.bitget_execution_profile.strip().lower() == "elite"
        )

    def _record_runtime_event(self, event: dict) -> None:
        try:
            self._event_no += 1
            self.trade_history.record_event(
                run_id=self.trade_history_run_id,
                event_no=self._event_no,
                mode="LIVE" if self.live else "PAPER",
                symbol=self.settings.symbol,
                asset_class=self.settings.asset_class,
                exchange=self.settings.exchange,
                timeframe=self.settings.timeframe,
                event=event,
            )
        except Exception:
            # Trading must never fail because chart journaling failed.
            pass

    def _record_entry_event(self, *, side: str, price: float, qty: float) -> None:
        self._record_runtime_event(
            {
                "event_time": self.current_bar_time or datetime.now(timezone.utc).isoformat(),
                "event_type": "ENTRY",
                "entry_no": int(self.position.entries),
                "side": side,
                "price": float(price),
                "qty": float(qty),
                "position_size": abs(float(self.position.size)),
                "reason": "FIRST_ENTRY" if self.position.entries == 1 else "ADD_ENTRY",
                "metadata": {
                    "tp": self.position.tp,
                    "sl": self.position.sl,
                    "live_entry_multiplier": float(self.settings.live_entry_multiplier) if self._elite_live() else None,
                },
            }
        )

    def _initialize_live(self) -> None:
        if not self.live or self._live_initialized:
            return

        if self._elite_live() and hasattr(self.adapter, "ensure_leverage"):
            try:
                result = self.adapter.ensure_leverage(
                    self.settings.symbol,
                    int(self.settings.leverage),
                )
                if not result.get("ok"):
                    self.safety.fail(
                        f"LIVE_LEVERAGE_SYNC_FAILED: {result.get('reason', result)}"
                    )
                    return
            except Exception as exc:
                self.safety.fail(
                    f"LIVE_LEVERAGE_SYNC_FAILED: {type(exc).__name__}: {exc}"
                )
                return

        super()._initialize_live()

        # After a process restart we cannot reliably reconstruct how many
        # tranches created an already-open exchange position. Be conservative
        # and block further pyramiding until that position closes.
        if self._elite_live() and self._live_initialized and not self.position.flat:
            self.position.entries = max(
                self.position.entries,
                int(self.settings.live_max_entries_per_position),
            )
            self._live_entry_equity_basis = None

    def step(self, df, precomputed=None):
        # Saved dashboard strategy settings may contain an older pyramiding
        # value. LIVE Elite always follows the dedicated live entry cap.
        if self._elite_live():
            live_entries = int(self.settings.live_max_entries_per_position)
            if self.settings.max_pyramiding != live_entries:
                self.settings.max_pyramiding = live_entries
                if hasattr(self.strategy, "s"):
                    self.strategy.s.max_pyramiding = live_entries
        return super().step(df, precomputed)

    def _amount(self, price: float) -> float:
        if not self._elite_live():
            return super()._amount(price)
        available = float(self.adapter.equity())
        notional = available * float(self.settings.live_entry_multiplier)
        return notional / price if price > 0 else 0.0

    def _open(self, side: str, price: float, tp_pct: float, sl_pct: float) -> None:
        if not self._elite_live():
            before_entries = int(self.position.entries)
            super()._open(side, price, tp_pct, sl_pct)
            if int(self.position.entries) > before_entries:
                qty = abs(float(self.position.size)) if before_entries == 0 else max(0.0, abs(float(self.position.size)))
                self._record_entry_event(side=side, price=float(self.position.entry_price or price), qty=qty)
            return

        max_entries = int(self.settings.live_max_entries_per_position)
        if max_entries < 1:
            self.safety.fail("LIVE_MAX_ENTRIES_INVALID")
            return
        if not self.position.flat and self.position.entries >= max_entries:
            return

        available = float(self.adapter.equity())
        if available <= 0 or price <= 0:
            return

        if self.position.flat:
            self._live_entry_equity_basis = available
        elif self._live_entry_equity_basis is None:
            # Conservative restart guard: an existing position with unknown
            # tranche count must not receive another add-on entry.
            return

        intended_notional = available * float(self.settings.live_entry_multiplier)
        amount = intended_notional / price
        if amount <= 0:
            return

        basis = float(self._live_entry_equity_basis or available)
        existing_notional = abs(self.position.size) * price if not self.position.flat else 0.0
        max_notional = basis * float(self.settings.live_max_total_multiplier)
        if existing_notional + intended_notional > max_notional + 1e-9:
            self.safety.fail("LIVE_TOTAL_MULTIPLIER_LIMIT_EXCEEDED")
            return

        tp_price = price * (1 + tp_pct / 100) if side == "LONG" else price * (1 - tp_pct / 100)
        sl_price = price * (1 - sl_pct / 100) if side == "LONG" else price * (1 + sl_pct / 100)
        actual_price = price
        actual_amount = amount

        if not self.safety.can_open:
            return

        order_side = "buy" if side == "LONG" else "sell"
        order = self.adapter.market_order(
            self.settings.symbol,
            order_side,
            amount,
            tp_price=tp_price,
            sl_price=sl_price,
        )
        if not order:
            self.safety.fail("ENTRY_ORDER_EMPTY_RESPONSE")
            return

        actual_price = float(order.get("average") or order.get("price") or price)
        actual_amount = float(order.get("filled") or order.get("amount") or amount)
        protection = self.adapter.protection_status(self.settings.symbol)
        self.safety.protection_ok = bool(protection.get("ok"))
        if self.settings.require_exchange_protection and not self.safety.protection_ok:
            self._emergency_flatten(
                self.settings.symbol,
                actual_amount,
                "sell" if side == "LONG" else "buy",
            )
            if self.position.flat:
                self._live_entry_equity_basis = None
            self.safety.fail(
                "ENTRY_FILLED_BUT_PROTECTION_NOT_VERIFIED_EMERGENCY_FLATTEN"
            )
            return

        signed_amount = actual_amount if side == "LONG" else -actual_amount
        if self.position.flat:
            self.position = Position(
                side=side,
                size=signed_amount,
                entry_price=actual_price,
                tp=tp_price,
                sl=sl_price,
                entries=1,
            )
            self.entry_notional = actual_amount * actual_price
            self.position_entry_time = (
                self.current_bar_time or datetime.now(timezone.utc).isoformat()
            )
        else:
            self.position.entries += 1
            self.position.size += signed_amount
            self.entry_notional += actual_amount * actual_price

        self.last_entry_bar = self.bar_number
        self._record_entry_event(side=side, price=actual_price, qty=actual_amount)
        exchange_pos = self.adapter.position(self.settings.symbol)
        self.safety.reconcile(self._internal_position_dict(), exchange_pos)

    def _close(self, price: float, reason: str) -> None:
        before_trades = len(self.trade_log)
        super()._close(price, reason)
        if len(self.trade_log) > before_trades:
            trade = self.trade_log[-1]
            self._record_runtime_event(
                {
                    "event_time": trade.get("exit_time") or self.current_bar_time or datetime.now(timezone.utc).isoformat(),
                    "event_type": "EXIT",
                    "entry_no": None,
                    "side": trade.get("side"),
                    "price": trade.get("exit_price"),
                    "qty": trade.get("qty"),
                    "position_size": 0.0,
                    "pnl": trade.get("pnl"),
                    "pnl_percent": trade.get("pnl_percent"),
                    "reason": trade.get("reason") or reason,
                }
            )
        if self.position.flat:
            self._live_entry_equity_basis = None
