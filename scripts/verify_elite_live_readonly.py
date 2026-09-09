from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from universal_bot.adapters import BitgetEliteAdapter
from universal_bot.config import Settings
from universal_bot.runtime_engine import TradingEngine

SYMBOLS = ("BTC/USDT:USDT",)


def check(name: str, ok: bool, **extra):
    row = {"name": name, "ok": bool(ok)}
    row.update(extra)
    return row


def main() -> None:
    s = Settings()
    checks = []

    # This script is intentionally read-only. It must be run while the persistent
    # .env remains PAPER, and it never calls market_order/set_leverage/plan-order APIs.
    checks.append(check("persistent_mode_is_paper", s.bot_mode.upper() == "PAPER", value=s.bot_mode.upper()))
    checks.append(check("execution_profile", s.bitget_execution_profile.lower() == "elite", value=s.bitget_execution_profile))
    checks.append(check("leverage_setting", int(s.leverage) == 15, value=int(s.leverage)))
    checks.append(check("entry_multiplier", float(s.live_entry_multiplier) == 8.9, value=float(s.live_entry_multiplier)))
    checks.append(check("entry_execution_mode", s.live_entry_execution_mode == "adaptive_ioc", value=s.live_entry_execution_mode))
    checks.append(check("entry_slippage_cap", float(s.live_entry_max_adverse_slippage_percent) == 0.03, value=float(s.live_entry_max_adverse_slippage_percent)))
    checks.append(check("entry_child_orders", int(s.live_entry_max_child_orders) == 5, value=int(s.live_entry_max_child_orders)))
    checks.append(check("entry_window_seconds", float(s.live_entry_execution_window_seconds) == 3.0, value=float(s.live_entry_execution_window_seconds)))
    checks.append(check("max_entries", int(s.live_max_entries_per_position) == 1, value=int(s.live_max_entries_per_position)))
    checks.append(check("max_total_multiplier", float(s.live_max_total_multiplier) == 15.0, value=float(s.live_max_total_multiplier)))
    checks.append(check("exchange_protection_required", bool(s.require_exchange_protection), value=bool(s.require_exchange_protection)))
    checks.append(check("one_way_required", bool(s.live_require_one_way_mode), value=bool(s.live_require_one_way_mode)))
    checks.append(check("discord_enabled", bool(s.discord_notifications_enabled), value=bool(s.discord_notifications_enabled)))
    checks.append(check("discord_webhook_configured", bool(s.discord_webhook_url), value="SET" if s.discord_webhook_url else "MISSING"))

    # Local-only math check for the full-position protection logic.
    long_tp, long_sl = TradingEngine._prices_from_average("LONG", 100.0, 1.0, 2.0)
    short_tp, short_sl = TradingEngine._prices_from_average("SHORT", 100.0, 1.0, 2.0)
    math_ok = (
        abs(long_tp - 101.0) < 1e-9
        and abs(long_sl - 98.0) < 1e-9
        and abs(short_tp - 99.0) < 1e-9
        and abs(short_sl - 102.0) < 1e-9
    )
    checks.append(check("full_position_tp_sl_math", math_ok, long=[long_tp, long_sl], short=[short_tp, short_sl]))

    key, secret, passphrase = s.bitget_elite_credentials
    if not (key and secret and passphrase):
        checks.append(check("elite_credentials", False, value="MISSING"))
        print(json.dumps({"ready": False, "read_only": True, "checks": checks}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    for symbol in SYMBOLS:
        adapter = BitgetEliteAdapter(
            key,
            secret,
            passphrase,
            timeout=s.bitget_elite_request_timeout,
            coinapi_api_key=s.coinapi_api_key,
            fallback_exchanges=s.crypto_fallback_exchange_list,
            community_fallback=False,
        )

        cfg = adapter.configure_live(symbol, int(s.leverage), s.margin_mode, bool(s.live_require_one_way_mode))
        checks.append(check(
            f"{symbol}_classic_elite_account",
            bool(cfg.get("ok")),
            details={
                "symbol": cfg.get("symbol"),
                "margin_mode": cfg.get("margin_mode"),
                "position_mode": cfg.get("position_mode"),
                "account_leverage": cfg.get("account_leverage"),
                "elite_open": cfg.get("elite_open"),
                "reason": cfg.get("reason"),
            },
        ))

        try:
            balance = float(adapter.equity())
            checks.append(check(f"{symbol}_balance_read", balance > 0, available_usdt=balance))
        except Exception as exc:
            checks.append(check(f"{symbol}_balance_read", False, reason=f"{type(exc).__name__}: {exc}"))

        try:
            pos = adapter.position(symbol)
            position_summary = {k: v for k, v in pos.items() if k != "raw"}
            checks.append(check(f"{symbol}_position_read", True, position=position_summary))

            # If flat, there should be no bot-owned protection plans left over.
            # If a position exists, the full protection pair must already verify.
            if pos.get("side") == "FLAT":
                try:
                    bot_plans = [
                        row for row in adapter._pending_plan_orders(symbol)
                        if str(row.get("clientOid") or "").startswith("utb-")
                    ]
                    checks.append(check(
                        f"{symbol}_stale_bot_plans",
                        len(bot_plans) == 0,
                        count=len(bot_plans),
                    ))
                except Exception as exc:
                    checks.append(check(f"{symbol}_stale_bot_plans", False, reason=f"{type(exc).__name__}: {exc}"))
            else:
                protection = adapter.protection_status(symbol)
                checks.append(check(
                    f"{symbol}_existing_full_protection",
                    bool(protection.get("ok")) and int(protection.get("count") or 0) == 2,
                    count=protection.get("count"),
                    reason=protection.get("reason"),
                ))
        except Exception as exc:
            checks.append(check(f"{symbol}_position_read", False, reason=f"{type(exc).__name__}: {exc}"))

        # Critical LIVE market-data test. Universal v15 uses four normalized
        # futures-volume sources, so all four must be readable from this server.
        try:
            base = adapter.fetch_ohlcv(symbol, s.timeframe, limit=220)
            checks.append(check(f"{symbol}_bitget_ohlcv", len(base) >= 200, bars=len(base)))
        except Exception as exc:
            checks.append(check(f"{symbol}_bitget_ohlcv", False, reason=f"{type(exc).__name__}: {exc}"))

        try:
            sources = adapter.fetch_volume_sources(symbol, s.timeframe, limit=220)
            status = adapter.volume_source_status()
            four = ("binance", "bitget", "okx", "bybit")
            all_ok = all(
                name in sources
                and len(sources[name]) >= 200
                and str(status.get(name, {}).get("status", "")).upper() == "OK"
                for name in four
            )
            safe_status = {
                name: {
                    "status": status.get(name, {}).get("status"),
                    "mode": status.get(name, {}).get("mode"),
                    "bars": len(sources[name]) if name in sources else 0,
                    "error": status.get(name, {}).get("error"),
                }
                for name in four
            }
            checks.append(check(f"{symbol}_four_exchange_volume", all_ok, sources=safe_status))
        except Exception as exc:
            checks.append(check(f"{symbol}_four_exchange_volume", False, reason=f"{type(exc).__name__}: {exc}"))

    ready = all(row.get("ok") is True for row in checks)
    result = {
        "ready": ready,
        "read_only": True,
        "orders_placed": False,
        "profile": {
            "leverage": int(s.leverage),
            "entry_multiplier": float(s.live_entry_multiplier),
            "max_entries": int(s.live_max_entries_per_position),
            "max_total_multiplier": float(s.live_max_total_multiplier),
        },
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if not ready:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
