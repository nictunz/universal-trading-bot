from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

Side = Literal["LONG", "SHORT"]

@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Position:
    side: Optional[Side] = None
    size: float = 0.0
    entry_price: Optional[float] = None
    tp: Optional[float] = None
    sl: Optional[float] = None
    entries: int = 0

    @property
    def flat(self) -> bool:
        return self.side is None or self.size == 0

@dataclass
class Signal:
    side: Optional[Side]
    reason: str
    ready: bool
    diagnostics: dict[str, object] = field(default_factory=dict)

@dataclass
class StrategyState:
    symbol: str
    timeframe: str
    timestamp: Optional[datetime] = None
    position: Position = field(default_factory=Position)
    signal: Optional[Signal] = None
    values: dict[str, object] = field(default_factory=dict)
    stats: dict[str, float] = field(default_factory=dict)
