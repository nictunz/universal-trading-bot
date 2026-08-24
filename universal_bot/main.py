from __future__ import annotations

from datetime import timedelta
import threading
import time

import pandas as pd
import uvicorn

from universal_bot.adapters import BitgetEliteAdapter, HybridCCXTAdapter, YFinanceMarketAdapter
from universal_bot.cache_refresh_dashboard import install_cache_refresh_dashboard
from universal_bot.config import Settings
from universal_bot.dashboard import create_dashboard
from universal_bot.dashboard_auth import install_dashboard_auth
from universal_bot.dashboard_nav import install_dashboard_navigation
from universal_bot.runtime_engine import TradingEngine
from universal_bot.scanner import SymbolRuntime, UniversalScanner
from universal_bot.strategy import UniversalV15Strategy
from universal_bot.strategy_dashboard import (
    _apply as _apply_strategy_settings,
    _load as _load_strategy_settings,
    install_strategy_dashboard,
)


def build_adapter(settings: Settings):
    if settings.asset_class.lower() in {"stock", "stocks", "etf", "equity"}:
        return YFinanceMarketAdapter()

    exchange = settings.exchange.lower()
    live = settings.bot_mode.upper() == "LIVE"
    profile = settings.bitget_execution_profile.strip().lower()
    provider = settings.crypto_volume_provider.strip().lower()
    community_allowed = provider == "community" and (
        not live or bool(settings.allow_community_market_data_live)
    )
    coinapi_key = settings.coinapi_api_key if provider == "coinapi" else ""

    if exchange == "bitget" and live and profile == "elite":
        key, secret, passphrase = settings.bitget_elite_credentials
        return BitgetEliteAdapter(
            key,
            secret,
            passphrase,
            timeout=settings.bitget_elite_request_timeout,
            coinapi_api_key=coinapi_key,
            fallback_exchanges=settings.crypto_fallback_exchange_list,
            community_fallback=community_allowed,
        )

    bitget_key, bitget_secret, bitget_passphrase = settings.bitget_standard_credentials
    keys = {
        "binance": (settings.binance_api_key, settings.binance_api_secret, ""),
        "bitget": (bitget_key if live else "", bitget_secret if live else "", bitget_passphrase if live else ""),
        "okx": (settings.okx_api_key, settings.okx_api_secret, settings.okx_api_passphrase),
        "bybit": (settings.bybit_api_key, settings.bybit_api_secret, ""),
    }
    key, secret, password = keys.get(exchange, ("", "", ""))
    return HybridCCXTAdapter(
        exchange,
        key,
        secret,
        password,
        coinapi_api_key=coinapi_key,
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


def _scanner_fetch_limit(settings: Settings) -> int:
    required = max(
        settings.volatility_bars,
        settings.nbar_volatility_bars,
        settings.adx_length * 2,
        settings.rsi_length + 2,
        settings.volume_lookback + 2,
        50,
    )
    return max(100, min(500, required + 32))


def _runtime_worker(scanner: UniversalScanner, settings: Settings) -> None:
    """Initialize exchange runtimes and scan in the background.

    The HTTP server owns the main thread. Any slow exchange request therefore
    cannot prevent Uvicorn from binding port 8000 or answering dashboard health
    requests.
    """
    runtimes = scanner.runtimes

    for symbol in settings.symbol_list:
        try:
            local = settings.model_copy(update={"symbol": symbol})
            adapter = build_adapter(local)
            strategy = UniversalV15Strategy(local)
            runtimes.append(SymbolRuntime(symbol, TradingEngine(local, adapter, strategy)))
            profile = local.bitget_execution_profile if local.exchange.lower() == "bitget" else "standard"
            print(
                f"RUNTIME_READY symbol={symbol} mode={local.bot_mode.upper()} execution_profile={profile}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"RUNTIME_INIT_FAILED symbol={symbol} error={type(exc).__name__}: {exc}",
                flush=True,
            )

    if runtimes:
        try:
            _apply_strategy_settings(scanner, _load_strategy_settings())
        except Exception as exc:
            print(
                f"STRATEGY_SETTINGS_APPLY_FAILED error={type(exc).__name__}: {exc}",
                flush=True,
            )

    limit = _scanner_fetch_limit(settings)
    while True:
        frames = {}
        for runtime in list(runtimes):
            try:
                frame = runtime.engine.adapter.fetch_ohlcv(
                    runtime.symbol,
                    settings.timeframe,
                    limit=limit,
                )
                frame = completed_candles(frame, settings.timeframe)
                needed = runtime.engine.settings
                if len(frame) < max(
                    needed.volatility_bars,
                    needed.nbar_volatility_bars,
                    needed.adx_length * 2,
                    needed.rsi_length + 2,
                    50,
                ):
                    raise RuntimeError(f"insufficient completed candles: {len(frame)}")
                frames[runtime.symbol] = frame
            except Exception as exc:
                runtime.last_error = f"{type(exc).__name__}: {exc}"
        scanner.step(frames)
        time.sleep(max(1, settings.poll_seconds))


def main():
    settings = Settings()

    scanner = UniversalScanner([])
    app = create_dashboard(scanner)
    install_dashboard_auth(app)
    install_strategy_dashboard(app, scanner)
    install_cache_refresh_dashboard(app)
    install_dashboard_navigation(app)

    worker_started = threading.Event()

    @app.on_event("startup")
    def start_runtime_worker() -> None:
        if worker_started.is_set():
            return
        worker_started.set()
        threading.Thread(
            target=_runtime_worker,
            args=(scanner, settings),
            daemon=True,
            name="runtime-scanner",
        ).start()
        print("RUNTIME_WORKER_START", flush=True)

    print(
        f"DASHBOARD_HTTP_BIND host={settings.dashboard_host} port={settings.dashboard_port}",
        flush=True,
    )
    uvicorn.run(
        app,
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
