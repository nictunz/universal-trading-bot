from __future__ import annotations

import hashlib
import json
import pkgutil
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from universal_bot.indicators import dmi_adx, rolling_range_percent, rsi, sma

ENGINE_NAME = "Universal Vector Engine"
ENGINE_VERSION = "5.0.0"
ENGINE_SCHEMA = "universal-vector-event-v5"
ENGINE_REFERENCE = {
    "project": "freqtrade/freqtrade",
    "role": "backtest lifecycle and validation reference",
    "code_copied": False,
}

_RESULT_SIGNATURE_FIELDS = (
    "trades",
    "wins",
    "win_rate",
    "profit_factor",
    "pnl",
    "gross_pnl",
    "estimated_costs",
    "return_percent",
    "max_drawdown_percent",
    "liquidations",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


@lru_cache(maxsize=1)
def engine_code_sha256() -> str:
    """Hash every file which can change a simulated trade."""
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ("backtest_engine.py", "backtest.py", "indicators.py", "config.py"):
        digest.update(name.encode("utf-8"))
        try:
            bundled = pkgutil.get_data("universal_bot", name)
            if bundled is None:
                bundled = (package / name).read_bytes()
            digest.update(bundled)
        except OSError:
            digest.update(ENGINE_SCHEMA.encode("utf-8"))
    return digest.hexdigest()


def engine_manifest() -> dict[str, Any]:
    return {
        "name": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "schema": ENGINE_SCHEMA,
        "code_sha256": engine_code_sha256(),
        "execution": "vectorized indicators + deterministic event loop",
        "dependencies": ["numpy", "pandas"],
        "reference": dict(ENGINE_REFERENCE),
    }


def build_run_identity(
    *,
    cache_sha256: str,
    symbol: str,
    timeframe: str,
    requested_start: str,
    requested_end: str,
    strategy_overrides: dict[str, Any],
    candidate_schema: str,
) -> str:
    payload = {
        "engine": engine_manifest(),
        "cache_sha256": str(cache_sha256),
        "symbol": str(symbol),
        "timeframe": str(timeframe),
        "requested_start": str(requested_start),
        "requested_end": str(requested_end),
        "strategy_overrides": strategy_overrides,
        "candidate_schema": str(candidate_schema),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def candidate_signature(
    *,
    run_identity: str,
    parameters: dict[str, Any],
    result: dict[str, Any],
) -> str:
    compact_result = {key: result.get(key) for key in _RESULT_SIGNATURE_FIELDS}
    payload = {
        "run_identity": str(run_identity),
        "parameters": parameters,
        "result": compact_result,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def parameter_signature(parameters: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(parameters).encode("utf-8")).hexdigest()


def verify_candidate_signature(row: dict[str, Any], run_identity: str) -> bool:
    expected = str(row.get("candidate_signature") or "")
    if not expected or str(row.get("run_identity") or "") != str(run_identity):
        return False
    actual = candidate_signature(
        run_identity=run_identity,
        parameters=dict(row.get("parameters") or {}),
        result=dict(row.get("result") or {}),
    )
    return expected == actual


@dataclass(frozen=True)
class PreparedMarketData:
    index: pd.DatetimeIndex
    open_series: pd.Series
    high_series: pd.Series
    low_series: pd.Series
    close_series: pd.Series
    volume_series: pd.Series
    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    one_bar_volatility: np.ndarray
    timestamp_ns: np.ndarray
    hours: np.ndarray
    weekdays: np.ndarray


@dataclass(frozen=True)
class EngineArrays:
    market: PreparedMarketData
    volume_ratio: np.ndarray
    range_percent: np.ndarray
    block_range_percent: np.ndarray
    adx: np.ndarray
    rsi: np.ndarray
    regime_trend: np.ndarray
    regime_volatility: np.ndarray


def _prepare_market_data(df: pd.DataFrame) -> PreparedMarketData:
    missing = [name for name in ("open", "high", "low", "close", "volume") if name not in df.columns]
    if missing:
        raise ValueError(f"backtest data missing columns: {', '.join(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("backtest data index must be a DatetimeIndex")

    prepared = df.sort_index().loc[~df.index.duplicated(keep="last")].copy()
    if prepared.empty:
        raise ValueError("backtest data is empty")
    if prepared.index.hasnans:
        raise ValueError("backtest data contains an invalid timestamp")

    numeric: dict[str, pd.Series] = {}
    for name in ("open", "high", "low", "close", "volume"):
        values = pd.to_numeric(prepared[name], errors="coerce").astype(float)
        array = values.to_numpy(dtype=float, copy=False)
        if not bool(np.all(np.isfinite(array))):
            raise ValueError(f"backtest data contains non-finite {name} values")
        numeric[name] = values

    opens = numeric["open"].to_numpy(dtype=float, copy=False)
    highs = numeric["high"].to_numpy(dtype=float, copy=False)
    lows = numeric["low"].to_numpy(dtype=float, copy=False)
    closes = numeric["close"].to_numpy(dtype=float, copy=False)
    volumes = numeric["volume"].to_numpy(dtype=float, copy=False)
    if bool(np.any(opens <= 0) or np.any(highs <= 0) or np.any(lows <= 0) or np.any(closes <= 0)):
        raise ValueError("backtest OHLC prices must be positive")
    if bool(np.any(volumes < 0)):
        raise ValueError("backtest volume must not be negative")
    invalid_ohlc = (highs < np.maximum(opens, closes)) | (lows > np.minimum(opens, closes)) | (highs < lows)
    if bool(np.any(invalid_ohlc)):
        first = int(np.flatnonzero(invalid_ohlc)[0])
        raise ValueError(f"backtest data contains an invalid OHLC candle at {prepared.index[first]}")

    one_bar = np.divide(
        np.abs(closes - opens) * 100.0,
        opens,
        out=np.zeros_like(closes, dtype=float),
        where=opens != 0,
    )
    return PreparedMarketData(
        index=prepared.index,
        open_series=numeric["open"],
        high_series=numeric["high"],
        low_series=numeric["low"],
        close_series=numeric["close"],
        volume_series=numeric["volume"],
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        one_bar_volatility=one_bar,
        # Pandas 3 preserves millisecond input resolution; compare dates in ns.
        timestamp_ns=prepared.index.as_unit("ns").asi8,
        hours=np.asarray(prepared.index.hour, dtype=np.int8),
        weekdays=np.asarray(prepared.index.weekday, dtype=np.int8),
    )


class _PreparedFeatureBank:
    """One bounded, thread-safe feature bank for the active cached dataset."""

    def __init__(self, max_features: int = 48):
        self.max_features = max(8, int(max_features))
        self._lock = threading.RLock()
        self._dataset_key: str | None = None
        self._market: PreparedMarketData | None = None
        self._features: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def market(self, df: pd.DataFrame, cache_token: Any | None) -> PreparedMarketData:
        if cache_token is None:
            return _prepare_market_data(df)
        key = hashlib.sha256(_canonical_json(cache_token).encode("utf-8")).hexdigest()
        with self._lock:
            if key != self._dataset_key or self._market is None:
                self._dataset_key = key
                self._market = _prepare_market_data(df)
                self._features.clear()
                self._hits = 0
                self._misses = 0
            return self._market

    def feature(self, key: tuple[Any, ...], factory: Callable[[], Any], cache_enabled: bool) -> Any:
        if not cache_enabled:
            return factory()
        with self._lock:
            if key in self._features:
                self._hits += 1
                value = self._features.pop(key)
                self._features[key] = value
                return value
        value = factory()
        with self._lock:
            self._misses += 1
            self._features[key] = value
            while len(self._features) > self.max_features:
                self._features.popitem(last=False)
        return value

    def info(self) -> dict[str, int]:
        with self._lock:
            return {
                "datasets": int(self._market is not None),
                "features": len(self._features),
                "hits": self._hits,
                "misses": self._misses,
                "max_features": self.max_features,
            }


_FEATURE_BANK = _PreparedFeatureBank()


def _as_volume_ratio(
    value: pd.Series | np.ndarray | None,
    market: PreparedMarketData,
    lookback: int,
) -> np.ndarray:
    if value is None:
        average = sma(market.volume_series, int(lookback))
        return (market.volume_series / average.replace(0, np.nan)).to_numpy(dtype=float, copy=False)
    if isinstance(value, pd.Series):
        return value.reindex(market.index).to_numpy(dtype=float, copy=False)
    result = np.asarray(value, dtype=float)
    if result.ndim != 1 or len(result) != len(market.index):
        raise ValueError("normalized volume ratio must match the backtest data length")
    return result


def prepare_engine_arrays(
    df: pd.DataFrame,
    settings: Any,
    normalized_volume_ratio: pd.Series | np.ndarray | None = None,
    *,
    cache_token: Any | None = None,
) -> EngineArrays:
    market = _FEATURE_BANK.market(df, cache_token)
    cached = cache_token is not None
    dataset_prefix = (
        hashlib.sha256(_canonical_json(cache_token).encode("utf-8")).hexdigest()
        if cached
        else ""
    )

    def feature(key: tuple[Any, ...], factory: Callable[[], Any]) -> Any:
        # Prefixing protects the global bounded bank if two callers briefly
        # overlap while switching datasets.
        return _FEATURE_BANK.feature((dataset_prefix, *key), factory, cached)

    volatility_bars = int(settings.volatility_bars)
    block_bars = int(settings.nbar_volatility_bars)
    adx_length = int(settings.adx_length)
    rsi_length = int(settings.rsi_length)
    regime_lookback = max(20, int(getattr(settings, "regime_lookback_bars", 288)))

    range_values = feature(
        ("range", volatility_bars),
        lambda: rolling_range_percent(
            market.high_series, market.low_series, volatility_bars
        ).to_numpy(dtype=float, copy=False),
    )
    block_values = feature(
        ("block-range", block_bars),
        lambda: rolling_range_percent(
            market.high_series, market.low_series, block_bars
        ).to_numpy(dtype=float, copy=False),
    )
    adx_values = feature(
        ("adx", adx_length),
        lambda: dmi_adx(
            market.high_series,
            market.low_series,
            market.close_series,
            adx_length,
        )[2].to_numpy(dtype=float, copy=False),
    )
    rsi_values = feature(
        ("rsi", rsi_length),
        lambda: rsi(market.close_series, rsi_length).to_numpy(dtype=float, copy=False),
    )

    def regime_values() -> tuple[np.ndarray, np.ndarray]:
        trend = (
            (market.close_series / market.close_series.shift(regime_lookback) - 1.0)
            * 100.0
        ).to_numpy(dtype=float, copy=False)
        candle_range = (
            (
                (market.high_series - market.low_series)
                / market.close_series.replace(0, np.nan)
                * 100.0
            )
            .rolling(regime_lookback)
            .mean()
            .to_numpy(dtype=float, copy=False)
        )
        return trend, candle_range

    regime_trend, regime_volatility = feature(
        ("regime", regime_lookback), regime_values
    )
    volume_ratio = _as_volume_ratio(
        normalized_volume_ratio, market, int(settings.volume_lookback)
    )
    return EngineArrays(
        market=market,
        volume_ratio=volume_ratio,
        range_percent=range_values,
        block_range_percent=block_values,
        adx=adx_values,
        rsi=rsi_values,
        regime_trend=regime_trend,
        regime_volatility=regime_volatility,
    )


class FourExchangeVolumeCache:
    """Bounded cache of four-exchange volume ratios aligned to the trade feed."""

    def __init__(
        self,
        volumes: dict[str, pd.Series],
        target_index: pd.DatetimeIndex,
        max_lookbacks: int = 32,
    ):
        if len(volumes) < 4:
            raise ValueError("four exchange volume cache requires four sources")
        frame = pd.concat(
            {
                name: pd.to_numeric(series, errors="coerce").astype(float)
                for name, series in sorted(volumes.items())
            },
            axis=1,
        ).sort_index()
        self._frame = frame.reindex(target_index)
        self._max_lookbacks = max(4, int(max_lookbacks))
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()
        self._lock = threading.RLock()

    def ratio(self, lookback: int) -> np.ndarray:
        window = max(1, int(lookback))
        with self._lock:
            if window in self._cache:
                value = self._cache.pop(window)
                self._cache[window] = value
                return value
        average = self._frame.rolling(window, min_periods=window).mean()
        ratios = self._frame / average.replace(0.0, np.nan)
        complete = ratios.notna().sum(axis=1) >= 4
        result = ratios.mean(axis=1, skipna=True).where(complete).to_numpy(dtype=float, copy=False)
        with self._lock:
            self._cache[window] = result
            while len(self._cache) > self._max_lookbacks:
                self._cache.popitem(last=False)
        return result

    def info(self) -> dict[str, int]:
        with self._lock:
            return {
                "lookbacks": len(self._cache),
                "max_lookbacks": self._max_lookbacks,
                "bars": len(self._frame),
                "sources": len(self._frame.columns),
            }


def feature_cache_info() -> dict[str, int]:
    return _FEATURE_BANK.info()
