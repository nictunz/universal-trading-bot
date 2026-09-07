from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from universal_bot.adapters import BitgetEliteAdapter
from universal_bot.config import Settings


ENV_PATH = ROOT / ".env"
PROFILE = {
    "BOT_MODE": "PAPER",
    "EXCHANGE": "bitget",
    "ASSET_CLASS": "crypto",
    "SYMBOL": "BTC/USDT:USDT",
    "SYMBOLS": "BTC/USDT:USDT",
    "TIMEFRAME": "15m",
    "POLL_SECONDS": "2",
    "VOLUME_LOOKBACK": "40",
    "VOLUME_BREAK_MULTIPLIER": "6.4",
    "USE_FOUR_CRYPTO_EXCHANGES": "true",
    "MIN_ONE_BAR_VOL": "0.1",
    "MAX_ONE_BAR_VOL": "3.6",
    "VOLATILITY_BARS": "36",
    "TP_VOL_MULTIPLIER": "3.8",
    "SL_VOL_MULTIPLIER": "1.0",
    "MIN_TP_PERCENT": "0.3",
    "MAX_TP_PERCENT": "2.1",
    "MIN_SL_PERCENT": "0.3",
    "MAX_SL_PERCENT": "1.9",
    "USE_NBAR_VOLATILITY_BLOCK": "true",
    "NBAR_VOLATILITY_BARS": "200",
    "MAX_NBAR_VOLATILITY": "6.3",
    "USE_ADX_FILTER": "false",
    "ADX_LENGTH": "7",
    "ADX_MIN": "11.6",
    "ADX_MAX": "80.5",
    "USE_RSI_FILTER": "true",
    "RSI_LENGTH": "10",
    "RSI_OVERSOLD_MIN": "20.0",
    "RSI_OVERSOLD_MAX": "42.0",
    "RSI_OVERBOUGHT_MIN": "65.6",
    "RSI_OVERBOUGHT_MAX": "74.7",
    "ALLOW_LONG": "true",
    "ALLOW_SHORT": "true",
    "COOLDOWN_BARS": "3",
    "REENTRY_BARS": "5",
    "BLOCK_WEEKEND": "false",
    "EXCLUDED_HOURS": "",
    "ORDER_PERCENT_OF_EQUITY": "860",
    "INITIAL_CAPITAL": "1000",
    "BACKTEST_FEE_PERCENT": "0.02",
    "BACKTEST_SLIPPAGE_PERCENT": "0.01",
    "BACKTEST_COMPOUNDING_ENABLED": "true",
    "BACKTEST_EXECUTION_MODEL": "signal_close",
    "ADAPTIVE_REGIME_ENABLED": "false",
    "BITGET_EXECUTION_PROFILE": "elite",
    "BITGET_API_FAMILY": "classic-first",
    "LEVERAGE": "15",
    "MARGIN_MODE": "crossed",
    "LIVE_REQUIRE_ONE_WAY_MODE": "true",
    "MAX_PYRAMIDING": "1",
    "LIVE_ENTRY_MULTIPLIER": "8.6",
    "LIVE_MAX_ENTRIES_PER_POSITION": "1",
    "LIVE_MAX_TOTAL_MULTIPLIER": "15",
    "REQUIRE_EXCHANGE_PROTECTION": "true",
}
SYMBOLS = ("BTC/USDT:USDT",)


def update_env() -> Path:
    ENV_PATH.touch(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ROOT / f".env.bak-live-profile-{stamp}"
    shutil.copy2(ENV_PATH, backup)

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in PROFILE:
            out.append(f"{key}={PROFILE[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in PROFILE.items():
        if key not in seen:
            out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    ENV_PATH.chmod(0o600)
    return backup


def sync_dashboard_strategy_store(settings: Settings) -> Path | None:
    from universal_bot.strategy_dashboard import FIELDS

    store = ROOT / "data" / "dashboard-strategy-settings.json"
    mobile_store = Path.home() / ".cache" / "universal-trading-bot" / "mobile-strategy-settings.json"
    values = {field: getattr(settings, field) for field in FIELDS}
    text = json.dumps(values, ensure_ascii=False, indent=2) + "\n"

    backup = None
    if store.exists() and store.read_text(encoding="utf-8").strip() != text.strip():
        backup_dir = ROOT / "data" / "strategy-settings-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"strategy-settings-before-live-{stamp}.json"
        shutil.copy2(store, backup)

    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(text, encoding="utf-8")
    mobile_store.parent.mkdir(parents=True, exist_ok=True)
    mobile_store.write_text(text, encoding="utf-8")
    return backup


def main() -> None:
    backup = update_env()
    settings = Settings()
    strategy_backup = sync_dashboard_strategy_store(settings)
    key, secret, passphrase = settings.bitget_elite_credentials
    if not (key and secret and passphrase):
        raise SystemExit("Elite credentials are missing in .env")

    adapter = BitgetEliteAdapter(
        key,
        secret,
        passphrase,
        timeout=settings.bitget_elite_request_timeout,
        fallback_exchanges=settings.crypto_fallback_exchange_list,
        community_fallback=False,
    )

    print("BTC_15M_JSON_LIVE_PROFILE")
    print("NOTE: legacy filename is retained for compatibility; sizing follows the selected JSON.")
    print(f"env_backup={backup.name}")
    print(f"strategy_settings_backup={strategy_backup.name if strategy_backup else 'unchanged'}")
    print("BOT_MODE=PAPER")
    print("LEVERAGE=15")
    print("LIVE_ENTRY_MULTIPLIER=8.6 (진입_비중_pct=860)")
    print("MAX_ENTRIES=1")
    print("LIVE_MAX_TOTAL_MULTIPLIER=15")
    print("No orders are placed by this script. It only changes leverage/account config.")

    results = []
    for symbol in SYMBOLS:
        sync = adapter.ensure_leverage(symbol, 15)
        check = adapter.configure_live(symbol, 15, "crossed", True)
        row = {
            "symbol": adapter._symbol_id(symbol),
            "leverage_sync": sync,
            "ready": bool(check.get("ok")),
            "position_mode": check.get("position_mode"),
            "margin_mode": check.get("margin_mode"),
            "account_leverage": check.get("account_leverage"),
            "elite_open": check.get("elite_open"),
            "contract_max_leverage": check.get("contract_max_leverage"),
            "reason": check.get("reason"),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))

    if not all(row["ready"] for row in results):
        raise SystemExit("One or more symbols are not ready after leverage sync")

    print("PROFILE_READY=true")
    print("The .env file is still PAPER. Do not switch to LIVE until the remaining safety checks pass.")


if __name__ == "__main__":
    main()
