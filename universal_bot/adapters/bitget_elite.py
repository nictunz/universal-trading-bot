from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal, ROUND_DOWN
from typing import Any
from urllib.parse import urlencode

import requests

from universal_bot.adapters.hybrid_ccxt_adapter import HybridCCXTAdapter


class BitgetEliteAdapter(HybridCCXTAdapter):
    """Bitget Elite Trading Portfolio adapter using the current UTA v3 APIs.

    Public OHLCV / four-exchange volume still comes from HybridCCXTAdapter.
    Authenticated trading never goes through CCXT: it is signed directly with
    the dedicated Elite Trading API credentials and scoped to the elite/copy
    portfolio endpoints where available.

    Elite portfolios currently use hedge mode and crossed margin. The adapter
    deliberately refuses one-way/isolated configuration instead of attempting
    unsupported account-mode changes.
    """

    BASE_URL = "https://api.bitget.com"
    CATEGORY = "USDT-FUTURES"

    def __init__(
        self,
        api_key: str,
        secret: str,
        passphrase: str,
        *,
        timeout: float = 8.0,
        coinapi_api_key: str = "",
        fallback_exchanges: list[str] | None = None,
        community_fallback: bool = False,
    ) -> None:
        # Keep CCXT public-only. Elite credentials must never accidentally be
        # used by a classic/standard CCXT private endpoint.
        super().__init__(
            "bitget",
            "",
            "",
            "",
            coinapi_api_key=coinapi_api_key,
            fallback_exchanges=fallback_exchanges,
            community_fallback=community_fallback,
        )
        self.elite_api_key = api_key.strip()
        self.elite_api_secret = secret.strip()
        self.elite_api_passphrase = passphrase.strip()
        self.timeout = float(timeout)
        self._instrument_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _symbol_id(symbol: str) -> str:
        text = symbol.strip().upper()
        if "/" in text:
            base, rest = text.split("/", 1)
            quote = rest.split(":", 1)[0]
            return f"{base}{quote}"
        return text.replace("-", "")

    def _credentials_ready(self) -> bool:
        return bool(self.elite_api_key and self.elite_api_secret and self.elite_api_passphrase)

    def _signed_headers(self, method: str, path: str, query: str, body_text: str) -> dict[str, str]:
        if not self._credentials_ready():
            raise RuntimeError("Bitget Elite API credentials are not configured")
        timestamp = str(int(time.time() * 1000))
        suffix = f"?{query}" if query else ""
        prehash = f"{timestamp}{method.upper()}{path}{suffix}{body_text}"
        digest = hmac.new(
            self.elite_api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(digest).decode("ascii")
        return {
            "ACCESS-KEY": self.elite_api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.elite_api_passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        method = method.upper()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        query = urlencode(sorted((str(k), str(v)) for k, v in clean_params.items()))
        body_text = "" if not body else json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        headers = self._signed_headers(method, path, query, body_text)
        url = self.BASE_URL + path + (f"?{query}" if query else "")
        response = requests.request(
            method,
            url,
            headers=headers,
            data=body_text or None,
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Bitget Elite returned non-JSON response: HTTP {response.status_code}") from exc
        if str(payload.get("code")) != "00000":
            raise RuntimeError(f"Bitget Elite API error {payload.get('code')}: {payload.get('msg')}")
        return payload.get("data")

    def _public_get(self, path: str, params: dict[str, Any]) -> Any:
        response = requests.get(self.BASE_URL + path, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("code")) != "00000":
            raise RuntimeError(f"Bitget public API error {payload.get('code')}: {payload.get('msg')}")
        return payload.get("data")

    def account_info(self) -> dict[str, Any]:
        data = self._request("GET", "/api/v3/account/info")
        return dict(data or {})

    def elite_trading_pairs(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/v3/copy/futures/trading-pairs")
        return [dict(x) for x in (data or [])]

    def _instrument(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        cached = self._instrument_cache.get(sid)
        if cached is not None:
            return cached
        rows = self._public_get(
            "/api/v3/market/instruments",
            {"category": self.CATEGORY, "symbol": sid},
        )
        if not rows:
            raise RuntimeError(f"Bitget instrument not found: {sid}")
        instrument = dict(rows[0])
        if str(instrument.get("status", "")).lower() not in {"online", "normal"}:
            raise RuntimeError(f"Bitget instrument is not online: {sid}")
        self._instrument_cache[sid] = instrument
        return instrument

    @staticmethod
    def _step_floor(value: float, step_text: str, precision_text: str) -> str:
        step = Decimal(str(step_text or "0"))
        precision = max(0, int(precision_text or 0))
        number = Decimal(str(value))
        if step > 0:
            number = (number / step).to_integral_value(rounding=ROUND_DOWN) * step
        quantum = Decimal(1).scaleb(-precision)
        number = number.quantize(quantum, rounding=ROUND_DOWN)
        return format(number, "f")

    def _qty(self, symbol: str, amount: float) -> str:
        instrument = self._instrument(symbol)
        text = self._step_floor(
            amount,
            str(instrument.get("quantityMultiplier") or instrument.get("minOrderQty") or "0"),
            str(instrument.get("quantityPrecision") or "0"),
        )
        qty = Decimal(text)
        minimum = Decimal(str(instrument.get("minOrderQty") or "0"))
        if qty <= 0 or (minimum > 0 and qty < minimum):
            raise RuntimeError(f"order quantity {text} is below Bitget minimum {minimum}")
        return text

    def _price(self, symbol: str, price: float) -> str:
        instrument = self._instrument(symbol)
        return self._step_floor(
            price,
            str(instrument.get("priceMultiplier") or "0"),
            str(instrument.get("pricePrecision") or "0"),
        )

    def equity(self) -> float:
        # For the Elite lead account this endpoint exposes the amount currently
        # available to trade/transfer. Using available rather than total account
        # equity is intentionally conservative for position sizing.
        data = self._request(
            "GET",
            "/api/v3/copy/futures/max-transferable",
            params={"coin": "USDT"},
        )
        return float((data or {}).get("available") or 0.0)

    def position(self, symbol: str):
        sid = self._symbol_id(symbol)
        rows = self._request("GET", "/api/v3/copy/futures/position-summary") or []
        matches = [
            x for x in rows
            if str(x.get("symbol", "")).upper() == sid and float(x.get("holdSize") or 0.0) > 0
        ]
        if len(matches) > 1:
            raise RuntimeError(
                f"multiple Elite hedge positions exist for {sid}; the bot requires at most one active side per symbol"
            )
        if not matches:
            return {"side": "FLAT", "size": 0.0, "entry_price": 0.0, "notional": 0.0}
        row = dict(matches[0])
        side = "LONG" if str(row.get("holdSide", "")).lower() == "long" else "SHORT"
        size = abs(float(row.get("holdSize") or 0.0))
        return {
            "side": side,
            "size": size,
            "entry_price": float(row.get("avgPrice") or 0.0),
            "mark_price": float(row.get("markPrice") or 0.0),
            "notional": abs(float(row.get("positionValue") or 0.0)),
            "leverage": float(row.get("leverage") or 0.0),
            "margin_mode": row.get("marginMode"),
            "raw": row,
        }

    def configure_live(self, symbol: str, leverage: int, margin_mode: str, require_one_way: bool = False) -> dict:
        if not self._credentials_ready():
            return {"ok": False, "supported": True, "reason": "Bitget Elite credentials are missing"}
        if str(margin_mode).lower() not in {"cross", "crossed"}:
            return {
                "ok": False,
                "supported": True,
                "reason": "Bitget Elite Trading supports crossed margin only; set MARGIN_MODE=crossed",
            }
        if require_one_way:
            return {
                "ok": False,
                "supported": True,
                "reason": "Bitget Elite Trading does not support one-way mode; set LIVE_REQUIRE_ONE_WAY_MODE=false",
            }
        try:
            info = self.account_info()
            permissions = {str(x) for x in (info.get("permissions") or [])}
            required = {"uta_trade", "copy_futures_position", "copy_futures_order"}
            missing = sorted(required - permissions)
            if missing:
                return {
                    "ok": False,
                    "supported": True,
                    "reason": "Elite API missing permissions: " + ",".join(missing),
                    "permissions": sorted(permissions),
                }
            sid = self._symbol_id(symbol)
            pair = next(
                (x for x in self.elite_trading_pairs() if str(x.get("symbol", "")).upper() == sid),
                None,
            )
            if pair is None:
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"{sid} is not enabled in this Elite Trading Portfolio",
                }
            self._instrument(symbol)
            return {
                "ok": True,
                "supported": True,
                "profile": "elite",
                "margin_mode": "crossed",
                "position_mode": "hedge",
                "configured_leverage": int(leverage),
                "elite_pair_leverage": float(pair.get("leverage") or 0.0),
                "permissions": sorted(permissions),
            }
        except Exception as exc:
            return {"ok": False, "supported": True, "reason": f"Elite readiness failed: {type(exc).__name__}: {exc}"}

    @staticmethod
    def _client_oid(prefix: str = "utb") -> str:
        return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"[:32]

    def _order_detail(self, order_id: str) -> dict[str, Any]:
        data = self._request("GET", "/api/v3/trade/order-info", params={"orderId": order_id})
        return dict(data or {})

    def _place_protection(self, symbol: str, pos_side: str, tp_price: float | None, sl_price: float | None) -> dict[str, Any] | None:
        if tp_price is None and sl_price is None:
            return None
        body: dict[str, Any] = {
            "category": self.CATEGORY,
            "symbol": self._symbol_id(symbol),
            "type": "tpsl",
            "tpslMode": "full",
            "posSide": pos_side,
            "clientOid": self._client_oid("utb-tpsl"),
        }
        if tp_price is not None:
            body.update({
                "takeProfit": self._price(symbol, float(tp_price)),
                "tpTriggerBy": "mark",
                "tpOrderType": "market",
            })
        if sl_price is not None:
            body.update({
                "stopLoss": self._price(symbol, float(sl_price)),
                "slTriggerBy": "mark",
                "slOrderType": "market",
            })
        data = self._request("POST", "/api/v3/trade/place-strategy-order", body=body)
        return dict(data or {})

    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False, **kwargs):
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"invalid order side: {side}")
        sid = self._symbol_id(symbol)
        qty = self._qty(symbol, amount)
        pos_side = ("long" if side == "sell" else "short") if reduce_only else ("long" if side == "buy" else "short")
        body: dict[str, Any] = {
            "category": self.CATEGORY,
            "symbol": sid,
            "qty": qty,
            "side": side,
            "posSide": pos_side,
            "orderType": "market",
            "marginMode": "crossed",
            "clientOid": self._client_oid("utb-elite"),
        }
        data = self._request("POST", "/api/v3/trade/place-order", body=body) or {}
        order_id = str(data.get("orderId") or "")
        detail: dict[str, Any] = {}
        if order_id:
            for _ in range(6):
                try:
                    detail = self._order_detail(order_id)
                    if str(detail.get("orderStatus", "")).lower() == "filled":
                        break
                except Exception:
                    pass
                time.sleep(0.2)

        protection_data = None
        protection_error = None
        if not reduce_only and (kwargs.get("tp_price") is not None or kwargs.get("sl_price") is not None):
            try:
                protection_data = self._place_protection(
                    symbol,
                    pos_side,
                    float(kwargs["tp_price"]) if kwargs.get("tp_price") is not None else None,
                    float(kwargs["sl_price"]) if kwargs.get("sl_price") is not None else None,
                )
            except Exception as exc:
                # Do not hide an already-filled entry by raising after the fact.
                # TradingEngine immediately verifies exchange protection and will
                # emergency-flatten if TP/SL cannot be confirmed.
                protection_error = f"{type(exc).__name__}: {exc}"

        filled = float(detail.get("cumExecQty") or qty)
        average = float(detail.get("avgPrice") or 0.0) or None
        return {
            "id": order_id or data.get("clientOid"),
            "clientOid": data.get("clientOid"),
            "amount": filled,
            "filled": filled,
            "average": average,
            "price": average,
            "status": detail.get("orderStatus") or "accepted",
            "raw": {
                "order": detail or data,
                "protection": protection_data,
                "protection_error": protection_error,
            },
        }

    def _protection_orders(self, symbol: str) -> list[dict[str, Any]]:
        sid = self._symbol_id(symbol)
        data = self._request(
            "GET",
            "/api/v3/trade/unfilled-strategy-orders",
            params={"category": self.CATEGORY, "type": "tpsl"},
        ) or {}
        rows = data.get("list") if isinstance(data, dict) else data
        return [
            dict(x) for x in (rows or [])
            if str(x.get("symbol", "")).upper() == sid
            and str(x.get("status", "pending")).lower() in {"pending", "submitting", "live", "new"}
        ]

    def protection_status(self, symbol: str) -> dict:
        last_error: Exception | None = None
        for _ in range(5):
            try:
                orders = self._protection_orders(symbol)
                has_tp = any(bool(str(x.get("takeProfit") or "").strip()) for x in orders)
                has_sl = any(bool(str(x.get("stopLoss") or "").strip()) for x in orders)
                if has_tp and has_sl:
                    return {"ok": True, "supported": True, "count": len(orders), "orders": orders}
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        if last_error is not None:
            return {"ok": False, "supported": True, "reason": f"protection verification failed: {last_error}"}
        return {"ok": False, "supported": True, "count": 0, "reason": "both Elite TP and SL were not verified"}

    def cancel_protection(self, symbol: str) -> None:
        try:
            orders = self._protection_orders(symbol)
        except Exception:
            return
        for order in orders:
            order_id = order.get("orderId")
            client_oid = order.get("clientOid")
            body = {"orderId": str(order_id)} if order_id else {"clientOid": str(client_oid)}
            try:
                self._request("POST", "/api/v3/trade/cancel-strategy-order", body=body)
            except Exception:
                pass
