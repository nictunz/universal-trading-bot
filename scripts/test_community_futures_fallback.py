from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from universal_bot.providers.coinmetrics import CoinMetricsCommunityMarketData


def main() -> int:
    provider = CoinMetricsCommunityMarketData()
    checks = []
    for symbol in ("BTC/USDT:USDT", "ETH/USDT:USDT"):
        for exchange in ("binance", "bybit"):
            item = {
                "exchange": exchange,
                "symbol": symbol,
                "market_id": provider.market_id(exchange, symbol),
                "ok": False,
            }
            try:
                frame = provider.fetch_latest(exchange, symbol, "5m", 220)
                bars = len(frame)
                latest = frame.index[-1].to_pydatetime() if bars else None
                if latest is not None and latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                age_minutes = (
                    (datetime.now(timezone.utc) - latest.astimezone(timezone.utc)).total_seconds() / 60.0
                    if latest is not None
                    else None
                )
                positive_volume = bool(bars and (frame["volume"].astype(float) > 0).any())
                ok = bool(
                    item["market_id"].endswith("-future")
                    and bars >= 80
                    and age_minutes is not None
                    and age_minutes <= 20
                    and positive_volume
                )
                item.update(
                    {
                        "ok": ok,
                        "bars": bars,
                        "latest": latest.isoformat() if latest is not None else None,
                        "age_minutes": round(age_minutes, 2) if age_minutes is not None else None,
                        "positive_volume": positive_volume,
                    }
                )
            except Exception as exc:
                item["error"] = f"{type(exc).__name__}: {exc}"
            checks.append(item)

    ready = all(x.get("ok") is True for x in checks)
    print(
        json.dumps(
            {
                "ready": ready,
                "read_only": True,
                "orders_placed": False,
                "provider": "Coin Metrics Community",
                "purpose": "Binance/Bybit futures-volume fallback only",
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
