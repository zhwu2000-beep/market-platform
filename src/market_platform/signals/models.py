"""Structured market signal models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MarketSignal:
    """Immutable structured signal value for a single symbol."""

    symbol: str
    name: str
    value: float | None
    timestamp: datetime
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Signal timestamp must be timezone-aware")
        object.__setattr__(self, "parameters", dict(self.parameters))


@dataclass(frozen=True, slots=True)
class MarketSignalSnapshot:
    """Immutable snapshot of structured signals for a single symbol."""

    symbol: str
    timestamp: datetime
    signals: tuple[MarketSignal, ...]

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Snapshot timestamp must be timezone-aware")
        object.__setattr__(self, "signals", tuple(self.signals))
