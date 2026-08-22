from __future__ import annotations

import time
import uvicorn

from universal_bot.adapters import CCXTAdapter, YFinanceMarketAdapter
from universal_bot.config import Settings
from universal_bot.dashboard import create_dashboard
from universal_bot.engine import TradingEngine
from universal_bot.strategy import UniversalV15Strategy


def build_adapter(settings: Settings):
    symbol = settings.symbol
    if "/" in symbol:
        # Runtime exchange is selected by EXCHANGE in the future; Bitget is the
        # initial default because the previous bot used Bitget swaps.
        return CCXTAdapter("bitget", settings.bitget_api_key, settings.bitget_api_secret, settings.bitget_api_passphrase)
    return YFinanceMarketAdapter()


def main():
    settings = Settings()
    adapter = build_adapter(settings)
    strategy = UniversalV15Strategy(settings)
    engine = TradingEngine(settings, adapter, strategy)

    app = create_dashboard(engine)

    # Start dashboard in a daemon thread so the trading loop and API share state.
    import threading
    threading.Thread(target=lambda: uvicorn.run(app, host=settings.dashboard_host, port=settings.dashboard_port, log_level="warning"), daemon=True).start()

    while True:
        try:
            df = adapter.fetch_ohlcv(settings.symbol, settings.timeframe, limit=max(1000, settings.volatility_bars + 20))
            if not df.empty:
                engine.step(df)
        except Exception as exc:
            print(f"[ERROR] {type(exc).__name__}: {exc}")
        time.sleep(10)


if __name__ == "__main__":
    main()
