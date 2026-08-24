from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from universal_bot.archive_historical import OfficialArchiveHistoricalDataManager
from universal_bot.historical import DataRequest
from universal_bot.fast_backtest import FOUR_EXCHANGES, default_cache_path


def _timeframe_delta(timeframe: str) -> timedelta:
    value = int(timeframe[:-1])
    unit = timeframe[-1]
    seconds = {"m": 60, "h": 3600, "d": 86400}.get(unit)
    if not seconds:
        raise ValueError(f"unsupported cache refresh timeframe: {timeframe}")
    return timedelta(seconds=value * seconds)


def refresh_cached_symbol(
    symbol: str,
    timeframe: str = "5m",
    database_path: str | Path | None = None,
) -> dict:
    """Append only the missing tail of a completed crypto cache.

    Bitget/OKX can refresh through the latest completed candle. Binance/Bybit
    use exchange-owned daily archives on the US host, so their safe refresh
    target is the end of the previous UTC day. No already-cached history is
    re-downloaded.
    """
    path = Path(database_path) if database_path else default_cache_path(symbol, timeframe)
    if not path.exists():
        raise ValueError(f"cache not found: {path}")

    manager = OfficialArchiveHistoricalDataManager(f"sqlite:///{path}", fallback_exchanges=[])
    delta = _timeframe_delta(timeframe)
    now = datetime.now(timezone.utc)
    latest_completed = now - delta
    previous_day_end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)

    total_inserted = 0
    status: dict[str, dict] = {}
    for exchange in FOUR_EXCHANGES:
        probe = DataRequest(symbol, timeframe, None, None, "crypto", exchange)
        _, max_ms = manager._bounds(probe)
        if max_ms is None:
            status[exchange] = {"status": "SKIP", "reason": "cache has no existing rows"}
            continue
        last = datetime.fromtimestamp(max_ms / 1000, timezone.utc)
        start = last + delta
        target = previous_day_end if exchange in {"binance", "bybit"} else latest_completed
        if start > target:
            status[exchange] = {
                "status": "CURRENT",
                "inserted": 0,
                "cached_through": last.isoformat(),
            }
            continue
        request = DataRequest(symbol, timeframe, start, target, "crypto", exchange)
        try:
            inserted, df = manager.sync(request)
            total_inserted += inserted
            new_last = df.index[-1].isoformat() if not df.empty else last.isoformat()
            status[exchange] = {
                "status": "OK",
                "inserted": inserted,
                "cached_through": new_last,
                "mode": manager.last_fetch_status.get(exchange, {}).get("mode", "CACHE"),
            }
        except Exception as exc:
            # Keep the existing valid cache usable even if the newest archive
            # has not been published yet.
            status[exchange] = {
                "status": "DEFERRED",
                "inserted": 0,
                "cached_through": last.isoformat(),
                "error": str(exc)[:240],
            }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "database": str(path),
        "inserted": total_inserted,
        "sources": status,
        "note": "Binance/Bybit archive tails can lag realtime; fast backtests use only the common cached history available across all four venues.",
    }
