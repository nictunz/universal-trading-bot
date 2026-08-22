from __future__ import annotations
import threading
import time
import uvicorn
from universal_bot.adapters import CCXTAdapter, YFinanceMarketAdapter
from universal_bot.config import Settings
from universal_bot.dashboard import create_dashboard
from universal_bot.engine import TradingEngine
from universal_bot.scanner import SymbolRuntime, UniversalScanner
from universal_bot.strategy import UniversalV15Strategy

def build_adapter(settings: Settings):
    if settings.asset_class.lower() in {"stock", "stocks", "etf", "equity"}:
        return YFinanceMarketAdapter()
    keys = {
        "binance": (settings.binance_api_key, settings.binance_api_secret, ""),
        "bitget": (settings.bitget_api_key, settings.bitget_api_secret, settings.bitget_api_passphrase),
        "okx": (settings.okx_api_key, settings.okx_api_secret, settings.okx_api_passphrase),
        "bybit": (settings.bybit_api_key, settings.bybit_api_secret, ""),
    }
    exchange = settings.exchange.lower()
    key, secret, password = keys.get(exchange, ("", "", ""))
    return CCXTAdapter(exchange, key, secret, password)

def main():
    settings = Settings()
    runtimes = []
    for symbol in settings.symbol_list:
        local = settings.model_copy(update={"symbol": symbol})
        adapter = build_adapter(local)
        strategy = UniversalV15Strategy(local)
        runtimes.append(SymbolRuntime(symbol, TradingEngine(local, adapter, strategy)))
    scanner = UniversalScanner(runtimes)
    app = create_dashboard(scanner)
    threading.Thread(target=lambda: uvicorn.run(app, host=settings.dashboard_host, port=settings.dashboard_port, log_level="warning"), daemon=True).start()
    limit = max(1000, settings.volatility_bars + 20, settings.nbar_volatility_bars + 20)
    while True:
        frames = {}
        for runtime in runtimes:
            try:
                frames[runtime.symbol] = runtime.engine.adapter.fetch_ohlcv(runtime.symbol, settings.timeframe, limit=limit)
            except Exception as exc:
                runtime.last_error = f"{type(exc).__name__}: {exc}"
        scanner.step(frames)
        time.sleep(settings.poll_seconds)

if __name__ == "__main__":
    main()
