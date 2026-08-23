from __future__ import annotations

from universal_bot.historical import DataRequest, HistoricalDataManager
from universal_bot.providers.official_archives import OfficialArchiveMarketData


class OfficialArchiveHistoricalDataManager(HistoricalDataManager):
    """Historical manager that prefers venue APIs, then exchange-owned archives.

    This keeps the normal Bitget/OKX path unchanged while allowing Binance and
    Bybit backtests to run on a US-hosted server without routing exchange API
    traffic around geographic restrictions. CoinAPI remains an optional final
    fallback only when explicitly configured.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._official_archive = OfficialArchiveMarketData()

    def _fetch_crypto(self, request: DataRequest):
        try:
            df = self._fetch_crypto_direct(request)
            self.last_fetch_status[request.exchange] = {"mode": "DIRECT", "status": "OK"}
            return df
        except Exception as direct_exc:
            exchange = request.exchange.lower()
            archive_exc: Exception | None = None
            if exchange in {"binance", "bybit"} and request.start is not None:
                try:
                    df = self._official_archive.fetch_history(
                        exchange,
                        request.symbol,
                        request.timeframe,
                        request.start,
                        request.end,
                    )
                    if not df.empty:
                        self.last_fetch_status[request.exchange] = {"mode": "OFFICIAL_ARCHIVE", "status": "OK"}
                        return df
                    archive_exc = RuntimeError("official archive returned no rows")
                except Exception as exc:
                    archive_exc = exc

            if exchange in self._fallback_exchanges and self._coinapi.enabled:
                try:
                    if request.start is None:
                        raise ValueError("provider historical requests require a start date")
                    df = self._coinapi.fetch_history(exchange, request.symbol, request.timeframe, request.start, request.end)
                    self.last_fetch_status[request.exchange] = {"mode": "COINAPI", "status": "OK"}
                    return df
                except Exception as provider_exc:
                    self.last_fetch_status[request.exchange] = {
                        "mode": "FALLBACK",
                        "status": "FAIL",
                        "error": f"archive={archive_exc}; coinapi={provider_exc}"[:180],
                    }
                    raise RuntimeError(
                        f"{exchange} direct failed ({direct_exc}); official archive failed ({archive_exc}); "
                        f"CoinAPI failed ({provider_exc})"
                    ) from provider_exc

            mode = "OFFICIAL_ARCHIVE" if exchange in {"binance", "bybit"} else "DIRECT"
            self.last_fetch_status[request.exchange] = {
                "mode": mode,
                "status": "FAIL",
                "error": str(archive_exc or direct_exc)[:180],
            }
            if archive_exc is not None:
                raise RuntimeError(
                    f"{exchange} direct failed ({direct_exc}); official archive failed ({archive_exc})"
                ) from archive_exc
            raise
