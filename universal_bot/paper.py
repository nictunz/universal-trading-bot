from __future__ import annotations

import pandas as pd


def normalize_exchange_volume(
    volumes: dict[str, pd.Series],
    lookback: int,
    *,
    required_sources: int | None = None,
) -> pd.Series:
    """Return the v15 average of exchange volume / exchange-volume-SMA ratios.

    When ``required_sources`` is supplied, a bar is valid only when that many
    exchange ratios are present.  This prevents a temporary exchange/data
    failure from silently changing the live strategy from a four-exchange
    signal into a one-, two-, or three-exchange signal.
    """
    ratios: list[pd.Series] = []
    for series in volumes.values():
        numeric = pd.to_numeric(series, errors="coerce").astype(float)
        avg = numeric.rolling(lookback, min_periods=lookback).mean()
        ratios.append(numeric / avg.replace(0.0, pd.NA))

    if not ratios:
        return pd.Series(dtype=float)

    frame = pd.concat(ratios, axis=1).sort_index()
    result = frame.mean(axis=1, skipna=True)
    if required_sources is not None:
        result = result.where(frame.notna().sum(axis=1) >= int(required_sources))
    return result
