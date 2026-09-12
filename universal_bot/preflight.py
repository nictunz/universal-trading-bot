from __future__ import annotations

from datetime import datetime, timezone

from universal_bot.adapters import BitgetEliteAdapter, BitgetUtaAdapter, CCXTAdapter, YFinanceMarketAdapter
from universal_bot.config import Settings


def _adapter(settings: Settings):
    if settings.asset_class.lower() in {"stock", "stocks", "etf", "equity"}:
        return YFinanceMarketAdapter()

    exchange = settings.exchange.lower()
    profile = settings.bitget_execution_profile.strip().lower()
    if exchange == "bitget" and profile == "elite":
        key, secret, passphrase = settings.bitget_elite_credentials
        kwargs = {
            "timeout": settings.bitget_elite_request_timeout,
            "fallback_exchanges": settings.crypto_fallback_exchange_list,
            "community_fallback": False,
        }
        family = settings.bitget_api_family.strip().lower()
        if family in {"uta", "uta-v3", "v3"}:
            return BitgetUtaAdapter(key, secret, passphrase, **kwargs)
        classic = BitgetEliteAdapter(key, secret, passphrase, **kwargs)
        if family in {"classic-first", "auto-classic"}:
            try:
                classic.account_info(settings.symbol)
                return classic
            except Exception:
                uta = BitgetUtaAdapter(key, secret, passphrase, **kwargs)
                info = uta.account_info(settings.symbol)
                mode = str(info.get("accountMode") or "").lower()
                if mode in {"unified", "hybrid"}:
                    return uta
                raise RuntimeError(f"UTA account mode is not unified/hybrid: {mode or 'unknown'}")
        return classic

    bitget_key, bitget_secret, bitget_passphrase = settings.bitget_standard_credentials
    keys = {
        "binance": (settings.binance_api_key, settings.binance_api_secret, ""),
        "bitget": (bitget_key, bitget_secret, bitget_passphrase),
        "okx": (settings.okx_api_key, settings.okx_api_secret, settings.okx_api_passphrase),
        "bybit": (settings.bybit_api_key, settings.bybit_api_secret, ""),
    }
    key, secret, password = keys.get(exchange, ("", "", ""))
    return CCXTAdapter(exchange, key, secret, password)


def check_live_readiness(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    checks: list[dict] = []
    live = settings.bot_mode.upper() == "LIVE"
    profile = settings.bitget_execution_profile.strip().lower()

    checks.append({"name": "mode", "ok": True, "value": settings.bot_mode})
    checks.append({"name": "execution_profile", "ok": profile in {"elite", "standard"}, "value": profile})

    if settings.exchange.lower() != "bitget" and live:
        checks.append({"name": "exchange", "ok": False, "reason": "LIVE is restricted to Bitget"})
        return {"ready": False, "checks": checks, "timestamp": datetime.now(timezone.utc).isoformat()}

    try:
        adapter = _adapter(settings)

        if settings.exchange.lower() == "bitget" and profile == "elite":
            key, secret, passphrase = settings.bitget_elite_credentials
            checks.append({
                "name": "elite_credentials",
                "ok": bool(key and secret and passphrase),
                "value": "configured" if key and secret and passphrase else "missing",
            })
            checks.append({
                "name": "elite_margin_setting",
                "ok": settings.margin_mode.lower() in {"cross", "crossed"},
                "value": settings.margin_mode,
            })

            api_family = "uta-v3" if isinstance(adapter, BitgetUtaAdapter) else "classic-v2"
            account_check_name = "elite_uta_account" if api_family == "uta-v3" else "elite_classic_account"
            config = adapter.configure_live(
                settings.symbol,
                int(settings.leverage),
                settings.margin_mode,
                bool(settings.live_require_one_way_mode),
            )
            checks.append({
                "name": account_check_name,
                "ok": bool(config.get("ok")),
                "details": config,
            })

            if live and config.get("ok"):
                balance = adapter.equity()
                checks.append({"name": "balance", "ok": balance > 0, "available_usdt": balance})
                pos = adapter.position(settings.symbol)
                checks.append({
                    "name": "position_query",
                    "ok": True,
                    "position": {k: v for k, v in pos.items() if k != "raw"},
                })
                if pos.get("side") != "FLAT":
                    protection = adapter.protection_status(settings.symbol)
                    checks.append({
                        "name": "existing_protection",
                        "ok": protection.get("ok", False),
                        "details": {k: v for k, v in protection.items() if k != "orders"},
                    })

            required_names = {
                "execution_profile",
                "elite_credentials",
                "elite_margin_setting",
                account_check_name,
            }
            if live:
                required_names.update({"balance", "position_query"})
                if any(c.get("name") == "existing_protection" for c in checks):
                    required_names.add("existing_protection")

            ready = live and all(
                c.get("ok") for c in checks if c.get("name") in required_names
            ) and required_names.issubset({c.get("name") for c in checks})
            return {
                "ready": ready,
                "profile": "elite",
                "api_family": api_family,
                "checks": checks,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        market = adapter.exchange.market(settings.symbol)
        checks.append({
            "name": "market",
            "ok": bool(market and market.get("active", True)),
            "contract": bool(market.get("contract")),
            "contract_size": market.get("contractSize"),
        })
        checks.append({"name": "fetch_positions", "ok": bool(adapter.exchange.has.get("fetchPositions"))})
        checks.append({"name": "set_leverage", "ok": bool(adapter.exchange.has.get("setLeverage"))})
        checks.append({"name": "set_margin_mode", "ok": bool(adapter.exchange.has.get("setMarginMode"))})
        checks.append({
            "name": "set_position_mode",
            "ok": bool(adapter.exchange.has.get("setPositionMode")) if settings.live_require_one_way_mode else True,
        })
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
    if live:
        required.update({"balance", "position_query"})
    # Exceptions can leave only a prefix of the checks populated. Never let
    # all([]) or successful earlier checks turn an incomplete run into READY.
    completed = {c.get("name") for c in checks}
    ready = (
        live
        and required.issubset(completed)
        and all(c.get("ok") is True for c in checks)
    )
    return {"ready": ready, "profile": profile, "checks": checks, "timestamp": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import json

    print(json.dumps(check_live_readiness(), ensure_ascii=False, indent=2, default=str))
