from __future__ import annotations

from datetime import datetime, timezone

from universal_bot.config import Settings
from universal_bot.discord_notifier import DiscordNotifier


def main() -> None:
    s = Settings()
    notifier = DiscordNotifier(
        s.discord_webhook_url,
        enabled=s.discord_notifications_enabled,
        timeout=s.discord_timeout,
    )
    if not notifier.configured:
        raise SystemExit("DISCORD_WEBHOOK_URL is not configured")
    if not s.discord_notifications_enabled:
        raise SystemExit("DISCORD_NOTIFICATIONS_ENABLED is false")

    result = notifier.send(
        "🧪 [Universal Trading Bot] Discord 연결 테스트\n"
        f"시간(UTC): {datetime.now(timezone.utc).isoformat()}\n"
        "실거래 주문은 발생하지 않았습니다."
    )
    print("DISCORD_TEST")
    print("configured=true")
    print("webhook_value_printed=false")
    print("ok=", bool(result.get("ok")))
    print("http_status=", result.get("status"))
    if not result.get("ok"):
        raise SystemExit(f"Discord test failed: {result.get('reason')}")


if __name__ == "__main__":
    main()
