from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from universal_bot.backtest import run_backtest
from universal_bot.config import Settings
from universal_bot.historical import DataRequest, HistoricalDataManager


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 10:
        value += "T00:00:00+00:00"
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_symbol_backtest(symbol: str, asset_class: str = "crypto", exchange: str = "bitget", timeframe: str = "5m", start: str | None = None, end: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = Settings()
    values = dict(overrides or {})
    values.update({"symbol": symbol, "symbols": symbol, "asset_class": asset_class, "exchange": exchange, "timeframe": timeframe})
    if start:
        values["start_date"] = _dt(start)
        values["use_start_date"] = True
    settings = settings.model_copy(update=values)
    manager = HistoricalDataManager(settings.database_url)
    request = DataRequest(symbol=symbol, timeframe=timeframe, start=_dt(start) or settings.start_date.replace(tzinfo=timezone.utc), end=_dt(end), asset_class=asset_class, exchange=exchange)
    inserted, df = manager.sync(request)
    result = run_backtest(df, settings)
    return {"strategy": "Volume Strategy FINAL Universal v15", "symbol": symbol, "asset_class": asset_class, "exchange": exchange, "timeframe": timeframe, "start": request.start.isoformat() if request.start else None, "end": request.end.isoformat() if request.end else None, "bars": len(df), "inserted": inserted, "trades": result.trades, "wins": result.wins, "win_rate": result.win_rate, "profit_factor": result.profit_factor, "pnl": result.pnl, "return_percent": result.return_percent, "max_drawdown_percent": result.max_drawdown_percent, "trades_log": result.trades_log, "equity_curve": result.equity_curve}
