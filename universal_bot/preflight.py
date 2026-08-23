from __future__ import annotations

from datetime import datetime, timezone
from universal_bot.config import Settings
from universal_bot.main import build_adapter


def check_live_readiness(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    checks: list[dict] = []
    live = settings.bot_mode.upper() == "LIVE"
    checks.append({"name": "mode", "ok": True, "value": settings.bot_mode})
    if settings.exchange.lower() != "bitget" and live:
        checks.append({"name": "exchange", "ok": False, "reason": "LIVE is restricted to Bitget"})
        return {"ready": False, "checks": checks, "timestamp": datetime.now(timezone.utc).isoformat()}
    try:
        adapter = build_adapter(settings)
        market = adapter.exchange.market(settings.symbol)
        checks.append({"name": "market", "ok": bool(market and market.get("active", True)), "contract": bool(market.get("contract")), "contract_size": market.get("contractSize")})
        checks.append({"name": "fetch_positions", "ok": bool(adapter.exchange.has.get("fetchPositions"))})
        checks.append({"name": "set_leverage", "ok": bool(adapter.exchange.has.get("setLeverage"))})
        checks.append({"name": "set_margin_mode", "ok": bool(adapter.exchange.has.get("setMarginMode"))})
        checks.append({"name": "set_position_mode", "ok": bool(adapter.exchange.has.get("setPositionMode")) if settings.live_require_one_way_mode else True})
        if live:
            balance = adapter.equity()
            checks.append({"name": "balance", "ok": balance > 0, "equity": balance})
            pos = adapter.position(settings.symbol)
            checks.append({"name": "position_query", "ok": True, "position": {k: v for k, v in pos.items() if k != "raw"}})
            if pos.get("side") != "FLAT":
                protection = adapter.protection_status(settings.symbol)
                checks.append({"name": "existing_protection", "ok": protection.get("ok", False), "details": {k: v for k, v in protection.items() if k != "orders"}})
    except Exception as exc:
        checks.append({"name": "exchange_connection", "ok": False, "reason": f"{type(exc).__name__}: {exc}"})
    required = {"market", "fetch_positions", "set_leverage", "set_margin_mode"}
    if settings.live_require_one_way_mode:
        required.add("set_position_mode")
    ready = all(c.get("ok") for c in checks if c.get("name") in required) and all(c.get("ok") for c in checks if c.get("name") in {"balance", "position_query", "existing_protection"})
    if not live:
        ready = False
    return {"ready": ready, "checks": checks, "timestamp": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import json
    print(json.dumps(check_live_readiness(), ensure_ascii=False, indent=2, default=str))
