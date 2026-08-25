from __future__ import annotations

import threading
from typing import Any

import requests


class DiscordNotifier:
    """Best-effort Discord webhook notifier.

    Notification failures are never allowed to interrupt trading. The webhook
    URL stays in .env and is never logged or returned by this class.
    """

    def __init__(self, webhook_url: str, *, enabled: bool = False, timeout: float = 5.0) -> None:
        self.webhook_url = str(webhook_url or "").strip()
        self.enabled = bool(enabled and self.webhook_url)
        self.timeout = float(timeout)

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, content: str) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "skipped": True, "reason": "disabled-or-unconfigured"}
        text = str(content or "").strip()
        if not text:
            return {"ok": False, "skipped": True, "reason": "empty-message"}
        try:
            response = requests.post(
                self.webhook_url,
                json={"content": text[:1900]},
                timeout=self.timeout,
            )
            ok = 200 <= response.status_code < 300
            return {
                "ok": ok,
                "status": response.status_code,
                "reason": None if ok else "discord-http-error",
            }
        except Exception as exc:
            return {
                "ok": False,
                "status": None,
                "reason": f"{type(exc).__name__}: {exc}",
            }

    def send_async(self, content: str) -> None:
        if not self.enabled or not str(content or "").strip():
            return
        threading.Thread(
            target=self.send,
            args=(content,),
            daemon=True,
            name="discord-webhook",
        ).start()
