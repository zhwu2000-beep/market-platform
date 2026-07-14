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
    """Configuration for deterministic swing pivot detection and clustering."""

    pivot_window: int = 3
    atr_period: int = 14
    zone_atr_multiplier: float = 0.25

    def __post_init__(self) -> None:
        _require_positive_int(self.pivot_window, "pivot_window")
        _require_positive_int(self.atr_period, "atr_period")
        _require_positive_number(self.zone_atr_multiplier, "zone_atr_multiplier")
        if self.zone_atr_multiplier <= 0.0:
            raise ValueError("zone_atr_multiplier must be greater than 0")


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


@dataclass(frozen=True, slots=True)
class PriceZone:
    """Cluster of nearby price level candidates."""

    lower_bound: float
    upper_bound: float
    midpoint: float
    candidates: tuple[PriceLevelCandidate, ...]
    source_methods: tuple[str, ...]

    def __post_init__(self) -> None:
        lower_bound = _normalize_price(self.lower_bound)
        upper_bound = _normalize_price(self.upper_bound)
        midpoint = _normalize_price(self.midpoint)
        if lower_bound > upper_bound:
            raise ValueError("lower_bound must be less than or equal to upper_bound")
        if not lower_bound <= midpoint <= upper_bound:
            raise ValueError("midpoint must be within [lower_bound, upper_bound]")
        candidates = _normalize_candidate_tuple(self.candidates, "candidates")
        if not candidates:
            raise ValueError("candidates must not be empty")
        for candidate in candidates:
            if candidate.price < lower_bound or candidate.price > upper_bound:
                raise ValueError("candidates must stay within the zone bounds")
        object.__setattr__(self, "lower_bound", lower_bound)
        object.__setattr__(self, "upper_bound", upper_bound)
        object.__setattr__(self, "midpoint", midpoint)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(
            self,
            "source_methods",
            _normalize_source_methods_tuple(self.source_methods),
        )


@dataclass(frozen=True, slots=True)
class PriceZoneObservation:
    """Independent touch statistics for a price zone."""

    touch_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None

    def __post_init__(self) -> None:
        touch_count = _require_non_negative_int(self.touch_count, "touch_count")
        first_observed_at = _normalize_optional_timestamp(
            self.first_observed_at,
            "first_observed_at",
        )
        last_observed_at = _normalize_optional_timestamp(
            self.last_observed_at,
            "last_observed_at",
        )
        if touch_count == 0:
            if first_observed_at is not None or last_observed_at is not None:
                raise ValueError(
                    "first_observed_at and last_observed_at must be None when "
                    "touch_count is 0"
                )
        else:
            if first_observed_at is None or last_observed_at is None:
                raise ValueError(
                    "first_observed_at and last_observed_at must be provided when "
                    "touch_count is greater than 0"
                )
            if first_observed_at > last_observed_at:
                raise ValueError(
                    "first_observed_at must be earlier than or equal to "
                    "last_observed_at"
                )
        object.__setattr__(self, "touch_count", touch_count)
        object.__setattr__(self, "first_observed_at", first_observed_at)
        object.__setattr__(self, "last_observed_at", last_observed_at)


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


def _require_positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite")
    if numeric_value <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0")
    return numeric_value


def _normalize_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("observed_at must be a datetime")
    if value.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_optional_timestamp(
    value: object,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _normalize_candidate_tuple(
    values: object,
    field_name: str,
) -> tuple[PriceLevelCandidate, ...]:
    if isinstance(values, (str, bytes, bytearray, dict)):
        raise TypeError(f"{field_name} must be a tuple or list")
    if isinstance(values, tuple):
        container = values
    elif isinstance(values, list):
        container = tuple(values)
    else:
        raise TypeError(f"{field_name} must be a tuple or list")
    normalized: list[PriceLevelCandidate] = []
    for value in container:
        if not isinstance(value, PriceLevelCandidate):
            raise TypeError(
                f"{field_name} elements must be PriceLevelCandidate instances"
            )
        normalized.append(value)
    return tuple(normalized)


def _normalize_source_methods_tuple(values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray, dict)):
        raise TypeError("source_methods must be a tuple or list")
    if isinstance(values, tuple):
        container = values
    elif isinstance(values, list):
        container = tuple(values)
    else:
        raise TypeError("source_methods must be a tuple or list")
    unique: list[str] = []
    seen: set[str] = set()
    for value in container:
        method = _normalize_required_text(value, "source_methods")
        if method in seen:
            continue
        seen.add(method)
        unique.append(method)
    if not unique:
        raise ValueError("source_methods must not be empty")
    return tuple(unique)