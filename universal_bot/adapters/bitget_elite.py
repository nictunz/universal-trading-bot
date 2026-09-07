from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from decimal import ROUND_DOWN, Decimal
from typing import Any
from urllib.parse import urlencode

import requests

from universal_bot.adapters.hybrid_ccxt_adapter import HybridCCXTAdapter


class AmbiguousOrderResult(RuntimeError):
    """The order request may have reached Bitget but no final reply was received."""

    def __init__(
        self,
        message: str,
        *,
        client_oid: str,
        side: str,
        requested_qty: float,
        reduce_only: bool,
    ) -> None:
        super().__init__(message)
        self.client_oid = client_oid
        self.side = side
        self.requested_qty = float(requested_qty)
        self.reduce_only = bool(reduce_only)


class BitgetEliteAdapter(HybridCCXTAdapter):
    """Bitget Elite/Copy API adapter for Classic Accounts.

    The user's Elite Copy API key is authenticated against Bitget Classic v2
    futures/copy endpoints. Public OHLCV still comes from HybridCCXTAdapter,
    while every authenticated account/order request is signed directly here.

    This intentionally does not route Elite credentials through CCXT, so they
    cannot accidentally hit a normal private Bitget account endpoint.
    """

    BASE_URL = "https://api.bitget.com"
    PRODUCT_TYPE = "USDT-FUTURES"
    MARGIN_COIN = "USDT"
    TPSL_TRIGGER_TYPE = "fill_price"  # Bitget last traded price, never mark price
    TPSL_ORDER_TYPE = "market"

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
        # Public market data only in the parent adapter.
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
        # Reuse TLS/TCP connections for lower private-order latency.
        self._session = requests.Session()
        self._session.headers.update({"Connection": "keep-alive"})
        self._contract_cache: dict[str, dict[str, Any]] = {}
        self._account_mode_cache: dict[str, str] = {}

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

    @staticmethod
    def _client_oid(prefix: str = "utb") -> str:
        return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"[:32]

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
        return {
            "ACCESS-KEY": self.elite_api_key,
            "ACCESS-SIGN": base64.b64encode(digest).decode("ascii"),
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
        query = urlencode([(str(k), str(v)) for k, v in clean_params.items()])
        body_text = "" if not body else json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        headers = self._signed_headers(method, path, query, body_text)
        url = self.BASE_URL + path + (f"?{query}" if query else "")
        response = self._session.request(
            method,
            url,
            headers=headers,
            data=body_text or None,
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Bitget Elite returned non-JSON response: HTTP {response.status_code}"
            ) from exc
        if str(payload.get("code")) != "00000":
            raise RuntimeError(
                f"Bitget Elite API error HTTP {response.status_code} "
                f"{payload.get('code')}: {payload.get('msg')}"
            )
        return payload.get("data")

    def _public_get(self, path: str, params: dict[str, Any]) -> Any:
        response = self._session.get(self.BASE_URL + path, params=params, timeout=self.timeout)
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Bitget public API returned HTTP {response.status_code}") from exc
        if str(payload.get("code")) != "00000":
            raise RuntimeError(f"Bitget public API error {payload.get('code')}: {payload.get('msg')}")
        return payload.get("data")

    def _contract(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        cached = self._contract_cache.get(sid)
        if cached is not None:
            return cached
        rows = self._public_get(
            "/api/v2/mix/market/contracts",
            {"productType": self.PRODUCT_TYPE, "symbol": sid},
        ) or []
        if not rows:
            raise RuntimeError(f"Bitget contract not found: {sid}")
        contract = dict(rows[0])
        status = str(contract.get("symbolStatus") or "").lower()
        if status not in {"normal", "listed"}:
            raise RuntimeError(f"Bitget contract is not API-tradable: {sid} status={status}")
        self._contract_cache[sid] = contract
        return contract

    @staticmethod
    def _floor_to_step(value: float, step_text: str, decimals: int) -> str:
        number = Decimal(str(value))
        step = Decimal(str(step_text or "0"))
        if step > 0:
            number = (number / step).to_integral_value(rounding=ROUND_DOWN) * step
        quantum = Decimal(1).scaleb(-max(0, decimals))
        number = number.quantize(quantum, rounding=ROUND_DOWN)
        return format(number, "f")

    def _qty(self, symbol: str, amount: float) -> str:
        contract = self._contract(symbol)
        decimals = int(contract.get("volumePlace") or 0)
        step = str(contract.get("sizeMultiplier") or "0")
        text = self._floor_to_step(amount, step, decimals)
        qty = Decimal(text)
        minimum = Decimal(str(contract.get("minTradeNum") or "0"))
        if qty <= 0 or (minimum > 0 and qty < minimum):
            raise RuntimeError(f"order quantity {text} is below Bitget minimum {minimum}")
        max_market = Decimal(str(contract.get("maxMarketOrderQty") or "0"))
        if max_market > 0 and qty > max_market:
            raise RuntimeError(f"order quantity {text} exceeds Bitget market maximum {max_market}")
        return text

    def _price(self, symbol: str, price: float) -> str:
        contract = self._contract(symbol)
        decimals = int(contract.get("pricePlace") or 0)
        step = Decimal(1).scaleb(-decimals) * Decimal(str(contract.get("priceEndStep") or "1"))
        return self._floor_to_step(price, str(step), decimals)

    def account_info(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        data = self._request(
            "GET",
            "/api/v2/mix/account/account",
            params={
                "symbol": sid,
                "productType": self.PRODUCT_TYPE,
                "marginCoin": self.MARGIN_COIN,
            },
        )
        info = dict(data or {})
        mode = str(info.get("posMode") or "").lower()
        if mode:
            self._account_mode_cache[sid] = mode
        return info

    def elite_trading_pairs(self) -> list[dict[str, Any]]:
        rows = self._request(
            "GET",
            "/api/v2/copy/mix-trader/config-query-symbols",
            params={"productType": self.PRODUCT_TYPE},
        ) or []
        return [dict(x) for x in rows]

    def configure_live(
        self,
        symbol: str,
        leverage: int,
        margin_mode: str,
        require_one_way: bool = False,
    ) -> dict:
        if not self._credentials_ready():
            return {"ok": False, "supported": True, "reason": "Bitget Elite credentials are missing"}
        if str(margin_mode).lower() not in {"cross", "crossed"}:
            return {
                "ok": False,
                "supported": True,
                "reason": "Elite bot is configured for crossed margin; set MARGIN_MODE=crossed",
            }
        try:
            sid = self._symbol_id(symbol)
            account = self.account_info(symbol)
            account_margin = str(account.get("marginMode") or "").lower()
            pos_mode = str(account.get("posMode") or "").lower()
            if account_margin and account_margin not in {"cross", "crossed"}:
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"Bitget account margin mode is {account_margin}, expected crossed",
                    "account": {"margin_mode": account_margin, "position_mode": pos_mode},
                }
            if require_one_way and pos_mode != "one_way_mode":
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"LIVE_REQUIRE_ONE_WAY_MODE=true but Bitget account is {pos_mode or 'unknown'}",
                }

            pairs = self.elite_trading_pairs()
            pair = next((x for x in pairs if str(x.get("symbol", "")).upper() == sid), None)
            if pair is None:
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"{sid} is not listed in Elite trader configuration",
                }
            if str(pair.get("openTrader") or "").lower() != "yes":
                return {
                    "ok": False,
                    "supported": True,
                    "reason": f"{sid} Elite trading is disabled (openTrader={pair.get('openTrader')})",
                    "pair": pair,
                }

            contract = self._contract(symbol)
            actual_leverage = float(
                account.get("crossedMarginLeverage")
                or account.get("crossedLever")
                or account.get("leverage")
                or 0.0
            )
            return {
                "ok": True,
                "supported": True,
                "profile": "elite-classic-v2",
                "account_type": "classic",
                "margin_mode": account_margin or "crossed",
                "position_mode": pos_mode or "unknown",
                "requested_leverage": int(leverage),
                "account_leverage": actual_leverage,
                "symbol": sid,
                "elite_open": True,
                "elite_min_open_count": pair.get("minOpenCount"),
                "contract_min_qty": contract.get("minTradeNum"),
                "contract_max_leverage": contract.get("maxLever"),
            }
        except Exception as exc:
            return {
                "ok": False,
                "supported": True,
                "reason": f"Elite Classic readiness failed: {type(exc).__name__}: {exc}",
            }

    def equity(self) -> float:
        rows = self._request(
            "GET",
            "/api/v2/mix/account/accounts",
            params={"productType": self.PRODUCT_TYPE},
        ) or []
        usdt = next(
            (x for x in rows if str(x.get("marginCoin", "")).upper() == self.MARGIN_COIN),
            None,
        )
        if usdt is None:
            return 0.0
        # Match the proven previous Elite bot: size from currently available USDT.
        return float(usdt.get("available") or 0.0)

    def position(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        rows = self._request(
            "GET",
            "/api/v2/mix/position/single-position",
            params={
                "symbol": sid,
                "productType": self.PRODUCT_TYPE,
                "marginCoin": self.MARGIN_COIN,
            },
        ) or []
        active = [dict(x) for x in rows if abs(float(x.get("total") or 0.0)) > 0]
        if len(active) > 1:
            raise RuntimeError(
                f"multiple active hedge positions exist for {sid}; this bot requires at most one active side per symbol"
            )
        if not active:
            return {"side": "FLAT", "size": 0.0, "entry_price": 0.0, "notional": 0.0}
        row = active[0]
        hold = str(row.get("holdSide") or "").lower()
        side = "LONG" if hold in {"long", "buy"} else "SHORT"
        size = abs(float(row.get("total") or 0.0))
        entry = float(row.get("openPriceAvg") or row.get("averageOpenPrice") or 0.0)
        mode = str(row.get("posMode") or "").lower()
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
            "unrealized_pnl": float(row.get("unrealizedPL") or 0.0),
            "raw": row,
        }

    def _position_mode(self, symbol: str) -> str:
        sid = self._symbol_id(symbol)
        cached = self._account_mode_cache.get(sid)
        if cached:
            return cached
        info = self.account_info(symbol)
        return str(info.get("posMode") or "one_way_mode").lower()

    @staticmethod
    def _is_ambiguous_order_error(exc: Exception) -> bool:
        if isinstance(exc, requests.RequestException):
            return True
        text = str(exc).lower()
        return (
            "non-json response" in text
            or "request timed out" in text
            or any(f" {code}:" in text for code in ("40010", "40725", "45001"))
        )

    def _order_detail(
        self,
        symbol: str,
        order_id: str | None = None,
        *,
        client_oid: str | None = None,
    ) -> dict[str, Any]:
        if not order_id and not client_oid:
            raise ValueError("order_id or client_oid is required")
        data = self._request(
            "GET",
            "/api/v2/mix/order/detail",
            params={
                "symbol": self._symbol_id(symbol),
                "productType": self.PRODUCT_TYPE,
                "orderId": order_id,
                "clientOid": client_oid,
            },
        )
        return dict(data or {})

    @staticmethod
    def _fill_number(row: dict[str, Any], *names: str) -> float:
        for name in names:
            value = row.get(name)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    @classmethod
    def _summarize_close_fills(
        cls,
        rows: list[dict[str, Any]],
        *,
        symbol_id: str,
        position_side: str,
        since_ms: int,
        source: str,
    ) -> dict[str, Any] | None:
        position_side = str(position_side).upper()
        expected_side = "sell" if position_side == "LONG" else "buy"
        matched: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            row_symbol = str(row.get("symbol") or symbol_id).upper()
            if row_symbol and row_symbol != symbol_id.upper():
                continue
            created = int(cls._fill_number(row, "createdTime", "cTime", "ctime", "fillTime", "uTime"))
            if created and created < since_ms:
                continue
            side = str(row.get("side") or "").lower()
            trade_side = str(row.get("tradeSide") or "").lower()
            pos_side = str(row.get("posSide") or row.get("holdSide") or "").lower()
            closes_position = (
                side == expected_side
                or f"close_{position_side.lower()}" in side
                or f"close-{position_side.lower()}" in side
                or (trade_side == "close" and pos_side == position_side.lower())
            )
            if closes_position:
                matched.append(row)
        if not matched:
            return None

        matched.sort(
            key=lambda row: cls._fill_number(row, "createdTime", "cTime", "ctime", "fillTime", "uTime"),
            reverse=True,
        )
        latest = matched[0]
        order_id = str(latest.get("orderId") or "")
        client_oid = str(latest.get("clientOid") or "")
        if order_id:
            group = [row for row in matched if str(row.get("orderId") or "") == order_id]
        elif client_oid:
            group = [row for row in matched if str(row.get("clientOid") or "") == client_oid]
        else:
            group = [latest]

        total_qty = 0.0
        total_value = 0.0
        fee = 0.0
        reported_pnl = 0.0
        has_reported_pnl = False
        for row in group:
            qty = abs(cls._fill_number(row, "execQty", "baseVolume", "sizeQty", "fillQty", "fillAmount", "size"))
            price = cls._fill_number(row, "execPrice", "fillPrice", "priceAvg", "price")
            if qty > 0 and price > 0:
                total_qty += qty
                total_value += qty * price
            # UTA can return both the legacy aggregate `fee` and the detailed
            # `feeDetail` list for the same fill. Prefer the detailed values so
            # the journal does not charge the closing fee twice.
            fee_details = row.get("feeDetail") or []
            if isinstance(fee_details, dict):
                fee_details = [fee_details]
            if fee_details:
                fee += sum(
                    abs(cls._fill_number(dict(detail), "fee"))
                    for detail in fee_details
                    if isinstance(detail, dict)
                )
            else:
                fee += abs(cls._fill_number(row, "fee"))
            for name in ("execPnl", "profit", "totalProfits"):
                if row.get(name) not in (None, ""):
                    reported_pnl += cls._fill_number(row, name)
                    has_reported_pnl = True
                    break
        if total_qty <= 0 or total_value <= 0:
            return None
        time_ms = int(
            max(
                cls._fill_number(row, "createdTime", "cTime", "ctime", "fillTime", "uTime")
                for row in group
            )
        )
        return {
            "price": total_value / total_qty,
            "qty": total_qty,
            "fee": fee,
            "realized_pnl": reported_pnl if has_reported_pnl else None,
            "time_ms": time_ms or None,
            "order_id": order_id or None,
            "client_oid": client_oid or None,
            "source": source,
            "raw": group,
        }

    def recent_close_fill(
        self,
        symbol: str,
        position_side: str,
        *,
        since_ms: int | None = None,
    ) -> dict[str, Any] | None:
        now_ms = int(time.time() * 1000)
        start_ms = max(int(since_ms or now_ms - 86_400_000), now_ms - 30 * 86_400_000)
        data = self._request(
            "GET",
            "/api/v2/mix/order/fills",
            params={
                "symbol": self._symbol_id(symbol),
                "productType": self.PRODUCT_TYPE,
                "startTime": str(start_ms),
                "endTime": str(now_ms),
                "limit": "100",
            },
        ) or {}
        if isinstance(data, dict):
            rows = data.get("fillList") or data.get("list") or data.get("entrustedList") or []
        else:
            rows = data
        return self._summarize_close_fills(
            [dict(row) for row in (rows or [])],
            symbol_id=self._symbol_id(symbol),
            position_side=position_side,
            since_ms=start_ms,
            source="bitget-classic-v2-fills",
        )

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
        results: list[dict[str, Any]] = []

        # In hedge mode Bitget's Classic API uses side as the position side for
        # close orders (close long => side=buy, close short => side=sell).
        # In one-way mode it uses the actual closing order direction.
        if mode == "hedge_mode":
            close_side = "buy" if position_side == "long" else "sell"
        else:
            close_side = "sell" if position_side == "long" else "buy"

        for kind, trigger in (("tp", tp_price), ("sl", sl_price)):
            if trigger is None:
                continue
            body: dict[str, Any] = {
                "planType": "normal_plan",
                "symbol": sid,
                "productType": self.PRODUCT_TYPE,
                "marginMode": "crossed",
                "marginCoin": self.MARGIN_COIN,
                "size": qty,
                "triggerPrice": self._price(symbol, float(trigger)),
                "triggerType": self.TPSL_TRIGGER_TYPE,
                "side": close_side,
                "orderType": self.TPSL_ORDER_TYPE,
                "clientOid": self._client_oid(f"utb-{kind}"),
            }
            if mode == "hedge_mode":
                body["tradeSide"] = "close"
            else:
                body["reduceOnly"] = "yes"
            data = self._request("POST", "/api/v2/mix/order/place-plan-order", body=body)
            results.append(dict(data or {}))
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

        client_oid = self._client_oid("utb-elite")
        body: dict[str, Any] = {
            "symbol": sid,
            "productType": self.PRODUCT_TYPE,
            "marginCoin": self.MARGIN_COIN,
            "marginMode": "crossed",
            "orderType": "market",
            "size": qty,
            "clientOid": client_oid,
        }

        if mode == "hedge_mode":
            if reduce_only:
                # TradingEngine calls sell to close LONG and buy to close SHORT.
                # Classic hedge-mode instead wants the position side + tradeSide=close.
                body["side"] = "buy" if side == "sell" else "sell"
                body["tradeSide"] = "close"
                position_side = "long" if side == "sell" else "short"
            else:
                body["side"] = side
                body["tradeSide"] = "open"
        else:
            body["side"] = side
            body["reduceOnly"] = "yes" if reduce_only else "no"

        detail: dict[str, Any] = {}
        recovered = False
        try:
            data = self._request("POST", "/api/v2/mix/order/place-order", body=body) or {}
        except Exception as exc:
            if not self._is_ambiguous_order_error(exc):
                raise
            # Never retry placement with a new ID. Bitget may already have
            # accepted it; resolve the original request using its clientOid.
            deadline = time.monotonic() + 0.8
            while True:
                try:
                    detail = self._order_detail(symbol, client_oid=client_oid)
                    if detail:
                        recovered = True
                        break
                except Exception:
                    pass
                if time.monotonic() >= deadline:
                    raise AmbiguousOrderResult(
                        f"Bitget order outcome is unknown after clientOid recovery: {client_oid}",
                        client_oid=client_oid,
                        side=side,
                        requested_qty=float(qty),
                        reduce_only=reduce_only,
                    ) from exc
                time.sleep(0.1)
            data = {
                "orderId": detail.get("orderId"),
                "clientOid": detail.get("clientOid") or client_oid,
            }
        order_id = str(data.get("orderId") or "")

        # Place temporary protection as soon as Bitget acknowledges the entry.
        # The runtime later replaces it with an exact full-position pair based
        # on the exchange average fill.
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
                # The entry may already be filled. TradingEngine verifies TP/SL
                # immediately and emergency-flattens when protection is absent.
                protection_error = f"{type(exc).__name__}: {exc}"

        if order_id and not detail:
            # First check immediately, then use short bounded retries. This
            # preserves confirmed fill sizing while reducing TP/SL placement lag.
            deadline = time.monotonic() + 0.65
            while True:
                try:
                    detail = self._order_detail(symbol, order_id)
                    if str(detail.get("state") or "").lower() == "filled":
                        break
                except Exception:
                    pass
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.1)

        filled = float(detail.get("baseVolume") or detail.get("size") or qty)
        average = float(detail.get("priceAvg") or 0.0) or None
        return {
            "id": order_id or data.get("clientOid"),
            "clientOid": data.get("clientOid") or client_oid,
            "amount": filled,
            "filled": filled,
            "average": average,
            "price": average,
            "status": detail.get("state") or "accepted",
            "protection": protection_data,
            "protection_error": protection_error,
            "recovered_by_client_oid": recovered,
            "raw": detail or data,
        }

    def _pending_plan_orders(self, symbol: str) -> list[dict[str, Any]]:
        sid = self._symbol_id(symbol)
        rows: list[dict[str, Any]] = []
        # Bitget has used both normal_plan and profit_loss for active TP/SL plans.
        for plan_type in ("normal_plan", "profit_loss"):
            try:
                data = self._request(
                    "GET",
                    "/api/v2/mix/order/orders-plan-pending",
                    params={
                        "symbol": sid,
                        "productType": self.PRODUCT_TYPE,
                        "planType": plan_type,
                    },
                ) or {}
                items = data.get("entrustedList") if isinstance(data, dict) else data
                rows.extend(dict(x) for x in (items or []))
            except Exception:
                continue
        return rows

    def protection_status(self, symbol: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for _ in range(5):
            try:
                orders = self._pending_plan_orders(symbol)
                # Our implementation places TP and SL as two normal trigger orders.
                prices = [str(x.get("triggerPrice") or "").strip() for x in orders]
                active = [x for x, p in zip(orders, prices) if p and p != "0"]
                if len(active) >= 2:
                    return {"ok": True, "supported": True, "count": len(active), "orders": active}
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        if last_error is not None:
            return {"ok": False, "supported": True, "reason": f"protection verification failed: {last_error}"}
        return {"ok": False, "supported": True, "count": 0, "reason": "both Elite TP and SL were not verified"}

    def cancel_protection(self, symbol: str) -> None:
        sid = self._symbol_id(symbol)
        for order in self._pending_plan_orders(symbol):
            order_id = order.get("orderId")
            client_oid = order.get("clientOid")
            if not order_id and not client_oid:
                continue
            body: dict[str, Any] = {
                "symbol": sid,
                "productType": self.PRODUCT_TYPE,
                "marginCoin": self.MARGIN_COIN,
                "planType": str(order.get("planType") or "normal_plan"),
            }
            if order_id:
                body["orderId"] = str(order_id)
            else:
                body["clientOid"] = str(client_oid)
            try:
                self._request("POST", "/api/v2/mix/order/cancel-plan-order", body=body)
            except Exception:
                pass
