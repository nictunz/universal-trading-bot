from __future__ import annotations

import ccxt
import pandas as pd

from universal_bot.adapters.base import MarketAdapter
from universal_bot.providers.coinapi import CoinAPIMarketData


class CCXTAdapter(MarketAdapter):
    asset_class = "crypto"

    def __init__(self, exchange_id: str, api_key: str = "", secret: str = "", password: str = "", *, coinapi_api_key: str = "", fallback_exchanges: list[str] | None = None):
        exchange_cls = getattr(ccxt, exchange_id)
        cfg = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
        if api_key:
            cfg["apiKey"] = api_key
        if secret:
            cfg["secret"] = secret
        if password:
            cfg["password"] = password
        self.exchange_id = exchange_id
        self.exchange = exchange_cls(cfg)
        self._volume_exchanges: dict[str, object] = {}
        self._volume_status: dict[str, dict[str, str]] = {}
        self._coinapi = CoinAPIMarketData(coinapi_api_key)
        self._fallback_exchanges = {x.strip().lower() for x in (fallback_exchanges or []) if x.strip()}
        self._provider_volume_cache: dict[tuple[str, str, str], pd.Series] = {}

    def _public_exchange(self, exchange_id: str):
        exchange_id = exchange_id.lower()
        if exchange_id == self.exchange_id and not any((getattr(self.exchange, "apiKey", ""), getattr(self.exchange, "secret", ""), getattr(self.exchange, "password", ""))):
            return self.exchange
        if exchange_id not in self._volume_exchanges:
            exchange_cls = getattr(ccxt, exchange_id)
            self._volume_exchanges[exchange_id] = exchange_cls({"enableRateLimit": True, "options": {"defaultType": "swap"}})
        return self._volume_exchanges[exchange_id]

    @staticmethod
    def _fetch(exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        rows = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.set_index("timestamp")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        return self._fetch(self.exchange, symbol, timeframe, limit)

    def _provider_volume(self, exchange_id: str, symbol: str, timeframe: str, limit: int) -> pd.Series:
        key = (exchange_id, symbol, timeframe)
        cached = self._provider_volume_cache.get(key)
        request_limit = limit if cached is None or len(cached) < min(limit, 100) else 3
        frame = self._coinapi.fetch_latest(exchange_id, symbol, timeframe, request_limit)
        if frame.empty:
            raise RuntimeError("empty CoinAPI OHLCV response")
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
                    status[exchange_id] = {"mode": "COINAPI", "status": "OK"}
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
        # Production CCXT exchanges normally require load_markets() before
        # market(). Lightweight adapters/tests may implement market() directly.
        # Preserve lazy network loading without requiring every adapter double to
        # expose load_markets().
        if not getattr(self.exchange, "markets", None):
            loader = getattr(self.exchange, "load_markets", None)
            if callable(loader):
                loader()
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
                side = "long" if signed >= 0 else "short"
            nonzero.append(p)
        if not nonzero:
            return {"side": "FLAT", "size": 0.0, "entry_price": 0.0, "notional": 0.0}
        p = nonzero[0]
        market = self._market(symbol)
        contracts = abs(float(p.get("contracts") or 0.0))
        size = self._from_exchange_contracts(symbol, contracts) if market.get("contract") else contracts
        entry_price = float(p.get("entryPrice") or 0.0)
        side = "LONG" if str(p.get("side") or "").lower() == "long" else "SHORT"
        return {"side": side, "size": size, "entry_price": entry_price, "notional": size * entry_price, "raw": p}

    def configure_live(self, symbol: str, leverage: int, margin_mode: str, require_one_way: bool = False) -> dict:
        try:
            self.exchange.set_margin_mode(margin_mode, symbol)
        except Exception:
            pass
        try:
            self.exchange.set_leverage(leverage, symbol)
        except Exception:
            pass
        return {"ok": True, "supported": True}

    def market_order(self, symbol: str, side: str, amount: float, *, reduce_only: bool = False, tp_price: float | None = None, sl_price: float | None = None):
        exchange_amount = self._to_exchange_amount(symbol, amount)
        params = {"reduceOnly": reduce_only}
        order = self.exchange.create_order(symbol, "market", side, exchange_amount, None, params)
        return self._normalize_order_amounts(symbol, order)

    def cancel_protection(self, symbol: str) -> None:
        return None

    def protection_status(self, symbol: str) -> dict:
        return {"ok": not False, "supported": False}
