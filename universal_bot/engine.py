from __future__ import annotations

import math
import time
from datetime import datetime, timezone

import pandas as pd

from universal_bot.config import Settings
from universal_bot.discord_notifier import DiscordNotifier
from universal_bot.live_safety import LiveSafety
from universal_bot.models import Position
from universal_bot.paper import normalize_exchange_volume
from universal_bot.strategy.v15 import UniversalV15Strategy
from universal_bot.trade_history import TradeHistoryStore


def effective_stale_seconds(timeframe: str, configured_seconds: int) -> int:
    """Allow a completed candle to age through the next candle boundary.

    Candle timestamps represent their open time. A fresh closed 15m candle is
    therefore already at least 15 minutes old and may approach 30 minutes old
    before the next closed candle becomes available.
    """
    text = str(timeframe).strip().lower()
    try:
        value = int(text[:-1])
        unit_seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[text[-1]]
        timeframe_seconds = value * unit_seconds
    except (KeyError, TypeError, ValueError, IndexError):
        timeframe_seconds = 0
    return max(int(configured_seconds), timeframe_seconds * 2 + 120)


class TradingEngine:
    REQUIRED_VOLUME_SOURCES = {"binance", "bitget", "okx", "bybit"}

    def __init__(self, settings: Settings, adapter, strategy: UniversalV15Strategy):
        self.settings = settings
        self.adapter = adapter
        self.strategy = strategy
        self.position = Position()
        self.last_entry_bar: int | None = None
        self.last_exit_bar: int | None = None
        self._exit_signal_bar_time: datetime | None = None
        self._previous_exit_bar: int | None = None
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
        self.position_entry_time: str | None = None
        self.current_bar_time: str | None = None
        self.current_market_regime = "미분류"
        self.current_volatility_regime = "미분류"
        self.current_regime_risk_multiplier = 1.0
        self.live = settings.bot_mode.upper() == "LIVE"
        self.safety = LiveSafety(enabled=self.live)
        self._live_initialized = False
        self.trade_history = TradeHistoryStore()
        self.discord = DiscordNotifier(
            settings.discord_webhook_url,
            enabled=self.live and settings.discord_notifications_enabled,
            timeout=settings.discord_timeout,
        )
        self._external_flat_notified = False
        self._last_protection_status: dict = {"ok": True, "count": 0, "orders": []}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.trade_history_run_id = f"{settings.bot_mode.upper()}-{settings.symbol}-{stamp}"

    def _notify_live(self, title: str, **fields) -> None:
        if not self.live:
            return
        lines = [f"**{title}**"]
        lines.extend(f"**{key}**: {value}" for key, value in fields.items())
        lines.append(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
        self.discord.send_async("\n".join(lines))

    def _amount(self, price: float) -> float:
        equity = self.settings.initial_capital if not self.live else self.adapter.equity()
        notional = equity * self.settings.order_percent_of_equity / 100.0 * self.current_regime_risk_multiplier
        return notional / price if price > 0 else 0.0

    def _adaptive_regime(self, df) -> tuple[str, str, float]:
        if not bool(getattr(self.settings, "adaptive_regime_enabled", False)):
            return "비활성", "비활성", 1.0
        lookback = max(20, int(getattr(self.settings, "regime_lookback_bars", 288)))
        if len(df.index) <= lookback:
            return "미분류", "미분류", 0.0
        closes = df["close"].astype(float).iloc[-(lookback + 1):]
        oldest = float(closes.iloc[0])
        newest = float(closes.iloc[-1])
        trend = (newest / oldest - 1.0) * 100.0 if oldest else 0.0
        threshold = float(getattr(self.settings, "regime_trend_threshold_percent", 2.0))
        market = "상승장" if trend >= threshold else ("하락장" if trend <= -threshold else "횡보장")
        recent = df.iloc[-lookback:]
        ranges = ((recent["high"].astype(float) - recent["low"].astype(float)) / recent["close"].astype(float).replace(0, float("nan")) * 100.0)
        avg_range = float(ranges.mean()) if len(ranges) else 0.0
        high_threshold = float(getattr(self.settings, "regime_high_volatility_percent", 0.8))
        volatility = "고변동성" if avg_range >= high_threshold else "저변동성"
        risk = float(getattr(self.settings, "regime_high_volatility_risk_multiplier", 0.5)) if volatility == "고변동성" else 1.0
        return market, volatility, risk

    def _internal_position_dict(self) -> dict:
        return {"side": self.position.side if not self.position.flat else "FLAT", "size": abs(self.position.size), "entry_price": self.position.entry_price or 0.0}

    def _emergency_flatten(self, symbol: str, amount: float, side: str) -> None:
        try:
            self.adapter.market_order(symbol, side, amount, reduce_only=True)
        except Exception as exc:
            self.safety.fail(f"EMERGENCY_FLATTEN_FAILED: {type(exc).__name__}: {exc}")

    def _restore_protection_prices(self, protection: dict) -> None:
        """Restore TP/SL from exchange-owned plans after a process restart."""
        if self.position.flat:
            return
        entry = float(self.position.entry_price or 0.0)
        found: dict[str, float] = {}
        unknown: list[float] = []
        for raw in protection.get("orders") or []:
            order = dict(raw)
            text = str(order.get("clientOid") or "").lower()
            leg = str(order.get("leg") or "").lower()
            value = order.get("triggerPrice")
            if leg == "tp":
                value = value or order.get("takeProfit")
            elif leg == "sl":
                value = value or order.get("stopLoss")
            try:
                price = float(value or 0.0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if leg in {"tp", "sl"}:
                found[leg] = price
            elif text.startswith("utb-tp-"):
                found["tp"] = price
            elif text.startswith("utb-sl-"):
                found["sl"] = price
            else:
                unknown.append(price)

        # Older pending-order responses do not always retain clientOid. Infer
        # the two legs from their position relative to the exchange entry.
        for price in unknown:
            if self.position.side == "LONG":
                found.setdefault("tp" if price > entry else "sl", price)
            else:
                found.setdefault("tp" if price < entry else "sl", price)
        if found.get("tp"):
            self.position.tp = found["tp"]
        if found.get("sl"):
            self.position.sl = found["sl"]

    def _handle_external_flat(self, exchange_position: dict) -> bool:
        """Hook for runtimes that can journal an exchange-side TP/SL fill."""
        return False

    def _confirm_live_flat(self, attempts: int = 7, delay: float = 0.15) -> dict:
        """Confirm a close without removing protection from a still-open position."""
        exchange_pos: dict = {}
        for attempt in range(max(1, int(attempts))):
            try:
                exchange_pos = self.adapter.position(self.settings.symbol)
            except Exception:
                exchange_pos = {}
            if (
                exchange_pos.get("side") == "FLAT"
                and float(exchange_pos.get("size") or 0.0) <= 1e-9
            ):
                return exchange_pos
            if attempt + 1 < attempts:
                time.sleep(max(0.0, float(delay)))
        return exchange_pos

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
                self.position_entry_time = datetime.now(timezone.utc).isoformat()
            if not self.safety.reconcile(self._internal_position_dict(), exchange_pos):
                return
            if self.position.flat:
                protection = {"ok": True, "count": 0, "orders": [], "skipped": "flat"}
                self.safety.protection_ok = True
            else:
                protection = self.adapter.protection_status(self.settings.symbol)
                self.safety.protection_ok = bool(protection.get("ok"))
                if self.safety.protection_ok:
                    self._restore_protection_prices(protection)
            self._last_protection_status = protection
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
            if not self.position.flat and exchange_pos.get("side") == "FLAT":
                # A single eventually-consistent FLAT response must not cancel
                # valid protection or create a false close journal entry.
                confirmed = self.adapter.position(self.settings.symbol)
                if confirmed.get("side") != "FLAT" or float(confirmed.get("size") or 0.0) > 1e-9:
                    exchange_pos = confirmed
            if not self.position.flat and exchange_pos.get("side") == "FLAT":
                if self._handle_external_flat(exchange_pos):
                    exchange_pos = {"side": "FLAT", "size": 0.0, "entry_price": 0.0}
                elif not self._external_flat_notified:
                    self._notify_live(
                        "🔔 Bitget TP/SL 청산 감지",
                        심볼=self.settings.symbol,
                        기존방향=self.position.side,
                        기존수량=f"{abs(self.position.size):.8f}",
                        진입가=f"{float(self.position.entry_price or 0.0):.4f}",
                        안내="거래소 보호주문 체결로 포지션이 FLAT입니다. 서버가 안전중지됩니다.",
                    )
                    self._external_flat_notified = True
            if not self.safety.reconcile(self._internal_position_dict(), exchange_pos):
                return
            self.safety.clear_error()
            if self.position.flat:
                # No position means there is nothing to protect. Avoid ten
                # needless plan-order calls on every two-second heartbeat.
                protection = {"ok": True, "count": 0, "orders": [], "skipped": "flat"}
                self.safety.protection_ok = True
            else:
                protection = self.adapter.protection_status(self.settings.symbol)
                self.safety.protection_ok = bool(protection.get("ok"))
                if self.safety.protection_ok:
                    self._restore_protection_prices(protection)
            self._last_protection_status = protection
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
            self.position_entry_time = self.current_bar_time or datetime.now(timezone.utc).isoformat()
        else:
            self.position.entries += 1
            self.position.size += signed_amount
            self.entry_notional += actual_amount * actual_price
        self.last_entry_bar = self.bar_number
        if self.live:
            exchange_pos = self.adapter.position(self.settings.symbol)
            if not self.safety.reconcile(self._internal_position_dict(), exchange_pos):
                return
            self._external_flat_notified = False
            self._notify_live(
                "🚀 실거래 진입 체결",
                심볼=self.settings.symbol,
                방향=side,
                체결가=f"{actual_price:.4f}",
                수량=f"{actual_amount:.8f}",
                명목금액=f"{actual_price * actual_amount:.2f} USDT",
                TP=f"{tp_price:.4f} ({tp_pct:.3f}%)",
                SL=f"{sl_price:.4f} ({sl_pct:.3f}%)",
                보호주문="검증 완료" if self.safety.protection_ok else "검증 실패",
            )

    def _open_pnl(self, price: float) -> float:
        if self.position.flat or not self.position.entry_price:
            return 0.0
        qty = abs(self.position.size)
        avg_entry = self.entry_notional / qty if qty and self.entry_notional else self.position.entry_price
        return (price - avg_entry) * qty if self.position.side == "LONG" else (avg_entry - price) * qty

    def _notify_closed_trade(self, trade: dict) -> None:
        self._notify_live(
            "✅ 실거래 청산 체결",
            심볼=self.settings.symbol,
            방향=trade.get("side"),
            진입가=f"{float(trade.get('avg_entry_price') or 0.0):.4f}",
            청산가=f"{float(trade.get('exit_price') or 0.0):.4f}",
            수량=f"{float(trade.get('qty') or 0.0):.8f}",
            손익=f"{float(trade.get('pnl') or 0.0):.2f} USDT",
            수익률=f"{float(trade.get('pnl_percent') or 0.0):.3f}%",
            사유=trade.get("reason"),
        )

    def _finalize_closed_trade(
        self,
        exit_price: float,
        reason: str,
        *,
        exit_time: str | None = None,
        fee: float = 0.0,
        reported_pnl: float | None = None,
        metadata: dict | None = None,
    ) -> dict | None:
        if self.position.flat or self.position.entry_price is None:
            return None
        qty = abs(self.position.size)
        side = self.position.side
        initial_entry = float(self.position.entry_price)
        avg_entry = self.entry_notional / qty if qty and self.entry_notional else initial_entry
        calculated_gross = (
            (float(exit_price) - avg_entry) * qty
            if side == "LONG"
            else (avg_entry - float(exit_price)) * qty
        )
        gross_pnl = float(reported_pnl) if reported_pnl is not None and math.isfinite(float(reported_pnl)) else calculated_gross
        cost = abs(float(fee or 0.0))
        pnl = gross_pnl - cost
        self.realized_pnl += pnl
        self.closed_trades += 1
        if pnl >= 0:
            self.winning_trades += 1
            self.gross_profit += pnl
        else:
            self.gross_loss += abs(pnl)
        trade = {
            "trade": self.closed_trades,
            "side": side,
            "entry_time": self.position_entry_time,
            "exit_time": exit_time or self.current_bar_time or datetime.now(timezone.utc).isoformat(),
            "entry_price": initial_entry,
            "avg_entry_price": avg_entry,
            "exit_price": float(exit_price),
            "qty": qty,
            "gross_pnl": gross_pnl,
            "estimated_cost": cost,
            "pnl": pnl,
            "pnl_percent": pnl / abs(avg_entry * qty) * 100 if avg_entry and qty else 0.0,
            "reason": reason,
            "bar": self.bar_number,
            "metadata": dict(metadata or {}),
        }
        self.trade_log.append(trade)
        try:
            self.trade_history.record_trade(
                run_id=self.trade_history_run_id,
                trade_no=self.closed_trades,
                mode="LIVE" if self.live else "PAPER",
                symbol=self.settings.symbol,
                asset_class=self.settings.asset_class,
                exchange=self.settings.exchange,
                timeframe=self.settings.timeframe,
                trade=trade,
            )
        except Exception:
            # Trading must not fail merely because the dashboard journal cannot be written.
            pass
        self.position = Position()
        self.entry_notional = 0.0
        self.position_entry_time = None
        self._previous_exit_bar = self.last_exit_bar
        self._exit_signal_bar_time = None
        # Only an exact, verified exchange TP/SL fill may use the backtest's
        # close-bar exception. Unknown fills and emergency/manual exits wait.
        if (self.live and reason in {"TP", "SL"} and exit_time
                and (metadata or {}).get("fill_exact") is True
                and (metadata or {}).get("close_bar_reentry_allowed", True)):
            try:
                stamp = pd.Timestamp(exit_time)
                stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
                unit = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[self.settings.timeframe[-1]]
                seconds = int(self.settings.timeframe[:-1]) * unit
                if seconds > 0:
                    self._exit_signal_bar_time = datetime.fromtimestamp(
                        int(stamp.timestamp()) // seconds * seconds, timezone.utc
                    )
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
        self.last_exit_bar = self.bar_number
        self._external_flat_notified = False
        if self.live:
            self._notify_closed_trade(trade)
        return trade

    def _close(self, price: float, reason: str) -> None:
        if self.position.flat or self.position.entry_price is None:
            return
        qty = abs(self.position.size)
        side = self.position.side
        exit_price = price
        if self.live:
            order = self.adapter.market_order(self.settings.symbol, "sell" if side == "LONG" else "buy", qty, reduce_only=True)
            if not order:
                self.safety.fail("EXIT_ORDER_EMPTY_RESPONSE")
                return
            exit_price = float(order.get("average") or order.get("price") or price)
        if self.live:
            exchange_pos = self._confirm_live_flat()
            if exchange_pos.get("side") != "FLAT" or float(exchange_pos.get("size") or 0) > 1e-9:
                self.safety.fail("EXIT_ORDER_DID_NOT_FLATTEN_POSITION")
                self._notify_live(
                    "🚨 실거래 청산 확인 실패",
                    심볼=self.settings.symbol,
                    방향=side,
                    요청수량=f"{qty:.8f}",
                    사유=reason,
                    안내="거래소 포지션이 FLAT이 아니므로 서버가 안전중지되었습니다.",
                )
                return
            # Only remove leftover plans after the exchange confirms FLAT. If a
            # market close is delayed or partial, its existing TP/SL stays live.
            self.adapter.cancel_protection(self.settings.symbol)
        self._finalize_closed_trade(exit_price, reason)

    def _normalized_live_volume(self, df) -> pd.Series | None:
        if not (self.settings.use_four_crypto_exchanges and self.adapter.asset_class == "crypto"):
            return None
        try:
            sources = self.adapter.fetch_volume_sources(self.settings.symbol, self.settings.timeframe, len(df))
        except Exception:
            sources = {}
        if set(sources) != self.REQUIRED_VOLUME_SOURCES:
            return pd.Series(0.0, index=df.index, dtype=float)
        ratio = normalize_exchange_volume(sources, self.settings.volume_lookback, required_sources=4)
        return ratio.reindex(df.index).fillna(0.0)

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
            if self.safety.stale(datetime.now(timezone.utc), effective_stale_seconds(self.settings.timeframe, self.settings.stale_data_seconds)):
                self.safety.fail("STALE_MARKET_DATA")
        if self.safety.halted:
            return self._halted_state(df)
        return self.last_state

    def step(self, df, precomputed: dict[str, float] | None = None):
        if len(df.index) == 0:
            return self.strategy._not_ready(self.settings.symbol, self.settings.timeframe, "NOT_ENOUGH_DATA", df).state

        bar_timestamp = df.index[-1]
        if self.last_processed_timestamp is not None and bar_timestamp == self.last_processed_timestamp:
            return self._live_heartbeat(df) if self.live else self.last_state

        self.last_processed_timestamp = bar_timestamp
        self.current_bar_time = bar_timestamp.isoformat() if hasattr(bar_timestamp, "isoformat") else str(bar_timestamp)
        self.bar_number += 1
        if self.live:
            self._initialize_live()
            self._reconcile_live()
            if self.safety.halted:
                return self._halted_state(df)

        # Backtest event order: the exit candle uses the PREVIOUS exit cooldown;
        # later candles use this exit. Match by exchange fill time, not poll time.
        # A heartbeat may detect the fill before this completed candle arrives.
        exit_bar_for_signal = self.last_exit_bar
        same_exit_candle = (
            self.live and self.position.flat and self._exit_signal_bar_time is not None
            and pd.Timestamp(bar_timestamp) == pd.Timestamp(self._exit_signal_bar_time)
        )
        if same_exit_candle:
            self.last_exit_bar = self.bar_number
            exit_bar_for_signal = self._previous_exit_bar
        bars_since_entry = None if self.last_entry_bar is None else self.bar_number - self.last_entry_bar
        bars_since_exit = None if exit_bar_for_signal is None else self.bar_number - exit_bar_for_signal
        normalized_volume = self._normalized_live_volume(df) if precomputed is None else None
        result = self.strategy.evaluate(df, self.settings.symbol, self.settings.timeframe, self.position, bars_since_entry, bars_since_exit, normalized_volume, precomputed)
        price = float(df.close.iloc[-1])
        if self.live:
            ts = bar_timestamp.to_pydatetime() if hasattr(bar_timestamp, "to_pydatetime") else bar_timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            self.safety.record_data(ts)
            if self.safety.stale(datetime.now(timezone.utc), effective_stale_seconds(self.settings.timeframe, self.settings.stale_data_seconds)):
                self.safety.fail("STALE_MARKET_DATA")
                return self._halted_state(df)
        # LIVE exits are owned by Bitget's last-traded-price market TP/SL.
        # Evaluating a completed candle here would be slower and could submit a
        # second close order after an exchange-side protection already fired.
        if not self.live and not self.position.flat and self.position.tp is not None and self.position.sl is not None:
            hit_tp = (self.position.side == "LONG" and price >= self.position.tp) or (self.position.side == "SHORT" and price <= self.position.tp)
            hit_sl = (self.position.side == "LONG" and price <= self.position.sl) or (self.position.side == "SHORT" and price >= self.position.sl)
            if hit_tp or hit_sl:
                self._close(price, "TP" if hit_tp else "SL")
        signal = result.signal.side
        market_regime, volatility_regime, regime_risk = self._adaptive_regime(df)
        self.current_market_regime = market_regime
        self.current_volatility_regime = volatility_regime
        self.current_regime_risk_multiplier = regime_risk
        if bool(getattr(self.settings, "adaptive_regime_enabled", False)):
            if market_regime == "상승장" and signal == "SHORT":
                signal = None
            elif market_regime == "하락장" and signal == "LONG":
                signal = None
            elif market_regime == "미분류":
                signal = None
        can_pyramid = (
            self.position.entries < self.settings.max_pyramiding
            and (volatility_regime != "고변동성" or self.position.entries < 1)
        )
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
        result.state.stats = {
            "closed_trades": float(self.closed_trades),
            "win_rate": self.winning_trades / self.closed_trades * 100 if self.closed_trades else 0.0,
            "profit_factor": self.gross_profit / self.gross_loss if self.gross_loss else None,
            "realized_pnl": self.realized_pnl,
            "return_percent": self.realized_pnl / self.settings.initial_capital * 100 if self.settings.initial_capital else 0.0,
            "open_pnl": open_pnl,
            "equity": display_equity,
            "live_halted": self.safety.halted,
            "live_safety_reason": self.safety.reason,
            "protection_ok": self.safety.protection_ok,
            "market_regime": self.current_market_regime,
            "volatility_regime": self.current_volatility_regime,
            "regime_risk_multiplier": self.current_regime_risk_multiplier,
            "adaptive_regime_enabled": bool(getattr(self.settings, "adaptive_regime_enabled", False)),
        }
        self.last_state = result.state
        self.equity_curve.append({"bar": self.bar_number, "timestamp": self.current_bar_time, "equity": display_equity})
        return result.state

    def _halted_state(self, df):
        state = self.strategy._not_ready(self.settings.symbol, self.settings.timeframe, f"LIVE_HALTED:{self.safety.reason}", df).state
        state.position = self.position
        state.stats = {
            "closed_trades": float(self.closed_trades),
            "win_rate": self.winning_trades / self.closed_trades * 100 if self.closed_trades else 0.0,
            "profit_factor": self.gross_profit / self.gross_loss if self.gross_loss else None,
            "realized_pnl": self.realized_pnl,
            "open_pnl": self._open_pnl(float(df.close.iloc[-1])) if len(df) else 0.0,
            "equity": self.adapter.equity() if self.live else self.settings.initial_capital + self.realized_pnl,
            "live_halted": True,
            "live_safety_reason": self.safety.reason,
            "protection_ok": self.safety.protection_ok,
        }
        self.last_state = state
        return state
