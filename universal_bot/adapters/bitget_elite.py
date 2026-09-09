from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import threading
import time
import uuid
from collections import defaultdict, deque
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


class _EndpointRateLimiter:
    """Small per-endpoint guard with headroom below Bitget's published limits."""

    def __init__(self) -> None:
        self._calls: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def acquire(self, method: str, path: str) -> None:
        # Public market data is documented at 20/s.  Private endpoint limits
        # vary; eight calls/s leaves headroom without delaying five IOC slices.
        limit = 18 if "/market/" in path else 8
        key = (method.upper(), path)
        while True:
            wait = 0.0
            with self._lock:
                now = time.monotonic()
                calls = self._calls[key]
                while calls and calls[0] <= now - 1.0:
                    calls.popleft()
                if len(calls) < limit:
                    calls.append(now)
                    return
                wait = max(0.001, calls[0] + 1.0 - now)
            time.sleep(wait)


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
        self._rate_limiter = _EndpointRateLimiter()
        self._known_protection_order_ids: set[str] = set()

    def _acquire_api_budget(self, method: str, path: str) -> None:
        # Tests and lightweight probes sometimes instantiate via __new__.
        limiter = getattr(self, "_rate_limiter", None)
        if limiter is None:
            limiter = _EndpointRateLimiter()
            self._rate_limiter = limiter
        limiter.acquire(method, path)

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
        url = self.BASE_URL + path + (f"?{query}" if query else "")
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            self._acquire_api_budget(method, path)
            headers = self._signed_headers(method, path, query, body_text)
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
            code = str(payload.get("code"))
            limited = response.status_code == 429 or code in {"429", "40010", "40500"}
            if code == "00000":
                return payload.get("data")
            if limited and method == "GET" and attempt + 1 < attempts:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.15 * (2**attempt)
                except (TypeError, ValueError):
                    delay = 0.15 * (2**attempt)
                time.sleep(min(1.0, max(0.05, delay) + random.uniform(0.0, 0.05)))
                continue
            raise RuntimeError(
                f"Bitget Elite API error HTTP {response.status_code} "
                f"{payload.get('code')}: {payload.get('msg')}"
            )
        raise RuntimeError("Bitget Elite GET retry budget exhausted")

    def _public_get(self, path: str, params: dict[str, Any]) -> Any:
        for attempt in range(3):
            self._acquire_api_budget("GET", path)
            response = self._session.get(self.BASE_URL + path, params=params, timeout=self.timeout)
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"Bitget public API returned HTTP {response.status_code}") from exc
            code = str(payload.get("code"))
            if code == "00000":
                return payload.get("data")
            if (response.status_code == 429 or code == "429") and attempt < 2:
                time.sleep(0.10 * (2**attempt) + random.uniform(0.0, 0.03))
                continue
            raise RuntimeError(f"Bitget public API error {payload.get('code')}: {payload.get('msg')}")
        raise RuntimeError("Bitget public GET retry budget exhausted")

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
            or "http 429" in text
            or any(f" {code}:" in text for code in ("40010", "40500", "40725", "45001"))
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

        try:
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
                data = dict(
                    self._request("POST", "/api/v2/mix/order/place-plan-order", body=body)
                    or {}
                )
                # Preserve the submitted semantics because some pending-order
                # responses omit one of these fields briefly after creation.
                data.update({
                    "clientOid": data.get("clientOid") or body["clientOid"],
                    "planType": body["planType"],
                    "triggerPrice": body["triggerPrice"],
                    "size": body["size"],
                    "side": body["side"],
                    "leg": kind,
                })
                results.append(data)
        except Exception:
            # If only one leg was accepted, remove that exact new leg while
            # leaving the previously verified pair untouched.
            self._cancel_plan_orders(symbol, results)
            raise
        return results

    def _public_order_book(self, symbol: str, limit: int = 50) -> dict[str, list[tuple[float, float]]]:
        data = self._public_get(
            "/api/v2/mix/market/merge-depth",
            {
                "symbol": self._symbol_id(symbol),
                "productType": self.PRODUCT_TYPE,
                "precision": "scale0",
                "limit": str(max(1, min(150, int(limit)))),
            },
        ) or {}

        def levels(name: str) -> list[tuple[float, float]]:
            out: list[tuple[float, float]] = []
            for row in data.get(name) or []:
                try:
                    price = float(row[0])
                    qty = float(row[1])
                except (IndexError, TypeError, ValueError):
                    continue
                if price > 0 and qty > 0:
                    out.append((price, qty))
            return out

        return {"bids": levels("bids"), "asks": levels("asks")}

    def _ioc_limit_child(
        self,
        symbol: str,
        side: str,
        amount: float,
        limit_price: float,
    ) -> dict[str, Any]:
        side = side.lower()
        qty = self._qty(symbol, amount)
        client_oid = self._client_oid("utb-ioc")
        body: dict[str, Any] = {
            "symbol": self._symbol_id(symbol),
            "productType": self.PRODUCT_TYPE,
            "marginCoin": self.MARGIN_COIN,
            "marginMode": "crossed",
            "orderType": "limit",
            "force": "ioc",
            "side": side,
            "size": qty,
            "price": self._price(symbol, limit_price),
            "clientOid": client_oid,
        }
        mode = self._position_mode(symbol)
        if mode == "hedge_mode":
            body["tradeSide"] = "open"
        else:
            body["reduceOnly"] = "no"

        detail: dict[str, Any] = {}
        recovered = False
        try:
            data = self._request("POST", "/api/v2/mix/order/place-order", body=body) or {}
        except Exception as exc:
            if not self._is_ambiguous_order_error(exc):
                raise
            deadline = time.monotonic() + 0.8
            while time.monotonic() < deadline:
                try:
                    detail = self._order_detail(symbol, client_oid=client_oid)
                    if detail:
                        recovered = True
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            if not detail:
                raise AmbiguousOrderResult(
                    f"Bitget IOC outcome is unknown after clientOid recovery: {client_oid}",
                    client_oid=client_oid,
                    side=side,
                    requested_qty=float(qty),
                    reduce_only=False,
                ) from exc
            data = detail

        order_id = str(data.get("orderId") or detail.get("orderId") or "")
        if order_id and not detail:
            deadline = time.monotonic() + 0.45
            while time.monotonic() < deadline:
                try:
                    detail = self._order_detail(symbol, order_id)
                    state = str(detail.get("state") or "").lower()
                    if state in {"filled", "cancelled", "canceled", "partially_filled"}:
                        break
                except Exception:
                    pass
                time.sleep(0.05)
        filled = self._fill_number(detail, "baseVolume", "filledQty", "fillQty", "sizeQty")
        average = self._fill_number(detail, "priceAvg", "fillPrice", "price") or None
        return {
            "id": order_id or client_oid,
            "clientOid": data.get("clientOid") or client_oid,
            "amount": filled,
            "requested": float(qty),
            "filled": filled,
            "average": average,
            "price": average,
            "status": detail.get("state") or "accepted",
            "recovered_by_client_oid": recovered,
            "raw": detail or data,
        }

    def adaptive_ioc_entry(
        self,
        symbol: str,
        side: str,
        amount: float,
        *,
        reference_price: float,
        tp_pct: float,
        sl_pct: float,
        fixed_tp_price: float | None = None,
        fixed_sl_price: float | None = None,
        max_adverse_slippage_percent: float = 0.03,
        max_child_orders: int = 5,
        execution_window_seconds: float = 3.0,
        depth_participation: float = 0.20,
        child_pause_seconds: float = 0.15,
    ) -> dict[str, Any]:
        """Fill an entry with bounded IOC slices; never market-chase a remainder."""
        started = time.monotonic()
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"invalid order side: {side}")
        requested = max(0.0, float(amount))
        if requested <= 0 or reference_price <= 0:
            return {"filled": 0.0, "status": "not-submitted"}

        position_side = "LONG" if side == "buy" else "SHORT"
        before = self.position(symbol)
        before_size = float(before.get("size") or 0.0) if before.get("side") == position_side else 0.0
        before_notional = before_size * float(before.get("entry_price") or 0.0)
        latest_size = before_size
        deadline = time.monotonic() + max(0.1, float(execution_window_seconds))
        children: list[dict[str, Any]] = []
        protection_updates: list[dict[str, Any]] = []
        protection_ok = True
        adverse = max(0.0, float(max_adverse_slippage_percent)) / 100.0
        limit_price = reference_price * (1.0 + adverse if side == "buy" else 1.0 - adverse)
        participation = min(1.0, max(0.01, float(depth_participation)))
        if position_side == "LONG":
            fixed_tp = float(fixed_tp_price or reference_price * (1.0 + float(tp_pct) / 100.0))
            fixed_sl = float(fixed_sl_price or reference_price * (1.0 - float(sl_pct) / 100.0))
        else:
            fixed_tp = float(fixed_tp_price or reference_price * (1.0 - float(tp_pct) / 100.0))
            fixed_sl = float(fixed_sl_price or reference_price * (1.0 + float(sl_pct) / 100.0))

        for _ in range(max(1, int(max_child_orders))):
            remaining = requested - max(0.0, latest_size - before_size)
            if remaining <= 1e-12 or time.monotonic() >= deadline:
                break
            book = self._public_order_book(symbol)
            levels = book["asks"] if side == "buy" else book["bids"]
            eligible = [qty for price, qty in levels if price <= limit_price] if side == "buy" else [qty for price, qty in levels if price >= limit_price]
            eligible_qty = sum(eligible)
            child_qty = min(remaining, eligible_qty * participation)
            if child_qty <= 0:
                break
            try:
                child = self._ioc_limit_child(symbol, side, child_qty, limit_price)
            except RuntimeError as exc:
                if "below Bitget minimum" in str(exc):
                    break
                raise
            children.append(child)

            # Position state is authoritative for partial IOC fills and protects
            # against delayed or incomplete order-detail responses.
            position = self.position(symbol)
            if position.get("side") != position_side:
                if position.get("side") == "FLAT":
                    if time.monotonic() < deadline:
                        time.sleep(min(max(0.0, child_pause_seconds), max(0.0, deadline - time.monotonic())))
                    continue
                raise RuntimeError(f"unexpected exchange position during IOC entry: {position.get('side')}")
            current_size = float(position.get("size") or 0.0)
            avg_entry = float(position.get("entry_price") or 0.0)
            if current_size > latest_size + 1e-12 and avg_entry > 0:
                protect_side = "long" if position_side == "LONG" else "short"
                replaced = self.replace_full_protection(
                    symbol, protect_side, current_size, fixed_tp, fixed_sl
                )
                protection_updates.append({
                    "qty": current_size,
                    "average": avg_entry,
                    "tp": fixed_tp,
                    "sl": fixed_sl,
                    "ok": bool(replaced.get("ok")),
                })
                protection_ok = bool(replaced.get("ok"))
                latest_size = current_size
                if not protection_ok:
                    break
            if time.monotonic() < deadline:
                time.sleep(min(max(0.0, child_pause_seconds), max(0.0, deadline - time.monotonic())))

        final_position = self.position(symbol)
        final_size = float(final_position.get("size") or 0.0) if final_position.get("side") == position_side else before_size
        filled = max(0.0, final_size - before_size)
        final_notional = final_size * float(final_position.get("entry_price") or 0.0)
        fill_notional = max(0.0, final_notional - before_notional)
        average = fill_notional / filled if filled > 0 and fill_notional > 0 else None
        return {
            "id": children[-1].get("id") if children else None,
            "clientOid": children[-1].get("clientOid") if children else None,
            "amount": filled,
            "filled": filled,
            "average": average,
            "price": average,
            "status": "filled" if filled >= requested - 1e-12 else "partial" if filled > 0 else "unfilled",
            "requested": requested,
            "unfilled": max(0.0, requested - filled),
            "children": children,
            "child_order_count": len(children),
            "elapsed_seconds": time.monotonic() - started,
            "protected_qty": latest_size,
            "protection_updates": protection_updates,
            "protection_ok": protection_ok,
            "execution_mode": "adaptive_ioc",
            "limit_price": limit_price,
            "fixed_tp": fixed_tp,
            "fixed_sl": fixed_sl,
        }

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
        errors: list[Exception] = []
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
            except Exception as exc:
                errors.append(exc)
        if len(errors) == 2:
            raise RuntimeError(f"pending protection queries failed: {errors[-1]}")
        unique: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            key = str(row.get("orderId") or row.get("clientOid") or f"row-{index}")
            unique[key] = row
        return list(unique.values())

    @staticmethod
    def _protection_leg(order: dict[str, Any]) -> str | None:
        leg = str(order.get("leg") or "").lower()
        client_oid = str(order.get("clientOid") or "").lower()
        if leg in {"tp", "sl"}:
            return leg
        if client_oid.startswith("utb-tp-"):
            return "tp"
        if client_oid.startswith("utb-sl-"):
            return "sl"
        return None

    def _bot_protection_orders(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        known_ids = getattr(self, "_known_protection_order_ids", set())
        return [
            order
            for order in orders
            if self._protection_leg(order) is not None
            or str(order.get("orderId") or "") in known_ids
        ]

    @staticmethod
    def _order_identity(order: dict[str, Any]) -> tuple[str, str]:
        return str(order.get("orderId") or ""), str(order.get("clientOid") or "")

    def protection_status(
        self,
        symbol: str,
        *,
        expected_orders: list[dict[str, Any]] | None = None,
        require_only_expected: bool = False,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for _ in range(5):
            try:
                orders = self._pending_plan_orders(symbol)
                bot_orders = self._bot_protection_orders(orders)
                expected = expected_orders or []
                if expected:
                    expected_order_ids = {
                        str(order.get("orderId")) for order in expected if order.get("orderId")
                    }
                    expected_client_oids = {
                        str(order.get("clientOid")) for order in expected if order.get("clientOid")
                    }
                    active = []
                    for pending in orders:
                        order_id = str(pending.get("orderId") or "")
                        client_oid = str(pending.get("clientOid") or "")
                        wanted = next(
                            (
                                order
                                for order in expected
                                if (order_id and order_id == str(order.get("orderId") or ""))
                                or (client_oid and client_oid == str(order.get("clientOid") or ""))
                            ),
                            None,
                        )
                        if wanted is not None:
                            matched = dict(pending)
                            # orderId is also a bot-ownership proof for the
                            # just-created pair when Bitget briefly omits clientOid.
                            matched.setdefault("leg", self._protection_leg(wanted))
                            active.append(matched)
                    owned_or_expected = {
                        self._order_identity(order): order for order in bot_orders + active
                    }
                    bot_orders = list(owned_or_expected.values())
                else:
                    active = bot_orders
                legs = [self._protection_leg(order) for order in active]
                def number(order: dict[str, Any], *names: str) -> Decimal:
                    for name in names:
                        value = order.get(name)
                        if value not in (None, ""):
                            try:
                                return Decimal(str(value))
                            except Exception:
                                return Decimal("0")
                    return Decimal("0")

                prices_ok = all(number(order, "triggerPrice") > 0 for order in active)
                sizes = [number(order, "size", "sizeQty", "qty") for order in active]
                sides = [str(order.get("side") or "").lower() for order in active]
                pair_semantics_ok = (
                    len(sizes) == 2
                    and all(size > 0 for size in sizes)
                    and sizes[0] == sizes[1]
                    and len(set(sides)) == 1
                    and sides[0] in {"buy", "sell"}
                )
                expected_semantics_ok = True
                if expected and len(active) == 2:
                    expected_by_leg = {self._protection_leg(order): order for order in expected}
                    for order in active:
                        leg = self._protection_leg(order)
                        wanted = expected_by_leg.get(leg)
                        if wanted is None:
                            expected_semantics_ok = False
                            break
                        if (
                            number(order, "triggerPrice") != number(wanted, "triggerPrice")
                            or number(order, "size", "sizeQty", "qty")
                            != number(wanted, "size", "sizeQty", "qty")
                            or str(order.get("side") or "").lower()
                            != str(wanted.get("side") or "").lower()
                        ):
                            expected_semantics_ok = False
                            break
                exact_pair = (
                    len(active) == 2
                    and sorted(legs) == ["sl", "tp"]
                    and prices_ok
                    and pair_semantics_ok
                    and expected_semantics_ok
                )
                no_stale = not require_only_expected or len(bot_orders) == len(active)
                if exact_pair and no_stale:
                    return {
                        "ok": True,
                        "supported": True,
                        "count": len(active),
                        "orders": active,
                        "bot_order_count": len(bot_orders),
                    }
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        if last_error is not None:
            return {"ok": False, "supported": True, "reason": f"protection verification failed: {last_error}"}
        return {
            "ok": False,
            "supported": True,
            "count": 0,
            "reason": "one exact bot-owned Elite TP/SL pair was not verified",
        }

    def _cancel_plan_orders(
        self,
        symbol: str,
        orders: list[dict[str, Any]],
    ) -> list[str]:
        sid = self._symbol_id(symbol)
        errors: list[str] = []
        known_ids = getattr(self, "_known_protection_order_ids", set())
        for order in orders:
            if (
                self._protection_leg(order) is None
                and str(order.get("orderId") or "") not in known_ids
            ):
                continue
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
            except Exception as exc:
                errors.append(f"{order_id or client_oid}: {type(exc).__name__}: {exc}")
        return errors

    def cancel_protection(self, symbol: str) -> dict[str, Any]:
        orders = self._bot_protection_orders(self._pending_plan_orders(symbol))
        errors = self._cancel_plan_orders(symbol, orders)
        remaining = self._bot_protection_orders(self._pending_plan_orders(symbol))
        self._known_protection_order_ids = {
            str(order.get("orderId")) for order in remaining if order.get("orderId")
        }
        return {
            "ok": not errors and not remaining,
            "cancelled": len(orders) - len(errors),
            "remaining": remaining,
            "errors": errors,
        }


    def replace_full_protection(
        self,
        symbol: str,
        position_side: str,
        total_qty: float,
        tp_price: float,
        sl_price: float,
    ) -> dict[str, Any]:
        """Replace bot-owned TP/SL with one exact full-position pair."""
        try:
            old_orders = self._bot_protection_orders(self._pending_plan_orders(symbol))
            qty = self._qty(symbol, total_qty)
            orders = self._place_protection(
                symbol,
                str(position_side).lower(),
                qty,
                float(tp_price),
                float(sl_price),
            )
            status = self.protection_status(symbol, expected_orders=orders)
            if not status.get("ok"):
                self._cancel_plan_orders(symbol, orders)
                return {
                    "ok": False,
                    "reason": status.get("reason") or "new TP/SL pair not verified; old pair retained",
                    "orders": orders,
                }
            new_order_ids = {str(order.get("orderId")) for order in orders if order.get("orderId")}
            new_client_oids = {str(order.get("clientOid")) for order in orders if order.get("clientOid")}
            stale = [
                order
                for order in old_orders
                if str(order.get("orderId") or "") not in new_order_ids
                and str(order.get("clientOid") or "") not in new_client_oids
            ]
            cancel_errors = self._cancel_plan_orders(symbol, stale)
            final = self.protection_status(
                symbol,
                expected_orders=orders,
                require_only_expected=True,
            )
            if not final.get("ok"):
                return {
                    "ok": False,
                    "reason": "stale bot TP/SL cancellation or exact-pair verification failed",
                    "cancel_errors": cancel_errors,
                    "orders": orders,
                    "verified": final,
                }
            self._known_protection_order_ids = {
                str(order.get("orderId")) for order in orders if order.get("orderId")
            }
            return {
                "ok": True,
                "orders": orders,
                "verified": final,
                "cancel_warnings": cancel_errors,
            }
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
