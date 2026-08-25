from __future__ import annotations

import time
from typing import Any

from universal_bot.adapters.bitget_elite import BitgetEliteAdapter as _ClassicBitgetEliteAdapter


class BitgetEliteAdapter(_ClassicBitgetEliteAdapter):
    """Runtime wrapper for the Classic v2 Elite adapter.

    Keeps the proven Classic v2 order/account implementation, but adds explicit
    leverage synchronisation plus bot-owned TP/SL management for LIVE trading.
    Preflight remains read-only: ``configure_live`` only verifies leverage
    equality, while the runtime calls ``ensure_leverage`` before arming a symbol.
    """

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        leverage = int(leverage)
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        contract = self._contract(symbol)
        max_leverage = int(float(contract.get("maxLever") or 0))
        if max_leverage and leverage > max_leverage:
            raise RuntimeError(
                f"requested leverage {leverage} exceeds Bitget maximum {max_leverage} for {self._symbol_id(symbol)}"
            )
        data = self._request(
            "POST",
            "/api/v2/mix/account/set-leverage",
            body={
                "symbol": self._symbol_id(symbol),
                "productType": self.PRODUCT_TYPE,
                "marginCoin": self.MARGIN_COIN,
                "leverage": str(leverage),
            },
        )
        return dict(data or {}) if isinstance(data, dict) else {"result": data}

    @staticmethod
    def _account_leverage(account: dict) -> float:
        return float(
            account.get("crossedMarginLeverage")
            or account.get("crossedLever")
            or account.get("leverage")
            or 0.0
        )

    def ensure_leverage(self, symbol: str, leverage: int) -> dict:
        leverage = int(leverage)
        before_account = self.account_info(symbol)
        before = self._account_leverage(before_account)
        if abs(before - leverage) < 1e-9:
            return {
                "ok": True,
                "symbol": self._symbol_id(symbol),
                "requested_leverage": leverage,
                "before": before,
                "after": before,
                "changed": False,
            }

        self.set_leverage(symbol, leverage)
        time.sleep(0.25)
        after_account = self.account_info(symbol)
        after = self._account_leverage(after_account)
        ok = abs(after - leverage) < 1e-9
        return {
            "ok": ok,
            "symbol": self._symbol_id(symbol),
            "requested_leverage": leverage,
            "before": before,
            "after": after,
            "changed": True,
            "reason": None if ok else f"Bitget leverage remained {after} after requesting {leverage}",
        }

    def configure_live(
        self,
        symbol: str,
        leverage: int,
        margin_mode: str,
        require_one_way: bool = False,
    ) -> dict:
        result = super().configure_live(symbol, leverage, margin_mode, require_one_way)
        if not result.get("ok"):
            return result
        actual = float(result.get("account_leverage") or 0.0)
        requested = float(leverage)
        if abs(actual - requested) >= 1e-9:
            return {
                **result,
                "ok": False,
                "reason": f"Bitget leverage mismatch: account={actual:g}x requested={requested:g}x",
            }
        return result

    @staticmethod
    def _is_bot_plan(order: dict[str, Any]) -> bool:
        """Only manage plans created by this bot; never cancel manual user plans."""
        client_oid = str(order.get("clientOid") or "")
        return client_oid.startswith("utb-")

    def _bot_plan_orders(self, symbol: str) -> list[dict[str, Any]]:
        return [x for x in self._pending_plan_orders(symbol) if self._is_bot_plan(x)]

    def _cancel_plan(self, symbol: str, order: dict[str, Any]) -> None:
        order_id = order.get("orderId")
        client_oid = order.get("clientOid")
        if not order_id and not client_oid:
            return
        body: dict[str, Any] = {
            "symbol": self._symbol_id(symbol),
            "productType": self.PRODUCT_TYPE,
            "marginCoin": self.MARGIN_COIN,
            "planType": str(order.get("planType") or "normal_plan"),
        }
        if order_id:
            body["orderId"] = str(order_id)
        else:
            body["clientOid"] = str(client_oid)
        self._request("POST", "/api/v2/mix/order/cancel-plan-order", body=body)

    def protection_status(self, symbol: str) -> dict[str, Any]:
        """Verify at least two active TP/SL plans owned by this bot."""
        last_error: Exception | None = None
        for _ in range(5):
            try:
                orders = self._bot_plan_orders(symbol)
                active = [
                    x for x in orders
                    if str(x.get("triggerPrice") or "").strip() not in {"", "0"}
                ]
                if len(active) >= 2:
                    return {
                        "ok": True,
                        "supported": True,
                        "count": len(active),
                        "orders": active,
                    }
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        if last_error is not None:
            return {
                "ok": False,
                "supported": True,
                "reason": f"bot protection verification failed: {last_error}",
            }
        return {
            "ok": False,
            "supported": True,
            "count": 0,
            "reason": "both bot-owned Elite TP and SL were not verified",
        }

    def cancel_protection(self, symbol: str) -> None:
        """Cancel only TP/SL plans created by this bot."""
        for order in self._bot_plan_orders(symbol):
            try:
                self._cancel_plan(symbol, order)
            except Exception:
                pass

    def replace_full_protection(
        self,
        symbol: str,
        position_side: str,
        total_amount: float,
        tp_price: float,
        sl_price: float,
    ) -> dict[str, Any]:
        """Replace tranche protections with one full-position TP and SL pair.

        New full-position orders are placed *before* old bot orders are removed,
        avoiding an intentional unprotected gap during a pyramiding update. The
        old snapshot is then cancelled, leaving only the new full-position pair.
        """
        side = str(position_side).strip().lower()
        if side not in {"long", "short"}:
            raise ValueError(f"invalid position side for protection: {position_side}")
        qty = self._qty(symbol, float(total_amount))
        old_orders = self._bot_plan_orders(symbol)

        created = self._place_protection(
            symbol,
            side,
            qty,
            float(tp_price),
            float(sl_price),
        )
        if len(created) < 2:
            return {
                "ok": False,
                "reason": "Bitget did not return both replacement TP and SL plans",
                "created": created,
            }

        # Cancel only the plans that existed before the replacement was placed.
        for order in old_orders:
            try:
                self._cancel_plan(symbol, order)
            except Exception:
                # Verification below is authoritative. A leftover old reduce-only
                # plan is safer than deleting the newly created full protection.
                pass

        status = self.protection_status(symbol)
        return {
            "ok": bool(status.get("ok")),
            "symbol": self._symbol_id(symbol),
            "total_qty": qty,
            "tp_price": float(tp_price),
            "sl_price": float(sl_price),
            "old_plan_count": len(old_orders),
            "created_count": len(created),
            "verification": status,
        }
