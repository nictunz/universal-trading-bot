from universal_bot.config import Settings
from universal_bot.dashboard import create_dashboard
from universal_bot.engine import TradingEngine
from universal_bot.scanner import SymbolRuntime, UniversalScanner
from universal_bot.strategy.v15 import UniversalV15Strategy


class DummyAdapter:
    asset_class = "crypto"

    def equity(self):
        return 1_000_000.0

    def market_order(self, *args, **kwargs):
        return {"id": "dummy"}

    def fetch_volume_sources(self, *args, **kwargs):
        return {}


def _app():
    settings = Settings(bot_mode="PAPER", symbol="ETH/USDT:USDT", symbols="ETH/USDT:USDT")
    engine = TradingEngine(settings, DummyAdapter(), UniversalV15Strategy(settings))
    scanner = UniversalScanner([SymbolRuntime(settings.symbol, engine)])
    return create_dashboard(scanner)


def _endpoint(app, path: str, method: str = "GET"):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"missing route {method} {path}")


def test_dashboard_health_endpoint_smoke():
    app = _app()
    payload = _endpoint(app, "/health")()
    assert payload["status"] == "ok"
    assert payload["symbols"] == 1


def test_dashboard_html_contains_safety_and_cost_panels():
    app = _app()
    html = _endpoint(app, "/")()
    assert "LIVE READINESS" in html
    assert "수수료/슬리피지" in html
    assert "실시간 전략 상태" in html
    assert "/api/backtest" in html
    assert "/api/live-readiness" in html
