from __future__ import annotations

import pandas as pd

from universal_bot.adapters.ccxt_adapter import CCXTAdapter
from universal_bot.providers.coinmetrics import CoinMetricsCommunityMarketData
from universal_bot.providers.mobile_relay import MobileRelayMarketData


class HybridCCXTAdapter(CCXTAdapter):
    """CCXT execution/direct-data adapter with read-only public data fallbacks.

    Order execution remains entirely on the configured exchange. For the two
    venues blocked from the GCP region (Binance/Bybit), a fresh Android relay
    snapshot takes priority when present. If that snapshot becomes stale, the
    adapter fails closed instead of silently changing the four-exchange signal.
    """

    def __init__(self, *args, community_fallback: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._community_enabled = bool(community_fallback)
        self._community = CoinMetricsCommunityMarketData()
        self._community_volume_cache: dict[tuple[str, str, str], pd.Series] = {}
        self._mobile_relay = MobileRelayMarketData()

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

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        """Fetch main-venue candles, gated by a configured mobile relay.

        Once the relay snapshot exists, the runtime never advances past the
        newest candle available on both relayed venues. This removes the race
        where Bitget sees a new 5m bar before the phone uploads Binance/Bybit.
        """
        frame = super().fetch_ohlcv(symbol, timeframe, limit)
        if not self._mobile_relay.configured:
            return frame
        latest = self._mobile_relay.latest_common_timestamp(symbol, timeframe)
        return frame[frame.index <= latest].copy()

    def fetch_volume_sources(self, symbol: str, timeframe: str, limit: int = 1000) -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        status: dict[str, dict[str, str]] = {}
        for exchange_id in ("binance", "bitget", "okx", "bybit"):
            # Once a relay file exists, Binance/Bybit are relay-owned. A stale
            # stream is a hard failure and never degrades to fewer exchanges.
            if exchange_id in self._fallback_exchanges and self._mobile_relay.configured:
                try:
                    out[exchange_id] = self._mobile_relay.fetch_volume(
                        exchange_id, symbol, timeframe, limit
                    )
                    status[exchange_id] = {"mode": "MOBILE_RELAY", "status": "OK"}
                except Exception as exc:
                    status[exchange_id] = {
                        "mode": "MOBILE_RELAY",
                        "status": "FAIL",
                        "error": str(exc)[:180],
                    }
                continue

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

            if exchange_id in self._fallback_exchanges and self._coinapi.enabled:
                try:
                    out[exchange_id] = self._provider_volume(exchange_id, symbol, timeframe, limit)
                    status[exchange_id] = {"mode": "COINAPI", "status": "OK"}
                    continue
                except Exception as coinapi_exc:
                    status[exchange_id] = {
                        "mode": "COINAPI",
                        "status": "FAIL",
                        "error": str(coinapi_exc)[:180],
                    }
                    continue

            status[exchange_id] = {
                "mode": "DIRECT",
                "status": "FAIL",
                "error": str(direct_error)[:180] if direct_error else "unknown volume-source error",
            }
        self._volume_status = status
        return out
