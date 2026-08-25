from __future__ import annotations

from datetime import datetime, timezone

from universal_bot.discord_notifier import DiscordNotifier
from universal_bot.engine import TradingEngine as _BaseTradingEngine
from universal_bot.models import Position


class TradingEngine(_BaseTradingEngine):
    """Runtime engine with LIVE-only Elite sizing and chart event journaling.

    Backtest/PAPER sizing stays on ORDER_PERCENT_OF_EQUITY. When LIVE execution
    uses the Bitget Elite profile, each entry uses current available USDT times
    LIVE_ENTRY_MULTIPLIER and the position is capped at
    LIVE_MAX_ENTRIES_PER_POSITION. After an add-on fill the full position's TP
    and SL are re-centered around the exchange-reported average entry price.
    """

    def __init__(self, settings, adapter, strategy):
        super().__init__(settings, adapter, strategy)
        self._live_entry_equity_basis: float | None = None
        self._active_tp_pct: float | None = None
        self._active_sl_pct: float | None = None
        self._event_no = 0
        self.notifier = DiscordNotifier(
            settings.discord_webhook_url,
            enabled=bool(settings.discord_notifications_enabled),
            timeout=float(settings.discord_timeout),
        )

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

    def _record_entry_event(
        self,
        *,
        side: str,
        price: float,
        qty: float,
        avg_price: float | None = None,
    ) -> None:
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
                    "avg_entry": float(avg_price if avg_price is not None else (self.position.entry_price or price)),
                    "tp": self.position.tp,
                    "sl": self.position.sl,
                    "live_entry_multiplier": float(self.settings.live_entry_multiplier) if self._elite_live() else None,
                },
            }
        )

    def _notify_entry(self, *, side: str, fill_price: float, qty: float) -> None:
        if not self.live:
            return
        entry_no = int(self.position.entries)
        label = "1차 진입" if entry_no == 1 else f"{entry_no}차 추가진입"
        avg = float(self.position.entry_price or fill_price)
        self.notifier.send_async(
            "\n".join(
                [
                    f"🚀 [ELITE {label}] {self.settings.symbol} {side}",
                    f"체결가: {fill_price:.6f}",
                    f"체결수량: {qty:.8f}",
                    f"전체 평단: {avg:.6f}",
                    f"전체 포지션: {abs(float(self.position.size)):.8f}",
                    f"TP: {float(self.position.tp or 0):.6f}",
                    f"SL: {float(self.position.sl or 0):.6f}",
                    f"레버리지: {int(self.settings.leverage)}x · 1회 진입배수: {float(self.settings.live_entry_multiplier):g}x",
                    f"진입횟수: {entry_no}/{int(self.settings.live_max_entries_per_position)}",
                ]
            )
        )

    def _notify_exit(self, trade: dict) -> None:
        if not self.live:
            return
        reason = str(trade.get("reason") or "EXIT").upper()
        icon = "✅" if reason == "TP" else "🛑" if reason == "SL" else "📤"
        pnl = float(trade.get("pnl") or 0.0)
        pct = float(trade.get("pnl_percent") or 0.0)
        self.notifier.send_async(
            "\n".join(
                [
                    f"{icon} [ELITE {reason}] {self.settings.symbol} {trade.get('side') or ''}",
                    f"평균 진입가: {float(trade.get('avg_entry_price') or trade.get('entry_price') or 0):.6f}",
                    f"청산가: {float(trade.get('exit_price') or 0):.6f}",
                    f"수량: {float(trade.get('qty') or 0):.8f}",
                    f"손익: {pnl:+.6f} USDT ({pct:+.3f}%)",
                ]
            )
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
        # tranches created an already-open exchange position or the original TP
        # and SL percentages. Be conservative and block further pyramiding until
        # that position closes.
        if self._elite_live() and self._live_initialized and not self.position.flat:
            self.position.entries = max(
                self.position.entries,
                int(self.settings.live_max_entries_per_position),
            )
            self._live_entry_equity_basis = None
            self._active_tp_pct = None
            self._active_sl_pct = None

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

    @staticmethod
    def _prices_from_average(side: str, avg: float, tp_pct: float, sl_pct: float) -> tuple[float, float]:
        if side == "LONG":
            return avg * (1 + tp_pct / 100), avg * (1 - sl_pct / 100)
        return avg * (1 - tp_pct / 100), avg * (1 + sl_pct / 100)

    def _flatten_full_position_after_protection_failure(self, side: str, total_qty: float) -> None:
        try:
            close_side = "sell" if side == "LONG" else "buy"
            self.adapter.market_order(
                self.settings.symbol,
                close_side,
                float(total_qty),
                reduce_only=True,
            )
            self.adapter.cancel_protection(self.settings.symbol)
            exchange_pos = self.adapter.position(self.settings.symbol)
            if exchange_pos.get("side") == "FLAT" and float(exchange_pos.get("size") or 0.0) <= 1e-9:
                self.position = Position()
                self.entry_notional = 0.0
                self.position_entry_time = None
                self._live_entry_equity_basis = None
                self._active_tp_pct = None
                self._active_sl_pct = None
            else:
                self.safety.fail("PROTECTION_REPLACE_FLATTEN_DID_NOT_CLOSE_POSITION")
        except Exception as exc:
            self.safety.fail(f"PROTECTION_REPLACE_FLATTEN_FAILED: {type(exc).__name__}: {exc}")

    def _open(self, side: str, price: float, tp_pct: float, sl_pct: float) -> None:
        if not self._elite_live():
            before_entries = int(self.position.entries)
            before_size = abs(float(self.position.size))
            super()._open(side, price, tp_pct, sl_pct)
            if int(self.position.entries) > before_entries:
                after_size = abs(float(self.position.size))
                qty = after_size if before_entries == 0 else max(0.0, after_size - before_size)
                self._record_entry_event(
                    side=side,
                    price=float(self.position.entry_price or price),
                    qty=qty,
                )
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

        before_entries = int(self.position.entries)
        if self.position.flat:
            self._live_entry_equity_basis = available
            self._active_tp_pct = float(tp_pct)
            self._active_sl_pct = float(sl_pct)
        elif self._live_entry_equity_basis is None:
            # Conservative restart guard: an existing position with unknown
            # tranche count must not receive another add-on entry.
            return

        active_tp_pct = float(self._active_tp_pct if self._active_tp_pct is not None else tp_pct)
        active_sl_pct = float(self._active_sl_pct if self._active_sl_pct is not None else sl_pct)

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

        # Temporary protection is attached to the new tranche immediately. For
        # an add-on entry it is replaced moments later by one full-position pair.
        temp_tp, temp_sl = self._prices_from_average(side, price, active_tp_pct, active_sl_pct)

        if not self.safety.can_open:
            return

        order_side = "buy" if side == "LONG" else "sell"
        order = self.adapter.market_order(
            self.settings.symbol,
            order_side,
            amount,
            tp_price=temp_tp,
            sl_price=temp_sl,
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
                self._active_tp_pct = None
                self._active_sl_pct = None
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
                tp=temp_tp,
                sl=temp_sl,
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

        # Re-read Bitget after every fill so the internal size/average matches the
        # exchange. This is especially important after the second entry.
        exchange_pos = self.adapter.position(self.settings.symbol)
        total_qty = abs(float(exchange_pos.get("size") or self.position.size))
        avg_entry = float(exchange_pos.get("entry_price") or 0.0)
        if avg_entry <= 0 and total_qty > 0:
            avg_entry = self.entry_notional / total_qty

        full_tp, full_sl = self._prices_from_average(
            side,
            avg_entry,
            active_tp_pct,
            active_sl_pct,
        )

        if before_entries > 0:
            if not hasattr(self.adapter, "replace_full_protection"):
                self._flatten_full_position_after_protection_failure(side, total_qty)
                self.safety.fail("FULL_POSITION_PROTECTION_REPLACE_UNSUPPORTED")
                return
            try:
                replaced = self.adapter.replace_full_protection(
                    self.settings.symbol,
                    "long" if side == "LONG" else "short",
                    total_qty,
                    full_tp,
                    full_sl,
                )
            except Exception as exc:
                replaced = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
            self.safety.protection_ok = bool(replaced.get("ok"))
            if self.settings.require_exchange_protection and not self.safety.protection_ok:
                self._flatten_full_position_after_protection_failure(side, total_qty)
                self.safety.fail(
                    f"ADD_ENTRY_FULL_PROTECTION_REPLACE_FAILED: {replaced.get('reason', replaced)}"
                )
                return

        # Align the internal position with Bitget and the final full-position TP/SL.
        self.position.side = side
        self.position.size = total_qty if side == "LONG" else -total_qty
        self.position.entry_price = avg_entry
        self.position.tp = full_tp
        self.position.sl = full_sl
        self.entry_notional = total_qty * avg_entry

        self.last_entry_bar = self.bar_number
        self._record_entry_event(
            side=side,
            price=actual_price,
            qty=actual_amount,
            avg_price=avg_entry,
        )
        self._notify_entry(side=side, fill_price=actual_price, qty=actual_amount)
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
            self._notify_exit(trade)
        if self.position.flat:
            self._live_entry_equity_basis = None
            self._active_tp_pct = None
            self._active_sl_pct = None
