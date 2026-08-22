from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionGuard:
    """Safety gate separating BACKTEST/PAPER from LIVE execution."""
    mode: str = "PAPER"
    live_confirmed: bool = False

    def can_execute_live(self) -> bool:
        return self.mode.upper() == "LIVE" and self.live_confirmed

    def require_live(self) -> None:
        if not self.can_execute_live():
            raise RuntimeError("LIVE execution is disabled. Set BOT_MODE=LIVE and explicit LIVE confirmation.")
