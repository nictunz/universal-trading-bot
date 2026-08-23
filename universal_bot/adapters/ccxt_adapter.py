from __future__ import annotations

import time
import uuid
import pandas as pd
import ccxt

from universal_bot.adapters.base import MarketAdapter


class CCXTAdapter(MarketAdapter):
    asset_class = "crypto"

    def __init__(self, exchange_id: str, api_key: str = "", secret: str = "", password: str = ""):
        exchange_class = getattr(ccxt, exchange_id)
        params = {"enableRateLimit": True}
        if api_key:
            params.update({"apiKey": api_key, "secret": secret})
            if password:
                params["password"] = password
        self.exchange_id = exchange_id
        self.exchange = exchange_class(params)
        self.exchange.load_markets()

    @staticmethod
    def _candidates(symbol: str) -> list[str]:
        if "/" not in symbol:
            return [symbol]
        if ":" in symbol:
            return [symbol, symbol.split(":")[0]]
        base, quote = symbol.split("/", 1)
        return [symbol, f"{base}/{quote}:{quote}"]

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

    def fetch_volume_sources(self, symbol: str, timeframe: str, limit: int = 1000) -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        for exchange_id in ("binance", "bitget", "okx", "bybit"):
            try:
                ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
                df = self._fetch(ex, symbol, timeframe, limit)
                if not df.empty:
                    out[exchange_id] = df.volume
            except Exception:
                continue
        return out

    def equity(self) -> float:
        balance = self.exchange.fetch_balance()
        usdt = balance.get("USDT") or balance.get("USDT:USDT") or {}
        return float(usdt.get("free", 0.0) or usdt.get("total", 0.0) or 0.0)

    def position(self, symbol: str):
        """Return one-way net position. Fail closed if the exchange cannot answer."""
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
            nonzero.append({
                "side": side,
                "size": abs(contracts),
                "entry_price": float(p.get("entryPrice") or 0.0),
                "mark_price": float(p.get("markPrice") or 0.0),
                "notional": abs(float(p.get("notional") or 0.0)),
                "leverage": float(p.get("leverage") or 0.0),
                "margin_mode": p.get("marginMode"),
                "raw": p,
            })
        if len(nonzero) > 1:
            raise RuntimeError(f"multiple non-zero positions returned for {symbol}; one-way mode required")
        return nonzero[0] if nonzero else {"side": "FLAT", "size": 0.0, "entry_price": 0.0, "notional": 0.0}

    def configure_live(self, symbol: str, leverage: int, margin_mode: str, require_one_way: bool = True) -> dict:
        if self.exchange_id != "bitget":
            return {"ok": False, "supported": False, "reason": "live configuration is restricted to Bitget"}
        if not self.exchange.has.get("setLeverage"):
            return {"ok": False, "supported": False, "reason": "setLeverage unsupported"}
        if not self.exchange.has.get("setMarginMode"):
            return {"ok": False, "supported": False, "reason": "setMarginMode unsupported"}
        self.exchange.set_margin_mode(margin_mode, symbol)
        self.exchange.set_leverage(int(leverage), symbol)
        if require_one_way and self.exchange.has.get("setPositionMode"):
            try:
                self.exchange.set_position_mode(False, symbol)
            except Exception as exc:
                return {"ok": False, "supported": True, "reason": f"unable to set one-way mode: {exc}"}
        return {"ok": True, "supported": True, "leverage": leverage, "margin_mode": margin_mode, "one_way_required": require_one_way}

    @staticmethod
    def _client_oid(prefix: str = "v15") -> str:
        return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:6]}"[:32]

    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False, **kwargs):
        params = {"reduceOnly": bool(reduce_only), "clientOid": self._client_oid()}
        if kwargs.get("tp_price") is not None:
            params.update({
                "takeProfitPrice": float(kwargs["tp_price"]),
                "tpTriggerBy": "mark",
                "tpOrderType": "market",
            })
        if kwargs.get("sl_price") is not None:
            params.update({
                "stopLossPrice": float(kwargs["sl_price"]),
                "slTriggerBy": "mark",
                "slOrderType": "market",
            })
        if kwargs.get("trigger_protection"):
            params["stopLossPrice"] = float(kwargs["sl_price"])
            params["takeProfitPrice"] = float(kwargs["tp_price"])
        order = self.exchange.create_order(symbol, "market", side.lower(), amount, None, params)
        return order

    def protection_status(self, symbol: str) -> dict:
        """Best-effort verification of exchange-side conditional orders."""
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            protected = []
            for o in orders:
                info = o.get("info") or {}
                text = str(info).lower()
                if o.get("reduceOnly") or "stoploss" in text or "takeprofit" in text or "tpsl" in text or "trigger" in text:
                    protected.append(o)
            return {"ok": bool(protected), "supported": True, "count": len(protected), "orders": protected}
        except Exception as exc:
            return {"ok": False, "supported": True, "reason": f"protection verification failed: {exc}"}

    def cancel_protection(self, symbol: str) -> None:
        try:
            for o in self.exchange.fetch_open_orders(symbol):
                if o.get("reduceOnly") or "trigger" in str(o.get("info") or {}).lower() or "tpsl" in str(o.get("info") or {}).lower():
                    try:
                        self.exchange.cancel_order(o["id"], symbol)
                    except Exception:
                        pass
        except Exception:
            pass
