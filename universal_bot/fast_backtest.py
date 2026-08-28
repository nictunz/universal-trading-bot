from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from universal_bot.backtest import run_backtest
from universal_bot.config import Settings
from universal_bot.historical import DataRequest, HistoricalDataManager
from universal_bot.paper import normalize_exchange_volume

FOUR_EXCHANGES = ("binance", "bitget", "okx", "bybit")

# One immutable prepared dataset is reused across optimization trials. This avoids
# reopening SQLite and allocating five year-long DataFrames thousands of times.
_PREPARED_CACHE_KEY: tuple | None = None
_PREPARED_CACHE_VALUE: tuple | None = None


def _dt(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 10:
        text += "T23:59:59.999999+00:00" if end_of_day else "T00:00:00+00:00"
    text = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _slug(symbol: str) -> str:
    base = symbol.split(":", 1)[0].split("/", 1)[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "asset"


def default_cache_path(symbol: str, timeframe: str = "5m") -> Path:
    return Path.home() / ".cache" / "universal-trading-bot" / f"{_slug(symbol)}-1y-{timeframe}.db"


def cache_available(symbol: str, timeframe: str = "5m") -> bool:
    p = default_cache_path(symbol, timeframe)
    return p.exists() and p.stat().st_size > 0


def _validate(df: pd.DataFrame, timeframe: str, label: str) -> None:
    if len(df) < 2:
        raise ValueError(f"cache incomplete for {label}: only {len(df)} bars")
    unit = timeframe[-1]
    try:
        n = int(timeframe[:-1])
    except Exception as exc:
        raise ValueError(f"unsupported timeframe for cache validation: {timeframe}") from exc
    mins = n * {"m": 1, "h": 60, "d": 1440}.get(unit, 0)
    if mins <= 0:
        return
    diffs = df.index.to_series().diff().dropna().dt.total_seconds() / 60
    gaps = diffs[diffs > mins * 1.5]
    if not gaps.empty:
        raise ValueError(f"cache incomplete for {label}: {len(gaps)} gap(s), largest {float(gaps.max()):.1f} minutes")


def run_cached_symbol_backtest(
    symbol: str,
    asset_class: str = "crypto",
    exchange: str = "bitget",
    timeframe: str = "5m",
    start: str | None = None,
    end: str | None = None,
    overrides: dict[str, Any] | None = None,
    database_path: str | Path | None = None,
    include_details: bool = True,
) -> dict[str, Any]:
    """Run a backtest without any network calls.

    Reads the one-time OHLCV cache produced by run_one_year_backtest.py and only
    recalculates strategy/indicators. This is intended for rapid parameter iteration.
    """
    if asset_class.lower() != "crypto":
        raise ValueError("fast cache backtest currently supports crypto caches only")
    if not symbol.strip():
        raise ValueError("symbol is required")

    path = Path(database_path) if database_path else default_cache_path(symbol, timeframe)
    if not path.exists():
        raise ValueError(f"fast cache not found: {path}")

    start_dt = _dt(start)
    end_dt = _dt(end, end_of_day=True)
    if start_dt and end_dt and start_dt > end_dt:
        raise ValueError("start must be before or equal to end")

    settings = Settings().model_copy(update=dict(overrides or {}))
    values = {
        "symbol": symbol,
        "symbols": symbol,
        "asset_class": "crypto",
        "exchange": exchange.lower(),
        "timeframe": timeframe,
    }
    if start_dt:
        values.update({"start_date": start_dt, "use_start_date": True})
    settings = settings.model_copy(update=values)

    req_start = start_dt or settings.start_date
    stat = path.stat()
    prepared_key = (
        str(path.resolve()), stat.st_size, stat.st_mtime_ns, symbol, timeframe,
        req_start.isoformat() if req_start else None,
        end_dt.isoformat() if end_dt else None,
        exchange.lower(),
    )
    global _PREPARED_CACHE_KEY, _PREPARED_CACHE_VALUE
    if _PREPARED_CACHE_KEY == prepared_key and _PREPARED_CACHE_VALUE is not None:
        df, volumes, source_bars, source_status = _PREPARED_CACHE_VALUE
    else:
        manager = HistoricalDataManager(f"sqlite:///{path}", fallback_exchanges=[])
        base_request = DataRequest(symbol, timeframe, req_start, end_dt, "crypto", exchange.lower())
        df = manager.read(base_request)
        if df.empty:
            raise ValueError(f"no cached {exchange} data for requested range")
        _validate(df, timeframe, exchange.lower())

        volumes = {}
        source_bars = {}
        source_status = {}
        for ex in FOUR_EXCHANGES:
            request = DataRequest(symbol, timeframe, req_start, end_dt, "crypto", ex)
            source = manager.read(request)
            if source.empty:
                raise ValueError(f"fast cache incomplete: missing {ex} data")
            _validate(source, timeframe, ex)
            source_bars[ex] = len(source)
            volumes[ex] = source["volume"].astype(float)
            source_status[ex] = {"mode": "CACHE_ONLY", "status": "OK"}
        _PREPARED_CACHE_KEY = prepared_key
        _PREPARED_CACHE_VALUE = (df, volumes, source_bars, source_status)

    normalized = normalize_exchange_volume(volumes, settings.volume_lookback, required_sources=4)
    common_count = int(normalized.reindex(df.index).notna().sum())
    if common_count < max(settings.volume_lookback, 10):
        raise ValueError("insufficient common four-exchange cached volume history")

    result = run_backtest(df, settings, normalized_volume_ratio=normalized)
    payload = {
        "strategy": "Volume Strategy FINAL Universal v15",
        "symbol": symbol,
        "asset_class": "crypto",
        "exchange": exchange.lower(),
        "timeframe": timeframe,
        "requested_start": req_start.isoformat() if req_start else None,
        "requested_end": end_dt.isoformat() if end_dt else None,
        "data_start": df.index[0].isoformat(),
        "data_end": df.index[-1].isoformat(),
        "bars": len(df),
        "inserted": 0,
        "fast_cache": True,
        "cache_database": str(path),
        "four_exchange_volume": True,
        "volume_source_bars": source_bars,
        "volume_source_status": source_status,
        "trades": result.trades,
        "wins": result.wins,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "pnl": result.pnl,
        "gross_pnl": result.gross_pnl,
        "estimated_costs": result.estimated_costs,
        "fee_percent_per_side": settings.backtest_fee_percent,
        "slippage_percent_per_side": settings.backtest_slippage_percent,
        "return_percent": result.return_percent,
        "max_drawdown_percent": result.max_drawdown_percent,
        "liquidations": result.liquidations,
        "margin_mode": settings.backtest_margin_mode,
        "maintenance_margin_percent": settings.backtest_maintenance_margin_percent,
        "cross_liquidation_buffer_percent": settings.backtest_cross_liquidation_buffer_percent,
        "max_total_multiplier": settings.backtest_max_total_multiplier,
    }
    if include_details:
        payload["trades_log"] = result.trades_log
        payload["equity_curve"] = result.equity_curve
    return payload
