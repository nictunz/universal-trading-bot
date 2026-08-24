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
    "BITGET_EXECUTION_PROFILE": "elite",
    "LEVERAGE": "50",
    "MARGIN_MODE": "crossed",
    "LIVE_REQUIRE_ONE_WAY_MODE": "true",
    "MAX_PYRAMIDING": "2",
    "LIVE_ENTRY_MULTIPLIER": "15",
    "LIVE_MAX_ENTRIES_PER_POSITION": "2",
    "LIVE_MAX_TOTAL_MULTIPLIER": "30",
    "REQUIRE_EXCHANGE_PROTECTION": "true",
}
SYMBOLS = ("BTC/USDT:USDT", "ETH/USDT:USDT")


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


def main() -> None:
    backup = update_env()
    settings = Settings()
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

    print("ELITE_50X_15X2_PROFILE")
    print("NOTE: legacy filename still contains 15x3; behavior is now 15x2.")
    print(f"env_backup={backup.name}")
    print("BOT_MODE=PAPER")
    print("LEVERAGE=50")
    print("LIVE_ENTRY_MULTIPLIER=15")
    print("MAX_ENTRIES=2 (first + one add-on)")
    print("LIVE_MAX_TOTAL_MULTIPLIER=30")
    print("No orders are placed by this script. It only changes leverage/account config.")

    results = []
    for symbol in SYMBOLS:
        sync = adapter.ensure_leverage(symbol, 50)
        check = adapter.configure_live(symbol, 50, "crossed", True)
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
