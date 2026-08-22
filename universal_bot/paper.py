from __future__ import annotations

import pandas as pd


def normalize_exchange_volume(volumes: dict[str, pd.Series], lookback: int) -> pd.Series:
    """v15-style normalized average of exchange volume/volume-SMA ratios."""
    ratios = []
    for series in volumes.values():
        avg = series.rolling(lookback).mean()
        ratios.append(series / avg.replace(0, pd.NA))
    if not ratios:
        return pd.Series(index=next(iter(volumes.values())).index, dtype=float) if volumes else pd.Series(dtype=float)
    frame = pd.concat(ratios, axis=1)
    return frame.mean(axis=1, skipna=True)
