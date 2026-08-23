from __future__ import annotations

import math

from universal_bot.config import Settings
from universal_bot.models import Position
from universal_bot.paper import normalize_exchange_volume
from universal_bot.strategy.v15 import UniversalV15Strategy


class TradingEngine:
    def __init__(self, settings: Settings, adapter, strategy: UniversalV15Strategy):
        self.settings = settings
        self.adapter = adapter
        self.strategy = strategy
        self.position = Position()
        self.last_entry_bar: int | None = None
        self.last_exit_bar: int | None = None
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

    def _amount(self, price: float) -> float:
        equity = self.settings.initial_capital if self.settings.bot_mode.upper() != "LIVE" else self.adapter.equity()
        notional = equity * self.settings.order_percent_of_equity / 100.0
        return notional / price if price > 0 else 0.0

    def _open(self, side: str, price: float, tp_pct: float, sl_pct: float) -> None:
        amount = self._amount(price)
        if amount <= 0:
            return
        if self.settings.bot_mode.upper() == "LIVE":
            self.adapter.market_order(self.settings.symbol, "buy" if side == "LONG" else "sell", amount)
        signed_amount = amount if side == "LONG" else -amount
        if self.position.flat:
            self.position = Position(
                side=side,
                size=signed_amount,
                entry_price=price,
                tp=price * (1 + tp_pct / 100) if side == "LONG" else price * (1 - tp_pct / 100),
                sl=price * (1 - sl_pct / 100) if side == "LONG" else price * (1 + sl_pct / 100),
                entries=1,
            )
            self.entry_notional = amount * price
        else:
            self.position.entries += 1
            self.position.size += signed_amount
            self.entry_notional += amount * price
        self.last_entry_bar = self.bar_number

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
        pnl = (price - avg_entry) * qty if side == "LONG" else (avg_entry - price) * qty
        if self.settings.bot_mode.upper() == "LIVE":
            self.adapter.market_order(self.settings.symbol, "sell" if side == "LONG" else "buy", qty, reduce_only=True)
        self.realized_pnl += pnl
        self.closed_trades += 1
        if pnl >= 0:
            self.winning_trades += 1
            self.gross_profit += pnl
        else:
            self.gross_loss += abs(pnl)
        self.trade_log.append({
            "trade": self.closed_trades,
            "side": side,
            "entry_price": initial_entry,
            "avg_entry_price": avg_entry,
            "exit_price": price,
            "qty": qty,
            "pnl": pnl,
            "pnl_percent": pnl / abs(avg_entry * qty) * 100 if avg_entry and qty else 0.0,
            "reason": reason,
            "bar": self.bar_number,
        })
        self.position = Position()
        self.entry_notional = 0.0
        self.last_exit_bar = self.bar_number

    def step(self, df):
        self.bar_number += 1
        bars_since_entry = None if self.last_entry_bar is None else self.bar_number - self.last_entry_bar
        bars_since_exit = None if self.last_exit_bar is None else self.bar_number - self.last_exit_bar

        normalized_volume = None
        if self.settings.use_four_crypto_exchanges and self.adapter.asset_class == "crypto":
            try:
                sources = self.adapter.fetch_volume_sources(self.settings.symbol, self.settings.timeframe, len(df))
                if len(sources) >= 1:
                    normalized_volume = normalize_exchange_volume(sources, self.settings.volume_lookback)
                    normalized_volume = normalized_volume.reindex(df.index).ffill()
            except Exception:
                normalized_volume = None

        result = self.strategy.evaluate(df, self.settings.symbol, self.settings.timeframe, self.position,
                                        bars_since_entry, bars_since_exit, normalized_volume)
        price = float(df.close.iloc[-1])

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
        result.state.stats = {
            "closed_trades": float(self.closed_trades),
            "win_rate": self.winning_trades / self.closed_trades * 100 if self.closed_trades else 0.0,
            "profit_factor": self.gross_profit / self.gross_loss if self.gross_loss else math.nan,
            "realized_pnl": self.realized_pnl,
            "return_percent": self.realized_pnl / self.settings.initial_capital * 100 if self.settings.initial_capital else 0.0,
            "open_pnl": open_pnl,
            "equity": self.settings.initial_capital + self.realized_pnl + open_pnl,
        }
        self.last_state = result.state
        self.equity_curve.append({
            "bar": self.bar_number,
            "timestamp": df.index[-1].isoformat() if hasattr(df.index[-1], "isoformat") else str(df.index[-1]),
            "equity": self.settings.initial_capital + self.realized_pnl + open_pnl,
        })
        return result.state
