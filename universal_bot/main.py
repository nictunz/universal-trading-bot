from __future__ import annotations

from datetime import timedelta
import threading
import time
import uvicorn
import pandas as pd

from universal_bot.adapters import HybridCCXTAdapter, YFinanceMarketAdapter
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
    community_allowed = settings.bot_mode.upper() != "LIVE" or bool(settings.allow_community_market_data_live)
    return HybridCCXTAdapter(
        exchange,
        key,
        secret,
        password,
        coinapi_api_key=settings.coinapi_api_key,
        fallback_exchanges=settings.crypto_fallback_exchange_list,
        community_fallback=community_allowed,
    )


def timeframe_delta(tf: str) -> timedelta:
    units = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
    if tf.endswith("M"):
        return timedelta(days=30 * int(tf[:-1]))
    unit = tf[-1]
    return timedelta(seconds=units.get(unit, 300) * int(tf[:-1]))


def completed_candles(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.sort_index().loc[~df.index.duplicated(keep="last")].copy()
    now = pd.Timestamp.now(tz="UTC")
    delta = timeframe_delta(timeframe)
    if out.index[-1] + delta > now:
        out = out.iloc[:-1]
    return out


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
                frame = runtime.engine.adapter.fetch_ohlcv(runtime.symbol, settings.timeframe, limit=limit)
                frame = completed_candles(frame, settings.timeframe)
                if len(frame) < max(settings.volatility_bars, settings.nbar_volatility_bars, settings.adx_length * 2, 50):
                    raise RuntimeError(f"insufficient completed candles: {len(frame)}")
                frames[runtime.symbol] = frame
            except Exception as exc:
                runtime.last_error = f"{type(exc).__name__}: {exc}"
        scanner.step(frames)
        time.sleep(max(1, settings.poll_seconds))


if __name__ == "__main__":
    main()
