from __future__ import annotations

from datetime import datetime, timezone

from universal_bot.engine import TradingEngine as _BaseTradingEngine
from universal_bot.models import Position


class TradingEngine(_BaseTradingEngine):
    """Runtime engine with LIVE-only Elite sizing.

    Backtest/PAPER sizing stays on ORDER_PERCENT_OF_EQUITY. When LIVE execution
    uses the Bitget Elite profile, each entry uses current available USDT times
    LIVE_ENTRY_MULTIPLIER and the position is capped at
    LIVE_MAX_ENTRIES_PER_POSITION. A separate total-multiplier ceiling prevents
    accidental oversizing.
    """

    def __init__(self, settings, adapter, strategy):
        super().__init__(settings, adapter, strategy)
        self._live_entry_equity_basis: float | None = None

    def _elite_live(self) -> bool:
        return (
            self.live
            and self.settings.exchange.lower() == "bitget"
            and self.settings.bitget_execution_profile.strip().lower() == "elite"
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

        # After a process restart we cannot reliably reconstruct how many of the
        # allowed three tranches created an already-open exchange position. Be
        # conservative and block further pyramiding until that position closes.
        if self._elite_live() and self._live_initialized and not self.position.flat:
            self.position.entries = max(
                self.position.entries,
                int(self.settings.live_max_entries_per_position),
            )
            self._live_entry_equity_basis = None

    def _amount(self, price: float) -> float:
        if not self._elite_live():
            return super()._amount(price)
        available = float(self.adapter.equity())
        notional = available * float(self.settings.live_entry_multiplier)
        return notional / price if price > 0 else 0.0

    def _open(self, side: str, price: float, tp_pct: float, sl_pct: float) -> None:
        if not self._elite_live():
            super()._open(side, price, tp_pct, sl_pct)
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
        exchange_pos = self.adapter.position(self.settings.symbol)
        self.safety.reconcile(self._internal_position_dict(), exchange_pos)

    def _close(self, price: float, reason: str) -> None:
        super()._close(price, reason)
        if self.position.flat:
            self._live_entry_equity_basis = None
