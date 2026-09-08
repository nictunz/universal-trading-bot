from __future__ import annotations

import json

from universal_bot.config import Settings
from universal_bot.rebate_transfer import BitgetRebateClient


def main() -> int:
    settings = Settings()
    standard = BitgetRebateClient(
        *settings.bitget_standard_credentials,
        timeout=settings.bitget_elite_request_timeout,
    )
    elite = BitgetRebateClient(
        *settings.bitget_elite_credentials,
        timeout=settings.bitget_elite_request_timeout,
    )
    checks: list[dict[str, object]] = []

    checks.append({"name": "standard_spot_credentials", "ok": standard.configured})
    checks.append({"name": "elite_transfer_credentials", "ok": elite.configured})

    if standard.configured:
        try:
            available = standard.spot_available_usdt()
            checks.append(
                {
                    "name": "spot_balance_query",
                    "ok": True,
                    "available_usdt": str(available),
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "spot_balance_query",
                    "ok": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )

    if elite.configured:
        try:
            records = elite.elite_transfer_records(limit=1)
            checks.append(
                {
                    "name": "elite_transfer_permission",
                    "ok": True,
                    "records_visible": len(records),
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "elite_transfer_permission",
                    "ok": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )

    ready = all(bool(item.get("ok")) for item in checks)
    print(json.dumps({"ready": ready, "checks": checks}, ensure_ascii=False, indent=2))
    print("No transfer was submitted.")
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
