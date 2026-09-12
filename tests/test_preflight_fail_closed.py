from types import SimpleNamespace

import pytest

from universal_bot import preflight


def settings(profile="standard"):
    return SimpleNamespace(
        bot_mode="LIVE", exchange="bitget", bitget_execution_profile=profile,
        symbol="BTC/USDT:USDT", live_require_one_way_mode=True,
        bitget_elite_credentials=("key", "secret", "passphrase"),
        margin_mode="crossed", leverage=15,
    )


class Adapter:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.exchange = self
        self.has = dict.fromkeys(
            ["fetchPositions", "setLeverage", "setMarginMode", "setPositionMode"], True
        )

    def check(self, name, value):
        if self.fail_at == name:
            raise RuntimeError("simulated exchange timeout")
        return value

    def market(self, symbol):
        return self.check("market", {"active": True, "contract": True})

    def configure_live(self, *args):
        return self.check("configure", {"ok": True})

    def equity(self):
        return self.check("balance", 1000.0)

    def position(self, symbol):
        return self.check("position", {"side": "LONG", "size": 0.01})

    def protection_status(self, symbol):
        return self.check("protection", {"ok": True})


@pytest.mark.parametrize("profile", ["standard", "elite"])
@pytest.mark.parametrize("failure", ["adapter", "balance", "position", "protection"])
def test_exchange_exception_never_reports_ready(monkeypatch, profile, failure):
    def factory(_):
        if failure == "adapter":
            raise RuntimeError("simulated connection failure")
        return Adapter(failure)
    monkeypatch.setattr(preflight, "_adapter", factory)
    result = preflight.check_live_readiness(settings(profile))
    assert result["ready"] is False
    assert any(c["name"] == "exchange_connection" and not c["ok"] for c in result["checks"])


def test_missing_market_checks_never_report_ready(monkeypatch):
    monkeypatch.setattr(preflight, "_adapter", lambda _: Adapter("market"))
    assert preflight.check_live_readiness(settings())["ready"] is False


@pytest.mark.parametrize("profile", ["standard", "elite"])
def test_complete_live_checks_still_pass(monkeypatch, profile):
    monkeypatch.setattr(preflight, "_adapter", lambda _: Adapter())
    assert preflight.check_live_readiness(settings(profile))["ready"] is True


def test_paper_is_not_live_ready(monkeypatch):
    monkeypatch.setattr(preflight, "_adapter", lambda _: Adapter())
    config = settings()
    config.bot_mode = "PAPER"
    assert preflight.check_live_readiness(config)["ready"] is False
