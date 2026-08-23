from __future__ import annotations

import json

from universal_bot.adapters.ccxt_adapter import CCXTAdapter


SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "5m"

adapter = CCXTAdapter("bitget")
exchange = adapter.exchange
market = exchange.market(SYMBOL)


def feature(path: str):
    fn = getattr(exchange, "feature_value", None)
    if fn is None:
        return None
    try:
        return fn(SYMBOL, "createOrder", path)
    except Exception:
        return None


frame = adapter.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=5)
if frame.empty:
    raise RuntimeError("Bitget returned no ETH/USDT:USDT 5m OHLCV")

checks = {
    "exchange": exchange.id,
    "ccxt_version": __import__("ccxt").__version__,
    "symbol": market.get("symbol"),
    "active": market.get("active"),
    "swap": market.get("swap"),
    "linear": market.get("linear"),
    "contract": market.get("contract"),
    "contract_size": market.get("contractSize"),
    "fetch_positions": exchange.has.get("fetchPositions"),
    "set_leverage": exchange.has.get("setLeverage"),
    "set_margin_mode": exchange.has.get("setMarginMode"),
    "set_position_mode": exchange.has.get("setPositionMode"),
    "attached_stop_loss": feature("stopLoss"),
    "attached_take_profit": feature("takeProfit"),
    "ohlcv_rows": len(frame),
    "ohlcv_last": frame.index[-1].isoformat(),
}

required_true = (
    "swap",
    "linear",
    "contract",
    "fetch_positions",
    "set_leverage",
    "set_margin_mode",
    "set_position_mode",
)
for key in required_true:
    if not checks.get(key):
        raise RuntimeError(f"required Bitget capability is unavailable: {key}={checks.get(key)!r}")

# Attached TP/SL support is mandatory for the fail-closed live design.  CCXT
# may expose a dict or boolean depending on its feature schema; only explicit
# False is a hard failure, while None is reported for private-account testing.
for key in ("attached_stop_loss", "attached_take_profit"):
    if checks[key] is False:
        raise RuntimeError(f"CCXT reports {key} unsupported for {SYMBOL}")

print(json.dumps(checks, ensure_ascii=False, indent=2, default=str))
