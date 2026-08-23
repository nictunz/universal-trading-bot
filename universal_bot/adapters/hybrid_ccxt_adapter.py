from __future__ import annotations

import pandas as pd

from universal_bot.adapters.ccxt_adapter import CCXTAdapter
from universal_bot.providers.coinmetrics import CoinMetricsCommunityMarketData


class HybridCCXTAdapter(CCXTAdapter):
    """CCXT execution/direct-data adapter with read-only public data fallbacks.

    Order execution remains entirely on the configured CCXT exchange (Bitget in
    LIVE mode). Fallback providers are used only for public market-volume data.
    """

    def __init__(self, *args, community_fallback: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._community_enabled = bool(community_fallback)
        self._community = CoinMetricsCommunityMarketData()
        self._community_volume_cache: dict[tuple[str, str, str], pd.Series] = {}

    def _community_volume(self, exchange_id: str, symbol: str, timeframe: str, limit: int) -> pd.Series:
        key = (exchange_id, symbol, timeframe)
        cached = self._community_volume_cache.get(key)
        request_limit = limit if cached is None or len(cached) < min(limit, 100) else 3
        frame = self._community.fetch_latest(exchange_id, symbol, timeframe, request_limit)
        if frame.empty:
            raise RuntimeError("empty Coin Metrics Community OHLCV response")
        latest = frame.volume.astype(float)
        if cached is not None and not cached.empty:
            latest = pd.concat([cached, latest]).sort_index()
            latest = latest.loc[~latest.index.duplicated(keep="last")]
        latest = latest.tail(limit)
        self._community_volume_cache[key] = latest
        return latest

    def fetch_volume_sources(self, symbol: str, timeframe: str, limit: int = 1000) -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        status: dict[str, dict[str, str]] = {}
        for exchange_id in ("binance", "bitget", "okx", "bybit"):
            direct_error: Exception | None = None
            try:
                ex = self._public_exchange(exchange_id)
                df = self._fetch(ex, symbol, timeframe, limit)
                if not df.empty:
                    out[exchange_id] = df.volume.astype(float)
                    status[exchange_id] = {"mode": "DIRECT", "status": "OK"}
                    continue
                direct_error = RuntimeError("empty direct OHLCV response")
            except Exception as exc:
                direct_error = exc

            if exchange_id in self._fallback_exchanges and self._community_enabled:
                try:
                    out[exchange_id] = self._community_volume(exchange_id, symbol, timeframe, limit)
                    status[exchange_id] = {"mode": "COMMUNITY", "status": "OK"}
                    continue
                except Exception as community_exc:
                    # CoinAPI remains an optional second fallback when configured.
                    if self._coinapi.enabled:
                        try:
                            out[exchange_id] = self._provider_volume(exchange_id, symbol, timeframe, limit)
                            status[exchange_id] = {"mode": "COINAPI", "status": "OK"}
                            continue
                        except Exception as coinapi_exc:
                            status[exchange_id] = {
                                "mode": "FALLBACK",
                                "status": "FAIL",
                                "error": f"community={community_exc}; coinapi={coinapi_exc}"[:180],
                            }
                            continue
                    status[exchange_id] = {
                        "mode": "COMMUNITY",
                        "status": "FAIL",
                        "error": str(community_exc)[:180],
                    }
                    continue

            status[exchange_id] = {
                "mode": "DIRECT",
                "status": "FAIL",
                "error": str(direct_error)[:180] if direct_error else "unknown volume-source error",
            }
        self._volume_status = status
        return out
