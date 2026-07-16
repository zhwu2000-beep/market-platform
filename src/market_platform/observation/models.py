"""Immutable market observation boundary models."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from numbers import Real

from market_platform.signals.models import MarketSignal
from market_platform.structure.models import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceStructureStatus,
)


@dataclass(frozen=True, slots=True)
class ObservationIdentity:
    """Identity and observation window for a market fact snapshot."""

    symbol: str
    interval: str
    as_of: datetime
    window_start: datetime
    window_end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(
            self,
            "interval",
            _normalize_required_text(self.interval, "interval"),
        )
        as_of = _normalize_timestamp(self.as_of, "as_of")
        window_start = _normalize_timestamp(self.window_start, "window_start")
        window_end = _normalize_timestamp(self.window_end, "window_end")
        if window_start > window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if window_end > as_of:
            raise ValueError("window_end must be earlier than or equal to as_of")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "window_start", window_start)
        object.__setattr__(self, "window_end", window_end)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "as_of": self.as_of.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ObservationProvenance:
    """Source and methodology metadata for a market observation."""

    provider: str
    methodology: str
    methodology_version: str
    parameters: Mapping[str, object]
    input_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider",
            _normalize_required_text(self.provider, "provider"),
        )
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        object.__setattr__(
            self,
            "methodology_version",
            _normalize_required_text(
                self.methodology_version,
                "methodology_version",
            ),
        )
        object.__setattr__(
            self,
            "parameters",
            _copy_parameters(self.parameters),
        )
        object.__setattr__(
            self,
            "input_fingerprint",
            _normalize_required_text(
                self.input_fingerprint,
                "input_fingerprint",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "provider": self.provider,
            "methodology": self.methodology,
            "methodology_version": self.methodology_version,
            "parameters": _serialize_mapping(self.parameters),
            "input_fingerprint": self.input_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class PriceFacts:
    """Latest observed price without directional interpretation."""

    latest_price: float
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "latest_price",
            _normalize_positive_number(self.latest_price, "latest_price"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _normalize_timestamp(self.observed_at, "observed_at"),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "latest_price": self.latest_price,
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class SignalFacts:
    """Raw calculated signal values at an observation time."""

    symbol: str
    as_of: datetime
    signals: tuple[MarketSignal, ...]

    def __post_init__(self) -> None:
        symbol = _normalize_symbol(self.symbol)
        as_of = _normalize_timestamp(self.as_of, "as_of")
        signals = _normalize_signal_tuple(self.signals)
        if any(
            _normalize_signal_timestamp(signal.timestamp) > as_of
            for signal in signals
        ):
            raise ValueError("signals must not contain values later than as_of")
        if any(signal.symbol.strip().upper() != symbol for signal in signals):
            raise ValueError("signals must match SignalFacts.symbol")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "signals", signals)

    def to_dict(self) -> dict[str, object]:
        """Return raw signal facts as JSON-compatible data."""

        return {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "signals": [_signal_to_dict(signal) for signal in self.signals],
        }


@dataclass(frozen=True, slots=True)
class StructureFacts:
    """Point-in-time structure facts copied from a structure snapshot."""

    status: PriceStructureStatus
    as_of: datetime | None
    current_price: float | None
    atr: float | None
    confirmed_pivots: tuple[PriceLevelCandidate, ...]
    available_zones: tuple[ObservedPriceZone, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, PriceStructureStatus):
            raise TypeError("status must be a PriceStructureStatus")
        as_of = _normalize_optional_timestamp(self.as_of, "as_of")
        current_price = _normalize_optional_positive_number(
            self.current_price,
            "current_price",
        )
        atr = _normalize_optional_non_negative_number(self.atr, "atr")
        confirmed_pivots = _normalize_model_tuple(
            self.confirmed_pivots,
            "confirmed_pivots",
            PriceLevelCandidate,
        )
        available_zones = _normalize_model_tuple(
            self.available_zones,
            "available_zones",
            ObservedPriceZone,
        )
        if (confirmed_pivots or available_zones) and as_of is None:
            raise ValueError("as_of is required when structure facts are present")
        if as_of is not None:
            if any(pivot.confirmed_at > as_of for pivot in confirmed_pivots):
                raise ValueError(
                    "confirmed_pivots must be confirmed no later than as_of"
                )
            if any(zone.zone.available_at > as_of for zone in available_zones):
                raise ValueError(
                    "available_zones must be available no later than as_of"
                )
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "current_price", current_price)
        object.__setattr__(self, "atr", atr)
        object.__setattr__(self, "confirmed_pivots", confirmed_pivots)
        object.__setattr__(self, "available_zones", available_zones)

    def to_dict(self) -> dict[str, object]:
        """Return point-in-time structure facts as JSON-compatible data."""

        return {
            "status": self.status.value,
            "as_of": self.as_of.isoformat() if self.as_of is not None else None,
            "current_price": self.current_price,
            "atr": self.atr,
            "confirmed_pivots": [
                _pivot_to_dict(pivot) for pivot in self.confirmed_pivots
            ],
            "available_zones": [
                _observed_zone_to_dict(zone) for zone in self.available_zones
            ],
        }


@dataclass(frozen=True, slots=True)
class MarketObservation:
    """Immutable container for observed market facts."""

    identity: ObservationIdentity
    provenance: ObservationProvenance
    price_facts: PriceFacts | None = None
    signal_facts: SignalFacts | None = None
    structure_facts: StructureFacts | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ObservationIdentity):
            raise TypeError("identity must be an ObservationIdentity")
        if not isinstance(self.provenance, ObservationProvenance):
            raise TypeError("provenance must be an ObservationProvenance")
        if self.price_facts is not None:
            if not isinstance(self.price_facts, PriceFacts):
                raise TypeError("price_facts must be a PriceFacts or None")
            if self.price_facts.observed_at > self.identity.as_of:
                raise ValueError("price_facts must not be later than identity.as_of")
        if self.signal_facts is not None:
            if not isinstance(self.signal_facts, SignalFacts):
                raise TypeError("signal_facts must be a SignalFacts or None")
            if self.signal_facts.as_of > self.identity.as_of:
                raise ValueError("signal_facts must not be later than identity.as_of")
            if self.signal_facts.symbol != self.identity.symbol:
                raise ValueError("signal_facts symbol must match identity.symbol")
        if self.structure_facts is not None:
            if not isinstance(self.structure_facts, StructureFacts):
                raise TypeError("structure_facts must be a StructureFacts or None")
            if (
                self.structure_facts.as_of is not None
                and self.structure_facts.as_of > self.identity.as_of
            ):
                raise ValueError(
                    "structure_facts must not be later than identity.as_of"
                )

    def to_dict(self) -> dict[str, object]:
        """Return a nested JSON-compatible representation."""

        return {
            "identity": self.identity.to_dict(),
            "provenance": self.provenance.to_dict(),
            "price_facts": (
                self.price_facts.to_dict()
                if self.price_facts is not None
                else None
            ),
            "signal_facts": (
                self.signal_facts.to_dict()
                if self.signal_facts is not None
                else None
            ),
            "structure_facts": (
                self.structure_facts.to_dict()
                if self.structure_facts is not None
                else None
            ),
        }


def _normalize_symbol(value: object) -> str:
    return _normalize_required_text(value, "symbol").upper()


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


def _normalize_optional_timestamp(
    value: object,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    return _normalize_timestamp(value, field_name)


def _normalize_positive_number(value: object, field_name: str) -> float:
    numeric = _normalize_number(value, field_name)
    if numeric <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0")
    return numeric


def _normalize_optional_positive_number(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _normalize_positive_number(value, field_name)


def _normalize_optional_non_negative_number(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    numeric = _normalize_number(value, field_name)
    if numeric < 0.0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric


def _normalize_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    return numeric


def _normalize_signal_tuple(values: object) -> tuple[MarketSignal, ...]:
    normalized = _normalize_model_tuple(values, "signals", MarketSignal)
    return tuple(
        MarketSignal(
            symbol=signal.symbol,
            name=signal.name,
            value=signal.value,
            timestamp=_normalize_signal_timestamp(signal.timestamp),
            parameters=dict(signal.parameters),
        )
        for signal in normalized
    )


def _normalize_model_tuple[ModelT](
    values: object,
    field_name: str,
    model_type: type[ModelT],
) -> tuple[ModelT, ...]:
    if isinstance(values, tuple):
        container = values
    elif isinstance(values, list):
        container = tuple(values)
    else:
        raise TypeError(f"{field_name} must be a tuple or list")
    for value in container:
        if not isinstance(value, model_type):
            raise TypeError(
                f"{field_name} elements must be {model_type.__name__} instances"
            )
    return container


def _normalize_signal_timestamp(value: datetime) -> datetime:
    return _normalize_timestamp(value, "signal timestamp")


def _copy_parameters(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("parameters must be a mapping")
    copied: dict[str, object] = {}
    for key, parameter_value in value.items():
        normalized_key = _normalize_required_text(key, "parameters key")
        if normalized_key in copied:
            raise ValueError("parameters keys must be unique after normalization")
        copied[normalized_key] = parameter_value
    return copied


def _serialize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _serialize_value(item) for key, item in value.items()}


def _serialize_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _serialize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    return value


def _signal_to_dict(signal: MarketSignal) -> dict[str, object]:
    return {
        "symbol": signal.symbol,
        "name": signal.name,
        "value": signal.value,
        "timestamp": signal.timestamp.isoformat(),
        "parameters": _serialize_mapping(signal.parameters),
    }


def _pivot_to_dict(pivot: PriceLevelCandidate) -> dict[str, object]:
    return {
        "price": pivot.price,
        "kind": pivot.kind.value,
        "occurred_at": pivot.occurred_at.isoformat(),
        "confirmed_at": pivot.confirmed_at.isoformat(),
        "observed_at": pivot.observed_at.isoformat(),
        "source_method": pivot.source_method,
    }


def _observed_zone_to_dict(observed: ObservedPriceZone) -> dict[str, object]:
    zone = observed.zone
    observation = observed.observation
    return {
        "zone": {
            "lower_bound": zone.lower_bound,
            "upper_bound": zone.upper_bound,
            "midpoint": zone.midpoint,
            "available_at": zone.available_at.isoformat(),
            "candidates": [
                _pivot_to_dict(pivot) for pivot in zone.candidates
            ],
            "source_methods": list(zone.source_methods),
        },
        "observation": {
            "touch_count": observation.touch_count,
            "first_observed_at": (
                observation.first_observed_at.isoformat()
                if observation.first_observed_at is not None
                else None
            ),
            "last_observed_at": (
                observation.last_observed_at.isoformat()
                if observation.last_observed_at is not None
                else None
            ),
        },
    }
