from __future__ import annotations

from dataclasses import asdict, is_dataclass


def strategy_snapshot(state) -> dict:
    """Dashboard-ready representation of the v15 decision state."""
    values = getattr(state, "values", {}) or {}
    position = getattr(state, "position", None)
    stats = getattr(state, "stats", {}) or {}
    return {
        "strategy": "거래량 전략 FINAL Universal v15",
        "signal": getattr(getattr(state, "signal", None), "side", None),
        "position": getattr(position, "side", "FLAT") if position else "FLAT",
        "entry_price": getattr(position, "entry_price", None) if position else None,
        "tp": getattr(position, "tp", None) if position else None,
        "sl": getattr(position, "sl", None) if position else None,
        "volume_ratio": values.get("volume_ratio"),
        "volume_break_multiplier": values.get("volume_break_multiplier"),
        "one_bar_volatility": values.get("one_bar_volatility"),
        "n_bar_range": values.get("n_bar_range"),
        "final_tp_percent": values.get("final_tp_percent"),
        "final_sl_percent": values.get("final_sl_percent"),
        "n_bar_blocked": values.get("n_bar_blocked"),
        "adx": values.get("adx"),
        "adx_min": values.get("adx_min"),
        "adx_max": values.get("adx_max"),
        "rsi": values.get("rsi"),
        "rsi_long_ok": values.get("rsi_long_ok"),
        "rsi_short_ok": values.get("rsi_short_ok"),
        "base_entry_condition": values.get("base_entry_condition"),
        "stats": stats,
    }
