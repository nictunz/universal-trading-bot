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
        return {"id": "smoke"}

    def fetch_volume_sources(self, *args, **kwargs):
        return {}


settings = Settings(bot_mode="PAPER", symbol="ETH/USDT:USDT", symbols="ETH/USDT:USDT")
engine = TradingEngine(settings, DummyAdapter(), UniversalV15Strategy(settings))
scanner = UniversalScanner([SymbolRuntime(settings.symbol, engine)])
app = create_dashboard(scanner)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
