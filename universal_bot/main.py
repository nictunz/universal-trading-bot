from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import threading
import time

import pandas as pd
import uvicorn

from universal_bot.adapters import BitgetEliteAdapter, BitgetUtaAdapter, HybridCCXTAdapter, YFinanceMarketAdapter
from universal_bot.cache_refresh_dashboard import install_cache_refresh_dashboard
from universal_bot.config import Settings
from universal_bot.dashboard import create_dashboard
from universal_bot.dashboard_auth import install_dashboard_auth
from universal_bot.dashboard_nav import install_dashboard_navigation
from universal_bot.live_settings_dashboard import install_live_settings_dashboard
from universal_bot.providers.mobile_relay import MobileRelayMarketData
from universal_bot.runtime_engine import TradingEngine
from universal_bot.scanner import SymbolRuntime, UniversalScanner
from universal_bot.strategy import UniversalV15Strategy
from universal_bot.strategy_dashboard import (
    _apply as _apply_strategy_settings,
    _load as _load_strategy_settings,
    install_strategy_dashboard,
)


def _build_bitget_live_adapter(settings: Settings, key: str, secret: str, passphrase: str, **kwargs):
    family = settings.bitget_api_family.strip().lower()
    if family in {"uta", "uta-v3", "v3"}:
        return BitgetUtaAdapter(key, secret, passphrase, **kwargs)
    if family in {"classic", "classic-v2", "v2"}:
        return BitgetEliteAdapter(key, secret, passphrase, **kwargs)
    if family in {"classic-first", "auto-classic"}:
        classic = BitgetEliteAdapter(key, secret, passphrase, **kwargs)
        try:
            classic.account_info(settings.symbol)
            print("BITGET_API_FAMILY_CLASSIC_FIRST selected=classic-v2", flush=True)
            return classic
        except Exception as classic_exc:
            print(
                f"BITGET_API_FAMILY_CLASSIC_FIRST classic_probe_failed={type(classic_exc).__name__}: {classic_exc}",
                flush=True,
            )
        uta = BitgetUtaAdapter(key, secret, passphrase, **kwargs)
        try:
            info = uta.account_info(settings.symbol)
            mode = str(info.get("accountMode") or "").lower()
            if mode in {"unified", "hybrid"}:
                print(f"BITGET_API_FAMILY_CLASSIC_FIRST selected=uta-v3 accountMode={mode}", flush=True)
                return uta
            raise RuntimeError(f"UTA account mode is not unified/hybrid: {mode or 'unknown'}")
        except Exception as uta_exc:
            raise RuntimeError(
                f"Bitget Classic v2 and UTA v3 probes both failed; UTA: {type(uta_exc).__name__}: {uta_exc}"
            ) from uta_exc
    if family != "auto":
        raise ValueError(
            f"invalid BITGET_API_FAMILY={settings.bitget_api_family!r}; "
            "use classic-first, auto, classic-v2 or uta-v3"
        )

    # Auto mode is intentionally UTA-first. A successfully upgraded account
    # answers /api/v3/account/settings with accountMode unified/hybrid. Classic
    # accounts fall back to the proven v2 adapter without changing credentials.
    uta = BitgetUtaAdapter(key, secret, passphrase, **kwargs)
    try:
        info = uta.account_info(settings.symbol)
        mode = str(info.get("accountMode") or "").lower()
        if mode in {"unified", "hybrid"}:
            print(f"BITGET_API_FAMILY_AUTO selected=uta-v3 accountMode={mode}", flush=True)
            return uta
    except Exception as exc:
        print(
            f"BITGET_API_FAMILY_AUTO uta_probe_failed={type(exc).__name__}: {exc}",
            flush=True,
        )

    print("BITGET_API_FAMILY_AUTO selected=classic-v2", flush=True)
    return BitgetEliteAdapter(key, secret, passphrase, **kwargs)


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
        return _build_bitget_live_adapter(
            settings,
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


def _relay_snapshot_revision(path: str | Path = MobileRelayMarketData.DEFAULT_PATH) -> tuple[int, int, int] | None:
    """Return a cheap atomic-upload revision without opening the JSON file."""
    try:
        stat = Path(path).expanduser().stat()
    except OSError:
        return None
    # Atomic SFTP replacement normally changes the inode.  Include all three so
    # even a coarse-mtime filesystem and equal-sized JSON cannot hide a change.
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def _wait_for_relay_change(
    previous_revision: tuple[int, int, int] | None,
    timeout_seconds: float,
    *,
    path: str | Path = MobileRelayMarketData.DEFAULT_PATH,
    check_interval_seconds: float = 0.05,
) -> bool:
    """Wake a scan promptly after the phone atomically replaces its snapshot.

    The normal POLL_SECONDS timeout remains the fallback if the relay is absent,
    unchanged, or the local file notification is missed.  stat polling is local
    and never adds exchange API traffic by itself.
    """
    timeout = max(0.0, float(timeout_seconds))
    deadline = time.monotonic() + timeout
    while True:
        if _relay_snapshot_revision(path) != previous_revision:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(max(0.01, float(check_interval_seconds)), remaining))


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
            api_family = getattr(adapter, "API_FAMILY", "classic-v2" if isinstance(adapter, BitgetEliteAdapter) else "standard")
            print(
                f"RUNTIME_READY symbol={symbol} mode={local.bot_mode.upper()} execution_profile={profile} api_family={api_family}",
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
        # Capture before fetching.  If an atomic phone upload lands anywhere
        # during this scan, the next pass runs immediately and cannot miss it.
        relay_revision = _relay_snapshot_revision()
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
        _wait_for_relay_change(
            relay_revision,
            max(1, settings.poll_seconds),
        )


def main():
    settings = Settings()

    scanner = UniversalScanner([])
    app = create_dashboard(scanner)
    install_dashboard_auth(app)
    install_strategy_dashboard(app, scanner)
    install_live_settings_dashboard(app, scanner)
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
