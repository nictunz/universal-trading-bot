from __future__ import annotations

import time
from datetime import datetime, timezone

from universal_bot.adapters.bitget_elite import AmbiguousOrderResult
from universal_bot.engine import TradingEngine as _BaseTradingEngine
from universal_bot.models import Position


class TradingEngine(_BaseTradingEngine):
    """Runtime engine with LIVE-only Elite sizing and chart event journaling.

    Backtest/PAPER sizing stays on ORDER_PERCENT_OF_EQUITY. When LIVE execution
    uses the Bitget Elite profile, each entry uses current available USDT times
    LIVE_ENTRY_MULTIPLIER and the position is capped at
    LIVE_MAX_ENTRIES_PER_POSITION. After every fill the bot re-reads Bitget and
    installs one full-position TP/SL pair at the original signal-based prices.
    """

    def __init__(self, settings, adapter, strategy):
        super().__init__(settings, adapter, strategy)
        self._live_entry_equity_basis: float | None = None
        self._active_tp_pct: float | None = None
        self._active_sl_pct: float | None = None
        self._active_tp_price: float | None = None
        self._active_sl_price: float | None = None
        self._event_no = 0
        self._active_execution_id: str | None = None
        # Entry and exit messages share one notifier, so a close can emit only
        # one Discord message even when the runtime wraps the base engine.
        self.notifier = self.discord

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
        execution: dict | None = None,
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
                    "execution": execution or {},
                },
            }
        )

    def _execution_signal_id(self, side: str) -> str:
        bar = self.current_bar_time or "unknown-bar"
        return f"{self.settings.symbol}|{self.settings.timeframe}|{bar}|{side}|ENTRY"

    def _claim_live_execution(self, side: str, requested_qty: float, reference_price: float) -> str | None:
        signal_id = self._execution_signal_id(side)
        claimed = self.trade_history.claim_execution_once(
            mode="LIVE",
            symbol=self.settings.symbol,
            timeframe=self.settings.timeframe,
            signal_id=signal_id,
            side=side,
            requested_qty=requested_qty,
            metadata={"reference_price": reference_price, "bar_time": self.current_bar_time},
        )
        if not claimed:
            self._record_runtime_event({
                "event_time": self.current_bar_time or datetime.now(timezone.utc).isoformat(),
                "event_type": "EXECUTION_SKIPPED",
                "side": side,
                "reason": "DUPLICATE_SIGNAL_ID",
                "metadata": {"signal_id": signal_id},
            })
            return None
        self._active_execution_id = signal_id
        return signal_id

    def _finish_live_execution(self, signal_id: str, status: str, **quality) -> None:
        try:
            try:
                self.trade_history.update_execution_claim(
                    mode="LIVE",
                    symbol=self.settings.symbol,
                    timeframe=self.settings.timeframe,
                    signal_id=signal_id,
                    status=status,
                    filled_qty=quality.get("filled_qty"),
                    avg_fill_price=quality.get("avg_fill_price"),
                    slippage_percent=quality.get("slippage_percent"),
                    child_orders=quality.get("child_orders"),
                    metadata=quality,
                )
            except Exception:
                # A filled/protected exchange position must not be disturbed by
                # an observability-only SQLite failure.
                pass
        finally:
            self._active_execution_id = None

    @staticmethod
    def _execution_quality(order: dict, reference_price: float, side: str) -> dict:
        requested = float(order.get("requested") or 0.0)
        filled = float(order.get("filled") or order.get("amount") or 0.0)
        average = float(order.get("average") or order.get("price") or 0.0)
        signed_slippage = 0.0
        if reference_price > 0 and average > 0:
            raw = (average / reference_price - 1.0) * 100.0
            signed_slippage = raw if side == "LONG" else -raw
        children = order.get("children") or []
        return {
            "execution_mode": order.get("execution_mode") or "market",
            "order_status": order.get("status"),
            "requested_qty": requested,
            "filled_qty": filled,
            "unfilled_qty": float(order.get("unfilled") or max(0.0, requested - filled)),
            "fill_ratio": filled / requested if requested > 0 else None,
            "reference_price": float(reference_price),
            "avg_fill_price": average or None,
            "slippage_percent": signed_slippage,
            "child_orders": int(order.get("child_order_count") or len(children)),
            "elapsed_seconds": order.get("elapsed_seconds"),
            "protection_ok": order.get("protection_ok"),
            "order_ids": [str(x.get("id")) for x in children if x.get("id")],
        }

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
        metadata = dict(trade.get("metadata") or {})
        source = str(metadata.get("fill_source") or "order-response")
        quality = "거래소 체결내역" if metadata.get("fill_exact", True) else "체결조회 지연 · 보수적 기록"
        self.notifier.send_async(
            "\n".join(
                [
                    f"{icon} [ELITE {reason}] {self.settings.symbol} {trade.get('side') or ''}",
                    f"평균 진입가: {float(trade.get('avg_entry_price') or trade.get('entry_price') or 0):.6f}",
                    f"청산가: {float(trade.get('exit_price') or 0):.6f}",
                    f"수량: {float(trade.get('qty') or 0):.8f}",
                    f"손익: {pnl:+.6f} USDT ({pct:+.3f}%)",
                    f"체결확인: {quality} ({source})",
                ]
            )
        )

    def _notify_closed_trade(self, trade: dict) -> None:
        self._notify_exit(trade)

    @staticmethod
    def _timestamp_ms(value: str | None) -> int | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _iso_from_ms(value: int | float | None) -> str | None:
        if not value:
            return None
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).isoformat()
        except (OverflowError, TypeError, ValueError):
            return None

    def _infer_external_exit_reason(self, fill: dict | None, exit_price: float) -> str:
        raw = (fill or {}).get("raw") or []
        text = " ".join(
            str(row.get(key) or "").lower()
            for row in raw
            for key in ("clientOid", "side", "tradeSide", "delegateType", "orderSource", "planType")
        )
        if "utb-tp" in text or "take_profit" in text or "take-profit" in text or "stop_profit" in text:
            return "TP"
        if "utb-sl" in text or "stop_loss" in text or "stop-loss" in text:
            return "SL"
        targets = {
            "TP": float(self.position.tp) if self.position.tp is not None else None,
            "SL": float(self.position.sl) if self.position.sl is not None else None,
        }
        available = {key: value for key, value in targets.items() if value and value > 0}
        if available and exit_price > 0:
            return min(available, key=lambda key: abs(exit_price - float(available[key])))
        return "EXCHANGE_EXIT"

    def _record_exit_event(self, trade: dict) -> None:
        metadata = trade.setdefault("metadata", {})
        if metadata.get("runtime_event_recorded"):
            return
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
                "reason": trade.get("reason"),
                "metadata": {
                    "fill_source": metadata.get("fill_source"),
                    "fill_exact": metadata.get("fill_exact"),
                    "order_id": metadata.get("order_id"),
                },
            }
        )
        metadata["runtime_event_recorded"] = True

    def _handle_external_flat(self, exchange_position: dict) -> bool:
        """Synchronize a Bitget-side TP/SL fill without halting the strategy."""
        if self.position.flat:
            return True
        side = str(self.position.side or "")
        avg_entry = float(self.position.entry_price or 0.0)
        since_ms = self._timestamp_ms(self.position_entry_time)
        if since_ms is not None:
            since_ms = max(0, since_ms - 60_000)

        fill = None
        if hasattr(self.adapter, "recent_close_fill"):
            for attempt in range(5):
                try:
                    fill = self.adapter.recent_close_fill(
                        self.settings.symbol,
                        side,
                        since_ms=since_ms,
                    )
                except Exception:
                    fill = None
                if fill:
                    break
                if attempt < 4:
                    time.sleep(0.15)

        exact = bool(fill and float(fill.get("price") or 0.0) > 0)
        exit_price = float(fill.get("price") or 0.0) if fill else 0.0
        # If fill history is briefly unavailable, synchronize safely and record
        # zero PnL instead of inventing an exchange price. Metadata and Discord
        # make the conservative fallback explicit.
        if exit_price <= 0:
            exit_price = avg_entry
        reason = self._infer_external_exit_reason(fill, exit_price) if exact else "EXCHANGE_EXIT"
        # A price close to TP/SL alone does not prove the exit was protection:
        # manual and emergency market closes must not gain a reentry exception.
        fill_tags = " ".join(
            str(row.get(key) or "").lower()
            for row in (fill or {}).get("raw", [])
            for key in ("clientOid", "delegateType", "orderSource", "planType")
        )
        protection_fill = any(tag in fill_tags for tag in (
            "utb-tp", "utb-sl", "take_profit", "take-profit", "stop_profit", "stop_loss", "stop-loss"
        ))
        metadata = {
            "fill_source": (fill or {}).get("source") or "fill-history-unavailable",
            "fill_exact": exact,
            "close_bar_reentry_allowed": exact and protection_fill,
            "order_id": (fill or {}).get("order_id"),
            "client_oid": (fill or {}).get("client_oid"),
            "exchange_fill_qty": (fill or {}).get("qty"),
        }
        try:
            self.adapter.cancel_protection(self.settings.symbol)
        except Exception:
            # The position is already flat; leftover bot-owned reduce-only plans
            # are retried on later maintenance and must not corrupt state sync.
            pass
        trade = self._finalize_closed_trade(
            exit_price,
            reason,
            exit_time=self._iso_from_ms((fill or {}).get("time_ms")),
            fee=float((fill or {}).get("fee") or 0.0),
            reported_pnl=(fill or {}).get("realized_pnl"),
            metadata=metadata,
        )
        if trade is not None:
            self._record_exit_event(trade)
        self._live_entry_equity_basis = None
        self._active_tp_pct = None
        self._active_sl_pct = None
        self._active_tp_price = None
        self._active_sl_price = None
        self.safety.protection_ok = True
        return self.position.flat

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
            self._active_tp_price = None
            self._active_sl_price = None

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

    def _position_after_fill(
        self,
        side: str,
        fallback_qty: float,
        fallback_notional: float,
        *,
        minimum_size: float = 0.0,
    ) -> dict:
        last = None
        for _ in range(7):
            last = self.adapter.position(self.settings.symbol)
            if (
                last.get("side") == side
                and float(last.get("size") or 0.0) > float(minimum_size) + 1e-9
                and float(last.get("entry_price") or 0.0) > 0
            ):
                return last
            time.sleep(0.15)
        # Do not pretend an exchange position is verified. Return a marked
        # fallback only so the emergency-close path has a quantity to use.
        qty = max(0.0, float(fallback_qty))
        avg = float(fallback_notional) / qty if qty > 0 and fallback_notional > 0 else 0.0
        return {
            "side": last.get("side") if isinstance(last, dict) else "UNKNOWN",
            "size": qty,
            "entry_price": avg,
            "verified": False,
        }

    def _flatten_full_position_after_protection_failure(self, side: str, total_qty: float) -> None:
        ambiguous: AmbiguousOrderResult | None = None
        try:
            close_side = "sell" if side == "LONG" else "buy"
            self.adapter.market_order(
                self.settings.symbol,
                close_side,
                float(total_qty),
                reduce_only=True,
            )
        except AmbiguousOrderResult as exc:
            # The close may already have reached Bitget. Never send a second
            # close order; resolve it from the position state below.
            ambiguous = exc
        except Exception as exc:
            self.safety.fail(f"PROTECTION_REPLACE_FLATTEN_FAILED: {type(exc).__name__}: {exc}")
            return

        exchange_pos: dict = {}
        for attempt in range(7):
            try:
                exchange_pos = self.adapter.position(self.settings.symbol)
            except Exception:
                exchange_pos = {}
            if (
                exchange_pos.get("side") == "FLAT"
                and float(exchange_pos.get("size") or 0.0) <= 1e-9
            ):
                # This also journals the emergency close and sends exactly one
                # exit notification when an internal position was established.
                self._handle_external_flat(exchange_pos)
                return
            if attempt < 6:
                time.sleep(0.15)

        if ambiguous is not None:
            self.safety.fail(
                f"PROTECTION_REPLACE_FLATTEN_OUTCOME_UNKNOWN clientOid={ambiguous.client_oid}"
            )
        else:
            self.safety.fail("PROTECTION_REPLACE_FLATTEN_DID_NOT_CLOSE_POSITION")

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
        before_size = abs(float(self.position.size))
        before_notional = float(self.entry_notional)
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

        # Match backtest semantics: freeze TP/SL at the first signal close.
        # Partial IOC fills may change only protected quantity and average entry.
        signal_tp, signal_sl = self._prices_from_average(
            side, price, active_tp_pct, active_sl_pct
        )
        if self.position.flat:
            self._active_tp_price = signal_tp
            self._active_sl_price = signal_sl
        fixed_tp = float(self._active_tp_price or signal_tp)
        fixed_sl = float(self._active_sl_price or signal_sl)

        if not self.safety.can_open:
            return

        execution_id = self._claim_live_execution(side, amount, price)
        if execution_id is None:
            return

        order_side = "buy" if side == "LONG" else "sell"
        recovered_exchange_pos = None
        try:
            if (
                str(self.settings.live_entry_execution_mode).strip().lower() == "adaptive_ioc"
                and hasattr(self.adapter, "adaptive_ioc_entry")
            ):
                order = self.adapter.adaptive_ioc_entry(
                    self.settings.symbol,
                    order_side,
                    amount,
                    reference_price=price,
                    tp_pct=active_tp_pct,
                    sl_pct=active_sl_pct,
                    fixed_tp_price=fixed_tp,
                    fixed_sl_price=fixed_sl,
                    max_adverse_slippage_percent=float(
                        self.settings.live_entry_max_adverse_slippage_percent
                    ),
                    max_child_orders=int(self.settings.live_entry_max_child_orders),
                    execution_window_seconds=float(
                        self.settings.live_entry_execution_window_seconds
                    ),
                    depth_participation=float(
                        self.settings.live_entry_depth_participation
                    ),
                    child_pause_seconds=float(
                        self.settings.live_entry_child_pause_seconds
                    ),
                )
            else:
                order = self.adapter.market_order(
                    self.settings.symbol,
                    order_side,
                    amount,
                    tp_price=fixed_tp,
                    sl_price=fixed_sl,
                )
        except AmbiguousOrderResult as exc:
            # The exchange may have filled the request despite a lost HTTP
            # response. Detect the position delta; never submit a second entry.
            recovered_exchange_pos = self._position_after_fill(
                side,
                before_size + amount,
                before_notional + intended_notional,
                minimum_size=before_size,
            )
            recovered_size = float(recovered_exchange_pos.get("size") or 0.0)
            if (
                recovered_exchange_pos.get("side") != side
                or recovered_size <= before_size + 1e-9
                or recovered_exchange_pos.get("verified", True) is False
            ):
                self.safety.fail(f"ENTRY_ORDER_OUTCOME_UNKNOWN clientOid={exc.client_oid}")
                self._notify_live(
                    "🚨 진입 주문 결과 확인 불가",
                    심볼=self.settings.symbol,
                    clientOid=exc.client_oid,
                    안내="동일 주문을 재전송하지 않고 안전중지했습니다. Bitget 주문/포지션을 확인하세요.",
                )
                self._finish_live_execution(
                    execution_id,
                    "OUTCOME_UNKNOWN",
                    filled_qty=0.0,
                    reference_price=price,
                    client_oid=exc.client_oid,
                )
                return
            delta_qty = recovered_size - before_size
            recovered_avg = float(recovered_exchange_pos.get("entry_price") or price)
            delta_notional = recovered_size * recovered_avg - before_notional
            recovered_fill_price = delta_notional / delta_qty if delta_qty > 0 and delta_notional > 0 else recovered_avg
            order = {
                "id": exc.client_oid,
                "clientOid": exc.client_oid,
                "filled": delta_qty,
                "average": recovered_fill_price,
                "status": "position-recovered",
                "recovered_by_position": True,
            }
        except Exception as exc:
            self._finish_live_execution(
                execution_id,
                "ERROR_UNKNOWN",
                filled_qty=0.0,
                reference_price=price,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        if not order:
            self.safety.fail("ENTRY_ORDER_EMPTY_RESPONSE")
            self._finish_live_execution(execution_id, "EMPTY_RESPONSE", filled_qty=0.0)
            return

        order.setdefault("requested", amount)
        order.setdefault("unfilled", max(0.0, amount - float(order.get("filled") or 0.0)))
        execution_quality = self._execution_quality(order, price, side)
        actual_amount = float(order.get("filled") or order.get("amount") or 0.0)
        if actual_amount <= 0:
            # IOC may legitimately expire without a fill. Never invent the
            # requested quantity and never fall back to an uncapped market order.
            if self.position.flat:
                self._live_entry_equity_basis = None
                self._active_tp_pct = None
                self._active_sl_pct = None
                self._active_tp_price = None
                self._active_sl_price = None
            self._finish_live_execution(execution_id, "UNFILLED", **execution_quality)
            return
        actual_price = float(order.get("average") or order.get("price") or price)
        signed_amount = actual_amount if side == "LONG" else -actual_amount

        if self.position.flat:
            self.position = Position(
                side=side,
                size=signed_amount,
                entry_price=actual_price,
                tp=fixed_tp,
                sl=fixed_sl,
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

        fallback_qty = abs(float(self.position.size))
        exchange_pos = recovered_exchange_pos or self._position_after_fill(
            side,
            fallback_qty,
            self.entry_notional,
            minimum_size=before_size,
        )
        verified_exchange_position = (
            exchange_pos.get("side") == side
            and float(exchange_pos.get("size") or 0.0) > 0
            and float(exchange_pos.get("entry_price") or 0.0) > 0
            and exchange_pos.get("verified", True) is not False
        )
        total_qty = abs(float(exchange_pos.get("size") or fallback_qty))
        avg_entry = float(exchange_pos.get("entry_price") or 0.0)

        if not verified_exchange_position or total_qty <= 0 or avg_entry <= 0:
            self._flatten_full_position_after_protection_failure(side, max(total_qty, fallback_qty))
            self.safety.fail("ENTRY_FILLED_BUT_EXCHANGE_POSITION_NOT_VERIFIED")
            self._finish_live_execution(
                execution_id,
                "FLATTENED_UNVERIFIED",
                **execution_quality,
            )
            return

        # Use Bitget's final position delta for the entry journal/notification,
        # even when the immediate order response did not yet contain fill data.
        exchange_delta_qty = total_qty - before_size
        exchange_delta_notional = total_qty * avg_entry - before_notional
        if exchange_delta_qty > 1e-9:
            actual_amount = exchange_delta_qty
            if exchange_delta_notional > 0:
                actual_price = exchange_delta_notional / exchange_delta_qty

        full_tp, full_sl = fixed_tp, fixed_sl

        if not hasattr(self.adapter, "replace_full_protection"):
            self._flatten_full_position_after_protection_failure(side, total_qty)
            self.safety.fail("FULL_POSITION_PROTECTION_REPLACE_UNSUPPORTED")
            self._finish_live_execution(
                execution_id,
                "FLATTENED_NO_PROTECTION",
                **execution_quality,
            )
            return
        adaptive_already_protected = (
            str(order.get("execution_mode") or "") == "adaptive_ioc"
            and bool(order.get("protection_ok"))
            and abs(float(order.get("protected_qty") or 0.0) - total_qty) <= 1e-9
            and abs(float(order.get("fixed_tp") or 0.0) - full_tp) <= 1e-9
            and abs(float(order.get("fixed_sl") or 0.0) - full_sl) <= 1e-9
        )
        if adaptive_already_protected:
            # The final IOC child already installed and verified this exact
            # quantity/pair; avoid a redundant private-API replacement cycle.
            replaced = {"ok": True, "source": "adaptive_ioc_final_verification"}
        else:
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
                f"FULL_POSITION_PROTECTION_REPLACE_FAILED: {replaced.get('reason', replaced)}"
            )
            self._finish_live_execution(
                execution_id,
                "FLATTENED_PROTECTION_FAILED",
                **execution_quality,
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
            execution=execution_quality,
        )
        self._finish_live_execution(
            execution_id,
            "PROTECTED",
            **{**execution_quality, "protected_qty": total_qty, "tp": full_tp, "sl": full_sl},
        )
        self._notify_entry(side=side, fill_price=actual_price, qty=actual_amount)
        self.safety.reconcile(self._internal_position_dict(), exchange_pos)

    def _close(self, price: float, reason: str) -> None:
        before_trades = len(self.trade_log)
        try:
            super()._close(price, reason)
        except AmbiguousOrderResult as exc:
            exchange_pos = None
            for _ in range(7):
                exchange_pos = self.adapter.position(self.settings.symbol)
                if exchange_pos.get("side") == "FLAT" and float(exchange_pos.get("size") or 0.0) <= 1e-9:
                    self._handle_external_flat(exchange_pos)
                    break
                time.sleep(0.15)
            else:
                self.safety.fail(f"EXIT_ORDER_OUTCOME_UNKNOWN clientOid={exc.client_oid}")
                self._notify_live(
                    "🚨 청산 주문 결과 확인 불가",
                    심볼=self.settings.symbol,
                    clientOid=exc.client_oid,
                    안내="중복 청산을 보내지 않고 안전중지했습니다. Bitget 포지션을 확인하세요.",
                )
        if len(self.trade_log) > before_trades:
            trade = self.trade_log[-1]
            self._record_exit_event(trade)
        if self.position.flat:
            self._live_entry_equity_basis = None
            self._active_tp_pct = None
            self._active_sl_pct = None
            self._active_tp_price = None
            self._active_sl_price = None
