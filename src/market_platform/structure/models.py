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


class PriceStructureStatus(StrEnum):
    """Outcome of a price structure analysis."""

    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"
    NO_PIVOTS = "no_pivots"
    VOLATILITY_UNAVAILABLE = "volatility_unavailable"


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


@dataclass(frozen=True, slots=True)
class ObservedPriceZone:
    """Price-zone geometry paired with its independent touch observation."""

    zone: PriceZone
    observation: PriceZoneObservation

    def __post_init__(self) -> None:
        if not isinstance(self.zone, PriceZone):
            raise TypeError("zone must be a PriceZone")
        if not isinstance(self.observation, PriceZoneObservation):
            raise TypeError("observation must be a PriceZoneObservation")


@dataclass(frozen=True, slots=True)
class PriceStructureSnapshot:
    """Immutable facts produced by a price structure analysis."""

    status: PriceStructureStatus
    as_of: datetime | None = None
    current_price: float | None = None
    atr: float | None = None
    candidates: tuple[PriceLevelCandidate, ...] = ()
    observed_zones: tuple[ObservedPriceZone, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, PriceStructureStatus):
            raise TypeError("status must be a PriceStructureStatus")

        as_of = _normalize_optional_timestamp(self.as_of, "as_of")
        current_price = _normalize_optional_positive_number(
            self.current_price,
            "current_price",
        )
        atr = _normalize_optional_non_negative_number(self.atr, "atr")
        candidates = tuple(
            sorted(
                _normalize_candidate_tuple(self.candidates, "candidates"),
                key=_candidate_sort_key,
            )
        )
        observed_zones = tuple(
            sorted(
                _normalize_observed_zone_tuple(self.observed_zones),
                key=_observed_zone_sort_key,
            )
        )

        if self.status is PriceStructureStatus.OK:
            if as_of is None:
                raise ValueError("as_of must be provided when status is OK")
            if current_price is None:
                raise ValueError("current_price must be provided when status is OK")
            if atr is None or atr <= 0.0:
                raise ValueError("atr must be greater than 0 when status is OK")
            if not candidates:
                raise ValueError("candidates must not be empty when status is OK")
            if not observed_zones:
                raise ValueError("observed_zones must not be empty when status is OK")
            _validate_candidate_partition(candidates, observed_zones)
        elif self.status is PriceStructureStatus.INSUFFICIENT_DATA:
            if atr is not None:
                raise ValueError("atr must be None when status is INSUFFICIENT_DATA")
            if candidates:
                raise ValueError(
                    "candidates must be empty when status is INSUFFICIENT_DATA"
                )
            if observed_zones:
                raise ValueError(
                    "observed_zones must be empty when status is INSUFFICIENT_DATA"
                )
        elif self.status is PriceStructureStatus.NO_PIVOTS:
            if as_of is None:
                raise ValueError("as_of must be provided when status is NO_PIVOTS")
            if current_price is None:
                raise ValueError(
                    "current_price must be provided when status is NO_PIVOTS"
                )
            if atr is not None:
                raise ValueError("atr must be None when status is NO_PIVOTS")
            if candidates:
                raise ValueError("candidates must be empty when status is NO_PIVOTS")
            if observed_zones:
                raise ValueError(
                    "observed_zones must be empty when status is NO_PIVOTS"
                )
        else:
            if as_of is None:
                raise ValueError(
                    "as_of must be provided when status is VOLATILITY_UNAVAILABLE"
                )
            if current_price is None:
                raise ValueError(
                    "current_price must be provided when status is "
                    "VOLATILITY_UNAVAILABLE"
                )
            if not candidates:
                raise ValueError(
                    "candidates must not be empty when volatility is unavailable"
                )
            if observed_zones:
                raise ValueError(
                    "observed_zones must be empty when status is "
                    "VOLATILITY_UNAVAILABLE"
                )
            if atr not in (None, 0.0):
                raise ValueError(
                    "atr must be None or 0 when status is VOLATILITY_UNAVAILABLE"
                )

        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "current_price", current_price)
        object.__setattr__(self, "atr", atr)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "observed_zones", observed_zones)

    @property
    def lower_zones(self) -> tuple[ObservedPriceZone, ...]:
        """Zones below the current price, nearest first."""

        if self.current_price is None:
            return ()
        current_price = self.current_price
        zones = (
            observed
            for observed in self.observed_zones
            if observed.zone.upper_bound < current_price
        )
        return tuple(
            sorted(
                zones,
                key=lambda observed: (
                    current_price - observed.zone.upper_bound,
                    -observed.zone.midpoint,
                    observed.zone.lower_bound,
                ),
            )
        )

    @property
    def containing_zones(self) -> tuple[ObservedPriceZone, ...]:
        """Zones whose inclusive bounds contain the current price."""

        if self.current_price is None:
            return ()
        current_price = self.current_price
        return tuple(
            observed
            for observed in self.observed_zones
            if observed.zone.lower_bound
            <= current_price
            <= observed.zone.upper_bound
        )

    @property
    def upper_zones(self) -> tuple[ObservedPriceZone, ...]:
        """Zones above the current price, nearest first."""

        if self.current_price is None:
            return ()
        current_price = self.current_price
        zones = (
            observed
            for observed in self.observed_zones
            if observed.zone.lower_bound > current_price
        )
        return tuple(
            sorted(
                zones,
                key=lambda observed: (
                    observed.zone.lower_bound - current_price,
                    observed.zone.midpoint,
                    observed.zone.upper_bound,
                ),
            )
        )

    @property
    def nearest_lower_zone(self) -> ObservedPriceZone | None:
        """Nearest zone strictly below the current price, if any."""

        lower_zones = self.lower_zones
        return lower_zones[0] if lower_zones else None

    @property
    def nearest_upper_zone(self) -> ObservedPriceZone | None:
        """Nearest zone strictly above the current price, if any."""

        upper_zones = self.upper_zones
        return upper_zones[0] if upper_zones else None


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


def _normalize_optional_positive_number(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    numeric_value = _normalize_finite_number(value, field_name)
    if numeric_value <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0")
    return numeric_value


def _normalize_optional_non_negative_number(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    numeric_value = _normalize_finite_number(value, field_name)
    if numeric_value < 0.0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric_value


def _normalize_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite")
    return numeric_value


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


def _normalize_observed_zone_tuple(
    values: object,
) -> tuple[ObservedPriceZone, ...]:
    if isinstance(values, (str, bytes, bytearray, dict)):
        raise TypeError("observed_zones must be a tuple or list")
    if isinstance(values, tuple):
        container = values
    elif isinstance(values, list):
        container = tuple(values)
    else:
        raise TypeError("observed_zones must be a tuple or list")
    normalized: list[ObservedPriceZone] = []
    for value in container:
        if not isinstance(value, ObservedPriceZone):
            raise TypeError(
                "observed_zones elements must be ObservedPriceZone instances"
            )
        normalized.append(value)
    return tuple(normalized)


def _candidate_sort_key(
    candidate: PriceLevelCandidate,
) -> tuple[str, str, float, str]:
    return (
        candidate.observed_at.isoformat(),
        candidate.kind.value,
        candidate.price,
        candidate.source_method,
    )


def _observed_zone_sort_key(
    observed: ObservedPriceZone,
) -> tuple[float, float, float, tuple[tuple[str, str, float, str], ...]]:
    zone = observed.zone
    return (
        zone.midpoint,
        zone.lower_bound,
        zone.upper_bound,
        tuple(_candidate_sort_key(candidate) for candidate in zone.candidates),
    )


def _validate_candidate_partition(
    candidates: tuple[PriceLevelCandidate, ...],
    observed_zones: tuple[ObservedPriceZone, ...],
) -> None:
    observed_candidates = tuple(
        sorted(
            (
                candidate
                for observed in observed_zones
                for candidate in observed.zone.candidates
            ),
            key=_candidate_sort_key,
        )
    )
    if len(set(candidates)) != len(candidates):
        raise ValueError("each candidate must appear exactly once")
    if len(set(observed_candidates)) != len(observed_candidates):
        raise ValueError("each candidate must appear exactly once")
    if observed_candidates != candidates:
        raise ValueError(
            "observed_zones candidates must match snapshot candidates exactly"
        )
