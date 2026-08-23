from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class LiveSafety:
    """Fail-closed runtime safety state for live execution."""
    enabled: bool = False
    halted: bool = False
    reason: str = ""
    consecutive_errors: int = 0
    last_reconciliation: datetime | None = None
    last_data: datetime | None = None
    protection_ok: bool = False
    exchange_position: dict[str, Any] | None = None
    internal_position: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def fail(self, reason: str) -> None:
        self.halted = True
        self.reason = reason

    def clear_error(self) -> None:
        self.consecutive_errors = 0

    def record_error(self, reason: str, max_errors: int = 3) -> None:
        self.consecutive_errors += 1
        if self.consecutive_errors >= max_errors:
            self.fail(reason)

    def record_data(self, timestamp: datetime) -> None:
        self.last_data = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)

    def stale(self, now: datetime, max_seconds: int) -> bool:
        if self.last_data is None:
            return True
        now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        return (now - self.last_data).total_seconds() > max_seconds

    def reconcile(self, internal: dict[str, Any], exchange: dict[str, Any] | None, tolerance: float = 1e-9) -> bool:
        self.internal_position = internal
        self.exchange_position = exchange
        if exchange is None:
            self.fail("EXCHANGE_POSITION_UNAVAILABLE")
            return False
        i_side = internal.get("side") or "FLAT"
        e_side = exchange.get("side") or "FLAT"
        i_size = abs(float(internal.get("size") or 0.0))
        e_size = abs(float(exchange.get("size") or 0.0))
        if i_side != e_side or abs(i_size - e_size) > max(tolerance, e_size * 1e-6):
            self.fail(f"POSITION_MISMATCH internal={i_side}:{i_size} exchange={e_side}:{e_size}")
            return False
        self.last_reconciliation = datetime.now(timezone.utc)
        return True

    @property
    def can_open(self) -> bool:
        return self.enabled and not self.halted and self.protection_ok
