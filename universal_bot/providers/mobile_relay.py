from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd


class MobileRelayMarketData:
    """Read-only Binance/Bybit futures volume uploaded by the Android app."""

    DEFAULT_PATH = Path.home() / ".cache" / "universal-trading-bot" / "mobile-market-relay.json"
    SUPPORTED_EXCHANGES = {"binance", "bybit"}
    READ_RETRIES = 4
    READ_RETRY_SECONDS = 0.025

    def __init__(self, path: str | Path | None = None, max_age_seconds: int = 90) -> None:
        self.path = Path(path).expanduser() if path else self.DEFAULT_PATH
        self.max_age_seconds = int(max_age_seconds)

    @property
    def configured(self) -> bool:
        return self.path.is_file()

    def _read_snapshot_text(self) -> str:
        """Read a relay snapshot without a check-then-open race.

        The Android relay replaces snapshots atomically over SSH.  A reader must
        therefore open the target directly rather than calling is_file() first.
        A very short retry window covers remote rename/unlink implementations
        while preserving fail-closed behaviour when the snapshot is truly gone.
        """
        last_exc: OSError | None = None
        for attempt in range(self.READ_RETRIES):
            try:
                return self.path.read_text(encoding="utf-8")
            except FileNotFoundError as exc:
                last_exc = exc
                if attempt + 1 < self.READ_RETRIES:
                    time.sleep(self.READ_RETRY_SECONDS)
        raise RuntimeError(f"mobile relay snapshot not found: {self.path}") from last_exc

    def _load(self) -> dict:
        try:
            payload = json.loads(self._read_snapshot_text())
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"invalid mobile relay JSON: {type(exc).__name__}: {exc}") from exc
        if not isinstance(payload, dict) or int(payload.get("schema_version") or 0) != 1:
            raise RuntimeError("unsupported mobile relay schema")
        generated_ms = int(payload.get("generated_at_ms") or 0)
        if generated_ms <= 0:
            raise RuntimeError("mobile relay generated_at_ms is missing")
        completed_ms = int(payload.get("snapshot_completed_at_ms") or generated_ms)
        if completed_ms < generated_ms:
            raise RuntimeError("mobile relay completion time precedes generation time")
        age = max(0.0, time.time() - completed_ms / 1000.0)
        if age > self.max_age_seconds:
            raise RuntimeError(f"mobile relay is stale: age={age:.1f}s max={self.max_age_seconds}s")
        return payload

    def _source_observed_at(self, payload: dict, symbol_key: str, exchange: str) -> pd.Timestamp:
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
        seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}.get(unit)
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
            if timeframe == "5m" and self.path.name == "mobile-market-relay.json":
                sidecar = self.path.with_name("mobile-market-relay-5m.json")
                # Do not pre-check sidecar existence: the sidecar reader owns the
                # retry/fail-closed policy and avoids the same TOCTOU race.
                return MobileRelayMarketData(sidecar, self.max_age_seconds).fetch_volume(
                    exchange_id, symbol, timeframe, limit
                )
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
        latest: list[pd.Timestamp] = []
        for exchange in ("binance", "bybit"):
            series = self.fetch_volume(exchange, symbol, timeframe, limit=2)
            latest.append(series.index[-1])
        return min(latest)
