from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Position:
    symbol: str
    side: str
    qty: float
    entry_price: float
    tp_price: float
    sl_price: float


@dataclass
class ExecutionGuard:
    """Safety gate separating BACKTEST/PAPER from LIVE execution."""
    mode: str = "PAPER"
    live_confirmed: bool = False

    def can_execute_live(self) -> bool:
        return self.mode.upper() == "LIVE" and self.live_confirmed

    def require_live(self) -> None:
        if not self.can_execute_live():
            raise RuntimeError("LIVE execution is disabled. Set BOT_MODE=LIVE and explicit LIVE confirmation.")


class ExecutionEngine:
    """TradingView-independent position engine. PAPER is the safe default."""

    def __init__(self, mode: str = "PAPER", order_router=None, live_confirmed: bool = False):
        self.guard = ExecutionGuard(mode.upper(), live_confirmed)
        self.order_router = order_router
        self.positions: dict[str, Position] = {}

    def enter(self, symbol: str, side: str, qty: float, price: float, tp_percent: float, sl_percent: float) -> Position:
        side = side.upper()
        if side not in ("LONG", "SHORT"):
            raise ValueError("side must be LONG or SHORT")
        if qty <= 0 or price <= 0:
            raise ValueError("qty and price must be positive")
        if symbol in self.positions:
            raise RuntimeError(f"Position already exists for {symbol}")
        if self.guard.mode == "LIVE":
            self.guard.require_live()
            if self.order_router is None:
                raise RuntimeError("LIVE mode requires an order_router")
        if side == "LONG":
            tp = price * (1 + tp_percent / 100)
            sl = price * (1 - sl_percent / 100)
        else:
            tp = price * (1 - tp_percent / 100)
            sl = price * (1 + sl_percent / 100)
        position = Position(symbol, side, qty, price, tp, sl)
        if self.guard.mode == "LIVE":
            self.order_router.open_position(position)
        self.positions[symbol] = position
        return position

    def check_exit(self, symbol: str, price: float) -> Optional[str]:
        p = self.positions.get(symbol)
        if p is None:
            return None
        if p.side == "LONG":
            reason = "TP" if price >= p.tp_price else "SL" if price <= p.sl_price else None
        else:
            reason = "TP" if price <= p.tp_price else "SL" if price >= p.sl_price else None
        if reason:
            self.close(symbol, price, reason)
        return reason

    def close(self, symbol: str, price: float, reason: str = "MANUAL") -> None:
        p = self.positions.pop(symbol, None)
        if p is None:
            return
        if self.guard.mode == "LIVE":
            self.guard.require_live()
            if self.order_router is None:
                raise RuntimeError("LIVE mode requires an order_router")
            self.order_router.close_position(p, price, reason)
