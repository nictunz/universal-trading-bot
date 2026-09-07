from __future__ import annotations

from universal_bot.discord_notifier import DiscordNotifier


def test_discord_disabled_does_not_start_network(monkeypatch):
    called = []
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: called.append((args, kwargs)))
    notifier = DiscordNotifier("https://example.invalid/webhook", enabled=False)
    notifier.send_async("entry")
    assert notifier.send("entry")["skipped"] is True
    assert called == []


def test_discord_payload_does_not_allow_unbounded_content(monkeypatch):
    captured = {}

    class Response:
        status_code = 204

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("requests.post", fake_post)
    notifier = DiscordNotifier("https://discord.invalid/webhook", enabled=True, timeout=3)
    result = notifier.send("x" * 2500)
    assert result["ok"] is True
    assert len(captured["json"]["content"]) == 1900
    assert captured["timeout"] == 3
