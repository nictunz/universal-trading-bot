from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from universal_bot.backtest import run_backtest
from universal_bot.config import Settings
from universal_bot.historical import DataRequest, HistoricalDataManager


def _dt(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 10:
        value += "T23:59:59.999999+00:00" if end_of_day else "T00:00:00+00:00"
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _timeframe_minutes(timeframe: str) -> int | None:
    if timeframe.endswith("m"):
        return int(timeframe[:-1])
    if timeframe.endswith("h"):
        return int(timeframe[:-1]) * 60
    if timeframe.endswith("d"):
        return int(timeframe[:-1]) * 1440
    return None


def _validate_crypto_data(df: pd.DataFrame, timeframe: str) -> None:
    if len(df) < 2:
        return
    minutes = _timeframe_minutes(timeframe)
    if minutes is None:
        return
    diffs = df.index.to_series().diff().dropna().dt.total_seconds() / 60
    gaps = diffs[diffs > minutes * 1.5]
    if not gaps.empty:
        largest = float(gaps.max())
        raise ValueError(f"incomplete OHLCV data: {len(gaps)} gap(s), largest gap {largest:.1f} minutes")


def run_symbol_backtest(symbol: str, asset_class: str = "crypto", exchange: str = "bitget", timeframe: str = "5m", start: str | None = None, end: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if not symbol.strip():
        raise ValueError("symbol is required")
    if timeframe not in {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"}:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    settings = Settings()
    values = dict(overrides or {})
    values.update({"symbol": symbol, "symbols": symbol, "asset_class": asset_class.lower(), "exchange": exchange.lower(), "timeframe": timeframe})
    start_dt = _dt(start)
    end_dt = _dt(end, end_of_day=True)
    if start_dt and end_dt and start_dt > end_dt:
        raise ValueError("start must be before or equal to end")
    if start_dt:
        values["start_date"] = start_dt
        values["use_start_date"] = True
    settings = settings.model_copy(update=values)

    manager = HistoricalDataManager(settings.database_url)
    request = DataRequest(symbol=symbol, timeframe=timeframe, start=start_dt or settings.start_date, end=end_dt, asset_class=asset_class.lower(), exchange=exchange.lower())
    inserted, df = manager.sync(request)
    if df.empty:
        raise ValueError(f"no OHLCV data for {symbol} ({asset_class}/{exchange}/{timeframe}) in the requested range")
    if len(df) < 10:
        raise ValueError(f"insufficient OHLCV data: only {len(df)} bars returned")
    if asset_class.lower() == "crypto":
        _validate_crypto_data(df, timeframe)

    result = run_backtest(df, settings)
    return {
        "strategy": "Volume Strategy FINAL Universal v15",
        "symbol": symbol,
        "asset_class": asset_class.lower(),
        "exchange": exchange.lower(),
        "timeframe": timeframe,
        "requested_start": request.start.isoformat() if request.start else None,
        "requested_end": request.end.isoformat() if request.end else None,
        "data_start": df.index[0].isoformat(),
        "data_end": df.index[-1].isoformat(),
        "bars": len(df),
        "inserted": inserted,
        "trades": result.trades,
        "wins": result.wins,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "pnl": result.pnl,
        "return_percent": result.return_percent,
        "max_drawdown_percent": result.max_drawdown_percent,
        "trades_log": result.trades_log,
        "equity_curve": result.equity_curve,
    }
