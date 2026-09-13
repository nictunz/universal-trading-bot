"""Causal chart overlays independent of strategy settings and live execution."""
from __future__ import annotations

import json
from contextlib import closing
from functools import lru_cache

import pandas as pd

from universal_bot.chart_workspace import clean, readonly, stamp
from universal_bot.indicators import dmi_adx, rsi


def calculate(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_index()
    close = frame["close"].astype(float)
    result = pd.DataFrame(index=frame.index)
    for span in (20, 60, 200):
        result[f"ema{span}"] = close.ewm(span=span, adjust=False, min_periods=span).mean()
    mean = close.rolling(20, min_periods=20).mean()
    deviation = close.rolling(20, min_periods=20).std(ddof=0)
    result["bb_mid"], result["bb_upper"], result["bb_lower"] = mean, mean + 2 * deviation, mean - 2 * deviation
    result["rsi14"] = rsi(close, 14)
    result["adx14"] = dmi_adx(frame["high"], frame["low"], close, 14)[2]
    result.loc[result.index[:14], "rsi14"] = float("nan")
    result.loc[result.index[:27], "adx14"] = float("nan")
    return result


@lru_cache(maxsize=1)
def _dataset(database: str, identity: str, exchange: str, symbol: str, timeframe: str):
    with closing(readonly(database)) as db:
        frame = pd.read_sql_query(
            "SELECT timestamp,high,low,close FROM ohlcv WHERE asset_class='crypto' "
            "AND exchange=? AND symbol=? AND timeframe=? ORDER BY timestamp",
            db, params=(exchange, symbol, timeframe), index_col="timestamp")
    if frame.empty:
        return frame
    if frame.index.has_duplicates:
        raise ValueError("중복 캔들이 있어 보조지표를 계산할 수 없습니다.")
    return calculate(frame)


def indicator_page(database: str, exchange: str, symbol: str, timeframe: str, first: int, last: int) -> str:
    identity = json.dumps(stamp(database), sort_keys=True)
    values = _dataset(database, identity, exchange, symbol, timeframe)
    rows = [{"timestamp": int(t), **row.to_dict()} for t, row in values.loc[first:last].iterrows()]
    if json.dumps(stamp(database), sort_keys=True) != identity:
        raise ValueError("지표 계산 중 DB가 변경됐습니다. 다시 불러오세요.")
    return json.dumps(clean(rows), allow_nan=False)
