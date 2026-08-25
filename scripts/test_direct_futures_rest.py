#!/usr/bin/env python3
from __future__ import annotations

import json
import requests


def probe_binance(symbol: str) -> dict:
    url = "https://fapi.binance.com/fapi/v1/klines"
    try:
        r = requests.get(url, params={"symbol": symbol, "interval": "5m", "limit": 5}, timeout=15)
        body = None
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]
        ok = r.status_code == 200 and isinstance(body, list) and len(body) > 0
        return {
            "exchange": "binance",
            "market": "USD-M perpetual",
            "symbol": symbol,
            "endpoint": "/fapi/v1/klines",
            "http": r.status_code,
            "ok": ok,
            "bars": len(body) if isinstance(body, list) else 0,
            "error": None if ok else str(body)[:300],
        }
    except Exception as exc:
        return {
            "exchange": "binance",
            "market": "USD-M perpetual",
            "symbol": symbol,
            "endpoint": "/fapi/v1/klines",
            "http": None,
            "ok": False,
            "bars": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def probe_bybit(symbol: str) -> dict:
    url = "https://api.bybit.com/v5/market/kline"
    try:
        r = requests.get(
            url,
            params={"category": "linear", "symbol": symbol, "interval": "5", "limit": 5},
            timeout=15,
        )
        body = None
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]
        rows = []
        if isinstance(body, dict):
            rows = ((body.get("result") or {}).get("list") or [])
        ok = r.status_code == 200 and isinstance(body, dict) and body.get("retCode") == 0 and len(rows) > 0
        return {
            "exchange": "bybit",
            "market": "USDT linear perpetual",
            "symbol": symbol,
            "endpoint": "/v5/market/kline?category=linear",
            "http": r.status_code,
            "ok": ok,
            "bars": len(rows),
            "error": None if ok else str(body)[:300],
        }
    except Exception as exc:
        return {
            "exchange": "bybit",
            "market": "USDT linear perpetual",
            "symbol": symbol,
            "endpoint": "/v5/market/kline?category=linear",
            "http": None,
            "ok": False,
            "bars": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    checks = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        checks.append(probe_binance(symbol))
        checks.append(probe_bybit(symbol))
    out = {
        "ready": all(x["ok"] for x in checks),
        "read_only": True,
        "orders_placed": False,
        "note": "Direct futures-only REST probe; avoids CCXT spot-market discovery.",
        "checks": checks,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
