"""Immutable price-structure models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from numbers import Real


class PriceLevelKind(StrEnum):
    """Directional pivot kind for a detected price level candidate."""

    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"


@dataclass(frozen=True, slots=True)
class PriceStructureConfig:
    """Configuration for deterministic swing pivot detection."""

    pivot_window: int = 3

    def __post_init__(self) -> None:
        _require_positive_int(self.pivot_window, "pivot_window")


@dataclass(frozen=True, slots=True)
class PriceLevelCandidate:
    """Detected swing high or swing low candidate."""

    price: float
    kind: PriceLevelKind
    observed_at: datetime
    source_method: str = "swing_pivot"

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _normalize_price(self.price))
        if not isinstance(self.kind, PriceLevelKind):
            raise TypeError("kind must be a PriceLevelKind")
        object.__setattr__(self, "observed_at", _normalize_timestamp(self.observed_at))
        object.__setattr__(
            self,
            "source_method",
            _normalize_required_text(self.source_method, "source_method"),
        )


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_price(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("price must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError("price must be finite")
    if numeric_value < 0.0:
        raise ValueError("price must not be negative")
    return numeric_value


def _normalize_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("observed_at must be a datetime")
    if value.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return value.astimezone(UTC)


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
    return value
