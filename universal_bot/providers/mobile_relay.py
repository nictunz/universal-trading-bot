from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd


class MobileRelayMarketData:
    """Read-only Binance/Bybit futures volume uploaded by the Android app.

    The Android app fetches public perpetual-futures candles on the user's
    network and atomically uploads one JSON snapshot over the phone's existing
    SSH key. No exchange/API credentials ever leave the server.

    Relay rows can include the exchange's currently-forming candle. This class
    deliberately removes any candle which had not completed at the snapshot's
    generated_at_ms. That prevents the server from treating a partial 5m volume
    value as final during the few seconds around a candle boundary.
    """

    DEFAULT_PATH = Path.home() / ".cache" / "universal-trading-bot" / "mobile-market-relay.json"
    SUPPORTED_EXCHANGES = {"binance", "bybit"}

    def __init__(self, path: str | Path | None = None, max_age_seconds: int = 90) -> None:
        self.path = Path(path).expanduser() if path else self.DEFAULT_PATH
        self.max_age_seconds = int(max_age_seconds)

    @property
    def configured(self) -> bool:
        return self.path.is_file()

    def _load(self) -> dict:
        if not self.path.is_file():
            raise RuntimeError(f"mobile relay snapshot not found: {self.path}")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"invalid mobile relay JSON: {type(exc).__name__}: {exc}") from exc
        if not isinstance(payload, dict) or int(payload.get("schema_version") or 0) != 1:
            raise RuntimeError("unsupported mobile relay schema")
        generated_ms = int(payload.get("generated_at_ms") or 0)
        if generated_ms <= 0:
            raise RuntimeError("mobile relay generated_at_ms is missing")
        # Newer Android relays keep generated_at_ms at the conservative cycle
        # start for compatibility with older servers, and publish the time at
        # which all venue reads completed separately.  Use that completion time
        # only for freshness; candle completion is still decided per source.
        completed_ms = int(payload.get("snapshot_completed_at_ms") or generated_ms)
        if completed_ms < generated_ms:
            raise RuntimeError("mobile relay completion time precedes generation time")
        age = max(0.0, time.time() - completed_ms / 1000.0)
        if age > self.max_age_seconds:
            raise RuntimeError(f"mobile relay is stale: age={age:.1f}s max={self.max_age_seconds}s")
        return payload

    def _source_observed_at(self, payload: dict, symbol_key: str, exchange: str) -> pd.Timestamp:
        """Return the conservative instant at which one venue read began.

        A REST call which starts before a 15-minute boundary and finishes after
        it must not make the previous, still-forming candle look completed.
        Old app payloads have no per-source timestamp and remain compatible by
        falling back to generated_at_ms.
        """
        generated_ms = int(payload["generated_at_ms"])
        completed_ms = int(payload.get("snapshot_completed_at_ms") or generated_ms)
        observations = payload.get("source_observed_at_ms") or {}
        symbol_observations = observations.get(symbol_key) or {}
        raw = symbol_observations.get(exchange)
        try:
            observed_ms = int(raw)
        except (TypeError, ValueError):
            observed_ms = generated_ms
        if observed_ms <= 0:
            observed_ms = generated_ms
        # Never trust a source timestamp later than the completed snapshot.
        observed_ms = min(observed_ms, completed_ms)
        if completed_ms - observed_ms > self.max_age_seconds * 1000:
            raise RuntimeError(
                f"mobile relay source is stale: {exchange} age={(completed_ms - observed_ms) / 1000.0:.1f}s"
            )
        return pd.to_datetime(observed_ms, unit="ms", utc=True)

    @staticmethod
    def _symbol_key(symbol: str) -> str:
        text = symbol.strip().upper().replace("-", "/")
        if ":" in text:
            return text
        if "/" in text:
            base, quote = text.split("/", 1)
            return f"{base}/{quote}:{quote}"
        for quote in ("USDT", "USDC", "USD"):
            if text.endswith(quote) and len(text) > len(quote):
                base = text[: -len(quote)]
                return f"{base}/{quote}:{quote}"
        return text

    @staticmethod
    def _timeframe_delta(timeframe: str) -> pd.Timedelta:
        text = timeframe.strip()
        if len(text) < 2:
            raise ValueError(f"invalid timeframe: {timeframe}")
        value = int(text[:-1])
        unit = text[-1]
        seconds = {
            "m": 60,
            "h": 3600,
            "d": 86400,
            "w": 604800,
        }.get(unit)
        if seconds is None:
            raise ValueError(f"unsupported mobile relay timeframe: {timeframe}")
        return pd.Timedelta(seconds=value * seconds)

    def fetch_volume(self, exchange_id: str, symbol: str, timeframe: str, limit: int = 1000) -> pd.Series:
        exchange = exchange_id.strip().lower()
        if exchange not in self.SUPPORTED_EXCHANGES:
            raise ValueError(f"mobile relay does not provide {exchange_id}")
        payload = self._load()
        relay_tf = str(payload.get("timeframe") or "")
        if relay_tf != timeframe:
            raise RuntimeError(f"mobile relay timeframe mismatch: relay={relay_tf} requested={timeframe}")
        markets = payload.get("markets") or {}
        symbol_key = self._symbol_key(symbol)
        streams = markets.get(symbol_key) or {}
        rows = streams.get(exchange) or []
        if not rows:
            raise RuntimeError(f"mobile relay has no {exchange} data for {symbol_key}")

        timestamps: list[int] = []
        volumes: list[float] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                timestamps.append(int(row[0]))
                volumes.append(float(row[1]))
            except (TypeError, ValueError):
                continue
        if not timestamps:
            raise RuntimeError(f"mobile relay contains no valid rows for {exchange} {symbol_key}")
        index = pd.to_datetime(timestamps, unit="ms", utc=True, errors="coerce")
        series = pd.Series(volumes, index=index, dtype=float).dropna().sort_index()
        series = series.loc[~series.index.duplicated(keep="last")]

        observed = self._source_observed_at(payload, symbol_key, exchange)
        delta = self._timeframe_delta(timeframe)
        series = series[(series.index + delta) <= observed]
        if series.empty:
            raise RuntimeError(f"mobile relay has no completed candles for {exchange} {symbol_key}")
        return series.tail(max(1, int(limit)))

    def latest_common_timestamp(self, symbol: str, timeframe: str) -> pd.Timestamp:
        payload = self._load()
        relay_tf = str(payload.get("timeframe") or "")
        if relay_tf != timeframe:
            raise RuntimeError(f"mobile relay timeframe mismatch: relay={relay_tf} requested={timeframe}")
        latest: list[pd.Timestamp] = []
        for exchange in ("binance", "bybit"):
            series = self.fetch_volume(exchange, symbol, timeframe, limit=2)
            latest.append(series.index[-1])
        return min(latest)
