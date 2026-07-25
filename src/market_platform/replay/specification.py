"""Immutable historical replay request specification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class HistoricalReplaySpecification:
    """Historical replay instrument, context, and evaluation intent."""

    symbol: str
    interval: str
    context_start: datetime
    evaluation_start: datetime
    evaluation_end: datetime

    def __post_init__(self) -> None:
        symbol = _normalize_required_text(self.symbol, "symbol").upper()
        interval = _normalize_required_text(self.interval, "interval")
        context_start = _normalize_timestamp(self.context_start, "context_start")
        evaluation_start = _normalize_timestamp(
            self.evaluation_start,
            "evaluation_start",
        )
        evaluation_end = _normalize_timestamp(self.evaluation_end, "evaluation_end")
        if context_start > evaluation_start:
            raise ValueError(
                "context_start must be earlier than or equal to evaluation_start"
            )
        if evaluation_start > evaluation_end:
            raise ValueError(
                "evaluation_start must be earlier than or equal to evaluation_end"
            )
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "interval", interval)
        object.__setattr__(self, "context_start", context_start)
        object.__setattr__(self, "evaluation_start", evaluation_start)
        object.__setattr__(self, "evaluation_end", evaluation_end)

    def to_dict(self) -> dict[str, str]:
        """Return a deterministic JSON-compatible representation."""

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "context_start": self.context_start.isoformat(),
            "evaluation_start": self.evaluation_start.isoformat(),
            "evaluation_end": self.evaluation_end.isoformat(),
        }


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = ["HistoricalReplaySpecification"]
