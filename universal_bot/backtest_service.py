from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from universal_bot.backtest import run_backtest
from universal_bot.config import Settings
from universal_bot.historical import DataRequest, HistoricalDataManager
from universal_bot.archive_historical import OfficialArchiveHistoricalDataManager
from universal_bot.paper import normalize_exchange_volume


FOUR_CRYPTO_EXCHANGES = ("binance", "bitget", "okx", "bybit")


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


def _validate_crypto_data(df: pd.DataFrame, timeframe: str, *, label: str = "OHLCV") -> None:
    if len(df) < 2:
        return
    minutes = _timeframe_minutes(timeframe)
    if minutes is None:
        return
    diffs = df.index.to_series().diff().dropna().dt.total_seconds() / 60
    gaps = diffs[diffs > minutes * 1.5]
    if not gaps.empty:
        largest = float(gaps.max())
        raise ValueError(f"incomplete {label} data: {len(gaps)} gap(s), largest gap {largest:.1f} minutes")


def _historical_four_exchange_ratio(
    manager: HistoricalDataManager,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime | None,
    lookback: int,
) -> tuple[pd.Series, int, dict[str, int]]:
    volumes: dict[str, pd.Series] = {}
    inserted_total = 0
    source_bars: dict[str, int] = {}
    for exchange_id in FOUR_CRYPTO_EXCHANGES:
        request = DataRequest(symbol=symbol, timeframe=timeframe, start=start, end=end, asset_class="crypto", exchange=exchange_id)
        inserted, source_df = manager.sync(request)
        inserted_total += inserted
        if source_df.empty:
            raise ValueError(f"missing required {exchange_id} futures data for four-exchange volume")
        _validate_crypto_data(source_df, timeframe, label=exchange_id)
        source_bars[exchange_id] = len(source_df)
        volumes[exchange_id] = source_df["volume"].astype(float)

    if set(volumes) != set(FOUR_CRYPTO_EXCHANGES):
        raise ValueError("all four crypto exchanges are required for v15 normalized volume")
    ratio = normalize_exchange_volume(volumes, lookback, required_sources=4)
    return ratio, inserted_total, source_bars


def run_symbol_backtest(symbol: str, asset_class: str = "crypto", exchange: str = "bitget", timeframe: str = "15m", start: str | None = None, end: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if not symbol.strip():
        raise ValueError("symbol is required")
    if timeframe not in {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"}:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    settings = Settings()
    asset = asset_class.lower()
    if asset in {"stocks", "equity"}:
        asset = "stock"
    effective_exchange = settings.stock_data_provider.lower() if asset in {"stock", "etf"} else exchange.lower()
    values = dict(overrides or {})
    values.update({"symbol": symbol, "symbols": symbol, "asset_class": asset, "exchange": effective_exchange, "timeframe": timeframe})
    start_dt = _dt(start)
    end_dt = _dt(end, end_of_day=True)
    if start_dt and end_dt and start_dt > end_dt:
        raise ValueError("start must be before or equal to end")
    if start_dt:
        values["start_date"] = start_dt
        values["use_start_date"] = True
    settings = settings.model_copy(update=values)

    manager = OfficialArchiveHistoricalDataManager(
        settings.database_url,
        coinapi_api_key=settings.coinapi_api_key if settings.crypto_volume_provider.lower() == "coinapi" else "",
        fallback_exchanges=settings.crypto_fallback_exchange_list,
    )
    request = DataRequest(symbol=symbol, timeframe=timeframe, start=start_dt or settings.start_date, end=end_dt, asset_class=asset, exchange=effective_exchange)
    inserted, df = manager.sync(request)
    if df.empty:
        raise ValueError(f"no OHLCV data for {symbol} ({asset}/{effective_exchange}/{timeframe}) in the requested range")
    if len(df) < 10:
        raise ValueError(f"insufficient OHLCV data: only {len(df)} bars returned")

    normalized_volume_ratio = None
    source_bars: dict[str, int] = {}
    if asset == "crypto":
        _validate_crypto_data(df, timeframe, label=effective_exchange)
        if settings.use_four_crypto_exchanges:
            normalized_volume_ratio, source_inserted, source_bars = _historical_four_exchange_ratio(manager, symbol, timeframe, request.start, request.end, settings.volume_lookback)
            inserted += source_inserted
            valid = normalized_volume_ratio.reindex(df.index).notna()
            if int(valid.sum()) < max(settings.volume_lookback, 10):
                raise ValueError("insufficient common four-exchange volume history")

    result = run_backtest(df, settings, normalized_volume_ratio=normalized_volume_ratio)
    return {
        "strategy": "Volume Strategy FINAL Universal v15",
        "symbol": symbol,
        "asset_class": asset,
        "exchange": effective_exchange,
        "timeframe": timeframe,
        "requested_start": request.start.isoformat() if request.start else None,
        "requested_end": request.end.isoformat() if request.end else None,
        "data_start": df.index[0].isoformat(),
        "data_end": df.index[-1].isoformat(),
        "bars": len(df),
        "inserted": inserted,
        "four_exchange_volume": bool(normalized_volume_ratio is not None),
        "volume_source_bars": source_bars,
        "volume_source_status": dict(manager.last_fetch_status),
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
        "trades_log": result.trades_log,
        "equity_curve": result.equity_curve,
    }
