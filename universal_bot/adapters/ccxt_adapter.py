from __future__ import annotations

import time
import uuid
import pandas as pd
import ccxt

from universal_bot.adapters.base import MarketAdapter
from universal_bot.providers.coinapi import CoinAPIMarketData


class CCXTAdapter(MarketAdapter):
    asset_class = "crypto"

    def __init__(
        self,
        exchange_id: str,
        api_key: str = "",
        secret: str = "",
        password: str = "",
        *,
        coinapi_api_key: str = "",
        fallback_exchanges: list[str] | None = None,
    ):
        exchange_class = getattr(ccxt, exchange_id)
        params = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
        if api_key:
            params.update({"apiKey": api_key, "secret": secret})
            if password:
                params["password"] = password
        self.exchange_id = exchange_id
        self.exchange = exchange_class(params)
        self.exchange.load_markets()
        self._volume_exchanges: dict[str, object] = {exchange_id: self.exchange}
        self._fallback_exchanges = {x.lower() for x in (fallback_exchanges or [])}
        self._coinapi = CoinAPIMarketData(coinapi_api_key)
        self._volume_status: dict[str, dict[str, str]] = {}
        self._provider_volume_cache: dict[tuple[str, str, str], pd.Series] = {}

    @staticmethod
    def _candidates(symbol: str) -> list[str]:
        if "/" not in symbol:
            return [symbol]
        if ":" in symbol:
            return [symbol, symbol.split(":")[0]]
        base, quote = symbol.split("/", 1)
        return [symbol, f"{base}/{quote}:{quote}"]

    def _public_exchange(self, exchange_id: str):
        cached = self._volume_exchanges.get(exchange_id)
        if cached is not None:
            return cached
        ex = getattr(ccxt, exchange_id)({"enableRateLimit": True, "options": {"defaultType": "swap"}})
        ex.load_markets()
        self._volume_exchanges[exchange_id] = ex
        return ex

    def _fetch(self, exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        last_error = None
        for candidate in self._candidates(symbol):
            try:
                rows = exchange.fetch_ohlcv(candidate, timeframe=timeframe, limit=limit)
                df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
                if df.empty:
                    continue
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                return df.set_index("timestamp").sort_index()
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        return self._fetch(self.exchange, symbol, timeframe, limit)

    def _provider_volume(self, exchange_id: str, symbol: str, timeframe: str, limit: int) -> pd.Series:
        key = (exchange_id, symbol, timeframe)
        cached = self._provider_volume_cache.get(key)
        # First request seeds enough history for the volume SMA. Later completed
        # bars only need a few newest candles; merge them into the local cache.
        request_limit = limit if cached is None or len(cached) < min(limit, 100) else 3
        frame = self._coinapi.fetch_latest(exchange_id, symbol, timeframe, request_limit)
        if frame.empty:
            raise RuntimeError("empty provider OHLCV response")
        latest = frame.volume.astype(float)
        if cached is not None and not cached.empty:
            latest = pd.concat([cached, latest]).sort_index()
            latest = latest.loc[~latest.index.duplicated(keep="last")]
        latest = latest.tail(limit)
        self._provider_volume_cache[key] = latest
        return latest

    def fetch_volume_sources(self, symbol: str, timeframe: str, limit: int = 1000) -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        status: dict[str, dict[str, str]] = {}
        for exchange_id in ("binance", "bitget", "okx", "bybit"):
            direct_error: Exception | None = None
            try:
                ex = self._public_exchange(exchange_id)
                df = self._fetch(ex, symbol, timeframe, limit)
                if not df.empty:
                    out[exchange_id] = df.volume.astype(float)
                    status[exchange_id] = {"mode": "DIRECT", "status": "OK"}
                    continue
                direct_error = RuntimeError("empty direct OHLCV response")
            except Exception as exc:
                direct_error = exc

            if exchange_id in self._fallback_exchanges and self._coinapi.enabled:
                try:
                    out[exchange_id] = self._provider_volume(exchange_id, symbol, timeframe, limit)
                    status[exchange_id] = {"mode": "PROVIDER", "status": "OK"}
                    continue
                except Exception as exc:
                    status[exchange_id] = {"mode": "PROVIDER", "status": "FAIL", "error": str(exc)[:180]}
                    continue

            mode = "PROVIDER_NOT_CONFIGURED" if exchange_id in self._fallback_exchanges else "DIRECT"
            status[exchange_id] = {
                "mode": mode,
                "status": "FAIL",
                "error": str(direct_error)[:180] if direct_error else "unknown volume-source error",
            }
        self._volume_status = status
        return out

    def volume_source_status(self) -> dict[str, dict[str, str]]:
        return {k: dict(v) for k, v in self._volume_status.items()}

    def equity(self) -> float:
        balance = self.exchange.fetch_balance()
        usdt = balance.get("USDT") or balance.get("USDT:USDT") or {}
        return float(usdt.get("total", 0.0) or usdt.get("free", 0.0) or 0.0)

    def _market(self, symbol: str) -> dict:
        market = self.exchange.market(symbol)
        if not market:
            raise RuntimeError(f"unknown market: {symbol}")
        return market

    def _to_exchange_amount(self, symbol: str, base_amount: float) -> float:
        market = self._market(symbol)
        if market.get("contract") and market.get("contractSize"):
            contracts = base_amount / float(market["contractSize"])
            contracts = float(self.exchange.amount_to_precision(symbol, contracts))
            if contracts <= 0:
                raise RuntimeError("calculated contract amount is below exchange precision/minimum")
            return contracts
        amount = float(self.exchange.amount_to_precision(symbol, base_amount))
        if amount <= 0:
            raise RuntimeError("calculated amount is below exchange precision/minimum")
        return amount

    def _from_exchange_contracts(self, symbol: str, contracts: float) -> float:
        market = self._market(symbol)
        if market.get("contract") and market.get("contractSize"):
            return abs(contracts) * float(market["contractSize"])
        return abs(contracts)

    def _normalize_order_amounts(self, symbol: str, order: dict) -> dict:
        result = dict(order)
        for key in ("amount", "filled", "remaining"):
            value = order.get(key)
            if value is not None:
                try:
                    result[f"exchange_{key}"] = float(value)
                    result[key] = self._from_exchange_contracts(symbol, float(value))
                except (TypeError, ValueError):
                    pass
        return result

    def position(self, symbol: str):
        if not self.exchange.has.get("fetchPositions"):
            raise RuntimeError("exchange does not support fetchPositions")
        positions = self.exchange.fetch_positions([symbol])
        nonzero = []
        for p in positions:
            contracts = float(p.get("contracts") or 0.0)
            side = (p.get("side") or "").lower()
            if contracts <= 0 and abs(float(p.get("notional") or 0.0)) <= 0:
                continue
            if side not in {"long", "short"}:
                signed = float(p.get("contractSize") or 1.0) * contracts
                side = "LONG" if signed > 0 else "SHORT"
            else:
                side = side.upper()
            nonzero.append({"side": side, "size": self._from_exchange_contracts(symbol, contracts), "contracts": abs(contracts), "entry_price": float(p.get("entryPrice") or 0.0), "mark_price": float(p.get("markPrice") or 0.0), "notional": abs(float(p.get("notional") or 0.0)), "leverage": float(p.get("leverage") or 0.0), "margin_mode": p.get("marginMode"), "raw": p})
        if len(nonzero) > 1:
            raise RuntimeError(f"multiple non-zero positions returned for {symbol}; one-way mode required")
        return nonzero[0] if nonzero else {"side": "FLAT", "size": 0.0, "entry_price": 0.0, "notional": 0.0}

    def configure_live(self, symbol: str, leverage: int, margin_mode: str, require_one_way: bool = True) -> dict:
        if self.exchange_id != "bitget":
            return {"ok": False, "supported": False, "reason": "live configuration is restricted to Bitget"}
        if not self.exchange.has.get("setLeverage") or not self.exchange.has.get("setMarginMode"):
            return {"ok": False, "supported": False, "reason": "Bitget leverage/margin API unsupported by installed CCXT"}
        self.exchange.set_margin_mode(margin_mode, symbol)
        self.exchange.set_leverage(int(leverage), symbol)
        if require_one_way:
            if not self.exchange.has.get("setPositionMode"):
                return {"ok": False, "supported": True, "reason": "cannot verify/enforce one-way position mode"}
            try:
                self.exchange.set_position_mode(False, symbol)
            except Exception as exc:
                return {"ok": False, "supported": True, "reason": f"unable to set one-way mode: {exc}"}
        return {"ok": True, "supported": True, "leverage": leverage, "margin_mode": margin_mode, "one_way_required": require_one_way}

    @staticmethod
    def _client_oid(prefix: str = "v15") -> str:
        return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:6]}"[:32]

    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False, **kwargs):
        exchange_amount = self._to_exchange_amount(symbol, amount)
        params = {"reduceOnly": bool(reduce_only), "clientOid": self._client_oid()}
        if kwargs.get("tp_price") is not None:
            params["takeProfit"] = {"triggerPrice": float(kwargs["tp_price"]), "type": "market"}
        if kwargs.get("sl_price") is not None:
            params["stopLoss"] = {"triggerPrice": float(kwargs["sl_price"]), "type": "market"}
        if kwargs.get("tp_price") is not None or kwargs.get("sl_price") is not None:
            params["triggerType"] = "mark_price"
        order = self.exchange.create_order(symbol, "market", side.lower(), exchange_amount, None, params)
        return self._normalize_order_amounts(symbol, order)

    def protection_status(self, symbol: str) -> dict:
        try:
            regular = self.exchange.fetch_open_orders(symbol)
            trigger = self.exchange.fetch_open_orders(symbol, params={"trigger": True})
            tpsl = self.exchange.fetch_open_orders(symbol, params={"planType": "profit_loss", "trigger": True})
            orders = regular + trigger + tpsl
            protected = []
            seen = set()
            for o in orders:
                oid = o.get("id") or str(o.get("info"))
                if oid in seen:
                    continue
                seen.add(oid)
                text = str(o.get("info") or {}).lower()
                if o.get("reduceOnly") or "stoploss" in text or "takeprofit" in text or "tpsl" in text or "trigger" in text or o.get("stopLossPrice") or o.get("takeProfitPrice"):
                    protected.append(o)
            return {"ok": bool(protected), "supported": True, "count": len(protected), "orders": protected}
        except Exception as exc:
            return {"ok": False, "supported": True, "reason": f"protection verification failed: {exc}"}

    def cancel_protection(self, symbol: str) -> None:
        try:
            orders = self.exchange.fetch_open_orders(symbol, params={"planType": "profit_loss", "trigger": True})
        except Exception:
            orders = []
        for o in orders:
            oid = o.get("id")
            if oid:
                try:
                    self.exchange.cancel_order(oid, symbol, {"trigger": True})
                except Exception:
                    pass
