from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from universal_bot.adapters.bitget_elite_runtime import BitgetEliteAdapter as _ClassicRuntimeAdapter


class BitgetUtaAdapter(_ClassicRuntimeAdapter):
    """Bitget Unified Trading Account (UTA) v3 adapter.

    Public market data still uses the existing hybrid adapter. Authenticated
    account, position, order and TP/SL calls use Bitget UTA v3 endpoints while
    retaining the engine-facing interface used by the proven Classic adapter.
    """

    CATEGORY = "USDT-FUTURES"
    API_FAMILY = "uta-v3"

    def _contract(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        cached = self._contract_cache.get(sid)
        if cached is not None:
            return cached
        rows = self._public_get(
            "/api/v3/market/instruments",
            {"category": self.CATEGORY, "symbol": sid},
        ) or []
        if not rows:
            raise RuntimeError(f"Bitget UTA instrument not found: {sid}")
        contract = dict(rows[0])
        status = str(contract.get("status") or "").lower()
        if status not in {"online", "normal"}:
            raise RuntimeError(f"Bitget UTA instrument is not API-tradable: {sid} status={status}")
        self._contract_cache[sid] = contract
        return contract

    def _qty(self, symbol: str, amount: float) -> str:
        contract = self._contract(symbol)
        decimals = int(contract.get("quantityPrecision") or 0)
        step = str(contract.get("quantityMultiplier") or "0")
        text = self._floor_to_step(amount, step, decimals)
        qty = Decimal(text)
        minimum = Decimal(str(contract.get("minOrderQty") or "0"))
        if qty <= 0 or (minimum > 0 and qty < minimum):
            raise RuntimeError(f"order quantity {text} is below Bitget UTA minimum {minimum}")
        max_market = Decimal(str(contract.get("maxMarketOrderQty") or "0"))
        if max_market > 0 and qty > max_market:
            raise RuntimeError(f"order quantity {text} exceeds Bitget UTA market maximum {max_market}")
        return text

    def _price(self, symbol: str, price: float) -> str:
        contract = self._contract(symbol)
        decimals = int(contract.get("pricePrecision") or 0)
        step = str(contract.get("priceMultiplier") or Decimal(1).scaleb(-decimals))
        return self._floor_to_step(price, step, decimals)

    def account_info(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        data = self._request("GET", "/api/v3/account/settings") or {}
        info = dict(data)
        hold_mode = str(info.get("holdMode") or "").lower()
        if hold_mode:
            self._account_mode_cache[sid] = hold_mode
        symbol_cfg = next(
            (
                dict(x)
                for x in (info.get("symbolConfigList") or [])
                if str(x.get("category") or "").upper() == self.CATEGORY
                and str(x.get("symbol") or "").upper() == sid
            ),
            {},
        )
        # Preserve the engine-facing Classic field names as aliases.
        info["posMode"] = hold_mode
        if symbol_cfg:
            info["marginMode"] = symbol_cfg.get("marginMode")
            info["leverage"] = symbol_cfg.get("leverage")
            info["crossedMarginLeverage"] = symbol_cfg.get("leverage")
        return info

    @staticmethod
    def _account_leverage(account: dict) -> float:
        return float(account.get("leverage") or account.get("crossedMarginLeverage") or 0.0)

    def configure_live(
        self,
        symbol: str,
        leverage: int,
        margin_mode: str,
        require_one_way: bool = False,
    ) -> dict:
        if not self._credentials_ready():
            return {"ok": False, "supported": True, "reason": "Bitget API credentials are missing"}
        if str(margin_mode).lower() not in {"cross", "crossed"}:
            return {
                "ok": False,
                "supported": True,
                "reason": "UTA bot is configured for crossed margin; set MARGIN_MODE=crossed",
            }
        try:
            sid = self._symbol_id(symbol)
            account = self.account_info(symbol)
            account_mode = str(account.get("accountMode") or "").lower()
            account_level = str(account.get("accountLevel") or "").lower()
            account_margin = str(account.get("marginMode") or "").lower()
            pos_mode = str(account.get("posMode") or "").lower()
            if account_mode not in {"unified", "hybrid"}:
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"Bitget account is not ready for UTA trading (accountMode={account_mode or 'unknown'})",
                }
            if account_margin and account_margin not in {"cross", "crossed"}:
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"Bitget UTA margin mode is {account_margin}, expected crossed",
                }
            if require_one_way and pos_mode != "one_way_mode":
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"LIVE_REQUIRE_ONE_WAY_MODE=true but Bitget UTA account is {pos_mode or 'unknown'}",
                }
            contract = self._contract(symbol)
            actual_leverage = self._account_leverage(account)
            result = {
                "ok": True,
                "supported": True,
                "profile": "elite-uta-v3",
                "api_family": self.API_FAMILY,
                "account_type": "uta",
                "account_mode": account_mode,
                "account_level": account_level,
                "margin_mode": account_margin or "crossed",
                "position_mode": pos_mode or "unknown",
                "requested_leverage": int(leverage),
                "account_leverage": actual_leverage,
                "symbol": sid,
                "contract_min_qty": contract.get("minOrderQty"),
                "contract_max_leverage": contract.get("maxLeverage"),
            }
            if abs(actual_leverage - float(leverage)) >= 1e-9:
                result["ok"] = False
                result["reason"] = (
                    f"Bitget leverage mismatch: account={actual_leverage:g}x requested={float(leverage):g}x"
                )
            return result
        except Exception as exc:
            return {
                "ok": False,
                "supported": True,
                "reason": f"UTA v3 readiness failed: {type(exc).__name__}: {exc}",
            }

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        leverage = int(leverage)
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        contract = self._contract(symbol)
        max_leverage = int(float(contract.get("maxLeverage") or 0))
        if max_leverage and leverage > max_leverage:
            raise RuntimeError(
                f"requested leverage {leverage} exceeds Bitget UTA maximum {max_leverage} for {self._symbol_id(symbol)}"
            )
        data = self._request(
            "POST",
            "/api/v3/account/set-leverage",
            body={
                "category": self.CATEGORY,
                "symbol": self._symbol_id(symbol),
                "leverage": str(leverage),
            },
        )
        return dict(data or {}) if isinstance(data, dict) else {"result": data}

    def equity(self) -> float:
        data = self._request("GET", "/api/v3/account/assets") or {}
        # Keep sizing behavior compatible with Classic: use available USDT,
        # not total multi-asset account equity.
        for asset in data.get("assets") or []:
            if str(asset.get("coin") or "").upper() == self.MARGIN_COIN:
                return float(asset.get("available") or 0.0)
        return 0.0

    def position(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        data = self._request(
            "GET",
            "/api/v3/position/current-position",
            params={"category": self.CATEGORY, "symbol": sid},
        ) or {}
        rows = data.get("list") if isinstance(data, dict) else data
        active = [dict(x) for x in (rows or []) if abs(float(x.get("total") or 0.0)) > 0]
        if len(active) > 1:
            raise RuntimeError(
                f"multiple active hedge positions exist for {sid}; this bot requires at most one active side per symbol"
            )
        if not active:
            return {"side": "FLAT", "size": 0.0, "entry_price": 0.0, "notional": 0.0}
        row = active[0]
        pos_side = str(row.get("posSide") or "").lower()
        side = "LONG" if pos_side == "long" else "SHORT"
        size = abs(float(row.get("total") or 0.0))
        entry = float(row.get("avgPrice") or 0.0)
        mode = str(row.get("holdMode") or "").lower()
        if mode:
            self._account_mode_cache[sid] = mode
        return {
            "side": side,
            "size": size,
            "entry_price": entry,
            "mark_price": float(row.get("markPrice") or 0.0),
            "notional": size * entry,
            "leverage": float(row.get("leverage") or 0.0),
            "margin_mode": row.get("marginMode"),
            "position_mode": mode,
            "unrealized_pnl": float(row.get("unrealisedPnl") or 0.0),
            "raw": row,
        }

    def _order_detail(self, symbol: str, order_id: str) -> dict[str, Any]:
        data = self._request("GET", "/api/v3/trade/order-info", params={"orderId": order_id})
        return dict(data or {})

    def _place_protection(
        self,
        symbol: str,
        position_side: str,
        qty: str,
        tp_price: float | None,
        sl_price: float | None,
    ) -> list[dict[str, Any]]:
        if tp_price is None and sl_price is None:
            return []
        sid = self._symbol_id(symbol)
        mode = self._position_mode(symbol)
        side = "sell" if position_side == "long" else "buy"
        body: dict[str, Any] = {
            "category": self.CATEGORY,
            "symbol": sid,
            "type": "tpsl",
            "tpslMode": "partial",
            "qty": qty,
            "side": side,
            "reduceOnly": "yes",
            "clientOid": self._client_oid("utb-tpsl"),
            "tpTriggerBy": "market",
            "slTriggerBy": "market",
            "tpOrderType": "market",
            "slOrderType": "market",
        }
        if mode == "hedge_mode":
            body["posSide"] = position_side
        if tp_price is not None:
            body["takeProfit"] = self._price(symbol, float(tp_price))
        if sl_price is not None:
            body["stopLoss"] = self._price(symbol, float(sl_price))
        data = self._request("POST", "/api/v3/trade/place-strategy-order", body=body) or {}
        # UTA represents a TP+SL pair as one tpsl strategy order. Return two
        # logical legs so the engine's protection-count contract remains stable.
        base = dict(data) if isinstance(data, dict) else {"result": data}
        results: list[dict[str, Any]] = []
        if tp_price is not None:
            results.append({**base, "leg": "tp", "triggerPrice": str(tp_price)})
        if sl_price is not None:
            results.append({**base, "leg": "sl", "triggerPrice": str(sl_price)})
        return results

    def market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        reduce_only: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"invalid order side: {side}")
        sid = self._symbol_id(symbol)
        qty = self._qty(symbol, amount)
        mode = self._position_mode(symbol)
        position_side = "long" if side == "buy" else "short"
        body: dict[str, Any] = {
            "category": self.CATEGORY,
            "symbol": sid,
            "orderType": "market",
            "qty": qty,
            "side": side,
            "clientOid": self._client_oid("utb-uta"),
        }
        if mode == "hedge_mode":
            if reduce_only:
                position_side = "long" if side == "sell" else "short"
            body["posSide"] = position_side
        elif reduce_only:
            body["reduceOnly"] = "yes"

        data = self._request("POST", "/api/v3/trade/place-order", body=body) or {}
        order_id = str(data.get("orderId") or "")
        detail: dict[str, Any] = {}
        if order_id:
            for _ in range(6):
                try:
                    detail = self._order_detail(symbol, order_id)
                    if str(detail.get("orderStatus") or "").lower() == "filled":
                        break
                except Exception:
                    pass
                time.sleep(0.2)

        protection_data: list[dict[str, Any]] = []
        protection_error = None
        if not reduce_only and (kwargs.get("tp_price") is not None or kwargs.get("sl_price") is not None):
            try:
                protection_data = self._place_protection(
                    symbol,
                    position_side,
                    qty,
                    float(kwargs["tp_price"]) if kwargs.get("tp_price") is not None else None,
                    float(kwargs["sl_price"]) if kwargs.get("sl_price") is not None else None,
                )
            except Exception as exc:
                protection_error = f"{type(exc).__name__}: {exc}"

        filled = float(detail.get("cumExecQty") or detail.get("qty") or qty)
        average = float(detail.get("avgPrice") or 0.0) or None
        return {
            "id": order_id or data.get("clientOid"),
            "clientOid": data.get("clientOid"),
            "amount": filled,
            "filled": filled,
            "average": average,
            "price": average,
            "status": detail.get("orderStatus") or "accepted",
            "protection": protection_data,
            "protection_error": protection_error,
            "raw": detail or data,
        }

    def _pending_plan_orders(self, symbol: str) -> list[dict[str, Any]]:
        sid = self._symbol_id(symbol)
        rows = self._request(
            "GET",
            "/api/v3/trade/unfilled-strategy-orders",
            params={"category": self.CATEGORY, "type": "tpsl"},
        ) or []
        return [dict(x) for x in rows if str(x.get("symbol") or "").upper() == sid]

    @staticmethod
    def _active_plans(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # One UTA tpsl strategy object may contain both TP and SL. Expand it
        # into logical legs to preserve the engine's >=2 verification contract.
        legs: list[dict[str, Any]] = []
        for order in orders:
            if str(order.get("status") or "pending").lower() not in {"pending", "submitting"}:
                continue
            if str(order.get("takeProfit") or "").strip() not in {"", "0"}:
                legs.append({**order, "leg": "tp", "triggerPrice": order.get("takeProfit")})
            if str(order.get("stopLoss") or "").strip() not in {"", "0"}:
                legs.append({**order, "leg": "sl", "triggerPrice": order.get("stopLoss")})
        return legs

    def _cancel_plan(self, symbol: str, order: dict[str, Any]) -> None:
        order_id = str(order.get("orderId") or "").strip()
        client_oid = str(order.get("clientOid") or "").strip()
        if not order_id and not client_oid:
            return
        body: dict[str, Any] = {}
        if order_id:
            body["orderId"] = order_id
        else:
            body["clientOid"] = client_oid
        self._request("POST", "/api/v3/trade/cancel-strategy-order", body=body)

    def cancel_protection(self, symbol: str) -> None:
        seen: set[str] = set()
        for order in self._bot_plan_orders(symbol):
            key = self._plan_key(order)
            if not key or key in seen:
                continue
            seen.add(key)
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
        side = str(position_side).strip().lower()
        if side not in {"long", "short"}:
            raise ValueError(f"invalid position side for protection: {position_side}")
        qty = self._qty(symbol, float(total_amount))
        old_orders = self._bot_plan_orders(symbol)
        created = self._place_protection(symbol, side, qty, float(tp_price), float(sl_price))
        if len(created) < 2:
            return {"ok": False, "reason": "Bitget UTA did not create both TP and SL legs", "created": created}

        new_ids = {
            str(x.get("orderId") or "").strip() for x in created if str(x.get("orderId") or "").strip()
        }
        for order in old_orders:
            if str(order.get("orderId") or "").strip() in new_ids:
                continue
            try:
                self._cancel_plan(symbol, order)
            except Exception:
                pass

        for _ in range(10):
            active = self._active_plans(self._bot_plan_orders(symbol))
            if len(active) >= 2:
                return {
                    "ok": True,
                    "symbol": self._symbol_id(symbol),
                    "total_qty": qty,
                    "tp_price": float(tp_price),
                    "sl_price": float(sl_price),
                    "verification": {"ok": True, "count": len(active), "orders": active},
                }
            time.sleep(0.2)
        return {
            "ok": False,
            "symbol": self._symbol_id(symbol),
            "reason": "UTA replacement protection was not verified",
        }
