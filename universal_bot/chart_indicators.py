"""Causal chart overlays independent of strategy settings and live execution."""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
from pathlib import Path
from contextlib import closing
from functools import lru_cache

import pandas as pd

from universal_bot.chart_workspace import clean, readonly, stamp
from universal_bot.indicators import dmi_adx, rsi


def calculate(frame: pd.DataFrame, rsi_length: int = 14, options_json: str = "{}") -> pd.DataFrame:
    rsi_length = int(rsi_length)
    if not 2 <= rsi_length <= 500:
        raise ValueError("RSI 길이는 2~500이어야 합니다.")
    options = json.loads(options_json)
    periods = [int(options.get(key, default)) for key, default in (("ema1",20),("ema2",60),("ema3",200))]
    volume_length = int(options.get("volume_length",41))
    volume_multiplier = float(options.get("volume_multiplier",6.4))
    if any(not 2 <= n <= 500 for n in periods + [volume_length]) or not 0.1 <= volume_multiplier <= 100:
        raise ValueError("지표 기간은 2~500, 거래량 배수는 0.1~100이어야 합니다.")
    frame = frame.sort_index()
    close = frame["close"].astype(float)
    result = pd.DataFrame(index=frame.index)
    for span in (20, 60, 200):
        result[f"ema{span}"] = close.ewm(span=span, adjust=False, min_periods=span).mean()
    for i, span in enumerate(periods):
        result[f"ema_custom{i+1}"] = close.ewm(span=span, adjust=False, min_periods=span).mean()
    volume = frame["volume"].astype(float) if "volume" in frame else pd.Series(float("nan"), index=frame.index)
    result["volume_sma"] = volume.rolling(volume_length, min_periods=volume_length).mean()
    result["volume_break"] = result["volume_sma"] * volume_multiplier
    mean = close.rolling(20, min_periods=20).mean()
    deviation = close.rolling(20, min_periods=20).std(ddof=0)
    result["bb_mid"], result["bb_upper"], result["bb_lower"] = mean, mean + 2 * deviation, mean - 2 * deviation
    result["rsi14"] = rsi(close, 14)
    result["rsi"] = rsi(close, rsi_length)
    result.loc[result.index[:rsi_length], "rsi"] = float("nan")
    result["adx14"] = dmi_adx(frame["high"], frame["low"], close, 14)[2]
    result.loc[result.index[:14], "rsi14"] = float("nan")
    result.loc[result.index[:27], "adx14"] = float("nan")
    return result


@lru_cache(maxsize=1)
def _dataset(database: str, identity: str, exchange: str, symbol: str, timeframe: str, rsi_length: int = 14, options_json: str = "{}"):
    with closing(readonly(database)) as db:
        frame = pd.read_sql_query(
            "SELECT timestamp,high,low,close,volume FROM ohlcv WHERE asset_class='crypto' "
            "AND exchange=? AND symbol=? AND timeframe=? ORDER BY timestamp",
            db, params=(exchange, symbol, timeframe), index_col="timestamp")
    if frame.empty:
        return frame
    if frame.index.has_duplicates:
        raise ValueError("중복 캔들이 있어 보조지표를 계산할 수 없습니다.")
    return calculate(frame, rsi_length, options_json)


def indicator_page(database: str, exchange: str, symbol: str, timeframe: str, first: int, last: int, rsi_length: int = 14, options_json: str = "{}") -> str:
    raw_options = json.loads(options_json)
    # Display-only color/width changes must not invalidate numerical indicator caches.
    options_json = json.dumps({k: raw_options[k] for k in ("ema1","ema2","ema3","volume_length","volume_multiplier") if k in raw_options}, sort_keys=True)
    identity = json.dumps(stamp(database), sort_keys=True)
    # JSON only: never deserialize executable cache formats. Bound disk usage.
    key = json.dumps(["chart-page-v3", str(Path(database).resolve()), identity,
                      exchange, symbol, timeframe, int(first), int(last), int(rsi_length), options_json])
    folder = Path(database).parent / "chart-indicator-cache"
    cached = folder / (hashlib.sha256(key.encode()).hexdigest() + ".json")
    try:
        payload = cached.read_text(encoding="utf-8")
        rows = json.loads(payload)
        if isinstance(rows, list) and json.dumps(stamp(database), sort_keys=True) == identity:
            return payload
    except (OSError, ValueError):
        pass
    values = _dataset(database, identity, exchange, symbol, timeframe, int(rsi_length), options_json)
    # Vectorized serialization avoids a Python Series allocation for each candle.
    page = values.loc[first:last].copy()
    page.insert(0, "timestamp", page.index.astype("int64"))
    payload = page.to_json(orient="records", double_precision=15)
    if json.dumps(stamp(database), sort_keys=True) != identity:
        raise ValueError("지표 계산 중 DB가 변경됐습니다. 다시 불러오세요.")
    temporary = None
    try:
        folder.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as out:
            temporary = out.name
            out.write(payload)
        os.replace(temporary, cached)
        temporary = None
        files = sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        size = 0
        for i, item in enumerate(files):
            size += item.stat().st_size
            if i >= 32 or size > 16 * 1024 * 1024:
                item.unlink(missing_ok=True)
    except OSError:
        pass  # A read-only/full disk must not prevent chart display.
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
    return payload
