from __future__ import annotations

import json
import ssl
import sys
from datetime import datetime, timedelta, timezone

import requests


def check_http(label: str, url: str) -> bool:
    try:
        r = requests.get(url, timeout=20, stream=True, allow_redirects=True)
        ok = 200 <= r.status_code < 300
        print(f"{label}: {'OK' if ok else 'FAIL'} HTTP={r.status_code} URL={r.url}")
        if not ok:
            print("  body=", (r.text or "")[:240].replace("\n", " "))
        return ok
    except Exception as exc:
        print(f"{label}: FAIL {type(exc).__name__}: {exc}")
        return False


def check_binance_ws() -> bool:
    try:
        from websockets.sync.client import connect
        url = "wss://fstream.binance.com/ws/ethusdt@kline_5m"
        with connect(url, open_timeout=15, close_timeout=3, ssl=ssl.create_default_context()) as ws:
            raw = ws.recv(timeout=15)
            msg = json.loads(raw)
            k = msg.get("k") or {}
            ok = bool(k and k.get("s") == "ETHUSDT" and k.get("i") == "5m")
            print(f"BINANCE_WS: {'OK' if ok else 'FAIL'} symbol={k.get('s')} interval={k.get('i')} volume={k.get('v')}")
            return ok
    except Exception as exc:
        print(f"BINANCE_WS: FAIL {type(exc).__name__}: {exc}")
        return False


def check_bybit_ws() -> bool:
    try:
        from websockets.sync.client import connect
        url = "wss://stream.bybit.com/v5/public/linear"
        with connect(url, open_timeout=15, close_timeout=3, ssl=ssl.create_default_context()) as ws:
            ws.send(json.dumps({"op": "subscribe", "args": ["kline.5.ETHUSDT"]}))
            for _ in range(8):
                raw = ws.recv(timeout=15)
                msg = json.loads(raw)
                if str(msg.get("topic", "")).startswith("kline.5.ETHUSDT"):
                    rows = msg.get("data") or []
                    row = rows[0] if rows else {}
                    print(f"BYBIT_WS: OK symbol=ETHUSDT interval=5 volume={row.get('volume')} confirm={row.get('confirm')}")
                    return True
            print("BYBIT_WS: FAIL no kline message received")
            return False
    except Exception as exc:
        print(f"BYBIT_WS: FAIL {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    now = datetime.now(timezone.utc)
    monthly = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    daily = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    print("===== OFFICIAL PUBLIC ARCHIVES =====")
    binance_url = f"https://data.binance.vision/data/futures/um/monthly/klines/ETHUSDT/5m/ETHUSDT-5m-{monthly}.zip"
    bybit_url = f"https://public.bybit.com/trading/ETHUSDT/ETHUSDT{daily}.csv.gz"
    a = check_http("BINANCE_ARCHIVE", binance_url)
    b = check_http("BYBIT_ARCHIVE", bybit_url)

    print("\n===== OFFICIAL PUBLIC WEBSOCKETS =====")
    c = check_binance_ws()
    d = check_bybit_ws()

    print("\n===== SUMMARY =====")
    print(json.dumps({
        "binance_archive": a,
        "bybit_archive": b,
        "binance_ws": c,
        "bybit_ws": d,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
