from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from universal_bot.engine import TradingEngine


@dataclass
class SymbolRuntime:
    symbol: str
    engine: TradingEngine
    last_error: str = ""


class UniversalScanner:
    """Runs the same v15 engine independently for every selected symbol."""

    def __init__(self, runtimes: Iterable[SymbolRuntime]):
        self.runtimes = list(runtimes)

    def step(self, frames: dict[str, object]) -> dict[str, object]:
        states: dict[str, object] = {}
        for runtime in self.runtimes:
            frame = frames.get(runtime.symbol)
            if frame is None:
                continue
            try:
                states[runtime.symbol] = runtime.engine.step(frame)
                runtime.last_error = ""
            except Exception as exc:  # keep other symbols alive
                runtime.last_error = str(exc)
        return states

    def snapshot(self) -> list[dict[str, object]]:
        result = []
        for runtime in self.runtimes:
            state = runtime.engine.last_state
            result.append({
                "symbol": runtime.symbol,
                "position": getattr(getattr(state, "position", None), "side", "FLAT") if state else "FLAT",
                "closed_trades": getattr(state, "stats", {}).get("closed_trades", 0) if state else 0,
                "win_rate": getattr(state, "stats", {}).get("win_rate", 0) if state else 0,
                "profit_factor": getattr(state, "stats", {}).get("profit_factor", None) if state else None,
                "realized_pnl": getattr(state, "stats", {}).get("realized_pnl", 0) if state else 0,
                "error": runtime.last_error,
            })
        return result
