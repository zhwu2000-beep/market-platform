"""Immutable market state domain models."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from numbers import Real
from types import MappingProxyType


class DirectionalRegime(StrEnum):
    """Aggregate directional state without trading intent."""

    STRONG_UP = "strong_up"
    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"
    STRONG_DOWN = "strong_down"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class TrendRegime(StrEnum):
    """State of the observed price trend."""

    STRONG_UP = "strong_up"
    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"
    STRONG_DOWN = "strong_down"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class MomentumRegime(StrEnum):
    """State of observed price momentum."""

    STRONG_POSITIVE = "strong_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    STRONG_NEGATIVE = "strong_negative"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class VolatilityRegime(StrEnum):
    """State of observed market volatility."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class StructureState(StrEnum):
    """Availability state of point-in-time market structure facts."""

    AVAILABLE = "available"
    OBSERVED = "observed"
    INSUFFICIENT = "insufficient"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class StateQuality(StrEnum):
    """Completeness of the state evaluation inputs and result."""

    COMPLETE = "complete"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class StateModelProvenance:
    """Identity and immutable configuration of a state model evaluation."""

    model_id: str
    model_version: str
    parameters: Mapping[str, object]
    observation_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_id",
            _normalize_required_text(self.model_id, "model_id"),
        )
        object.__setattr__(
            self,
            "model_version",
            _normalize_required_text(self.model_version, "model_version"),
        )
        object.__setattr__(
            self,
            "parameters",
            _freeze_parameters(self.parameters),
        )
        if self.observation_fingerprint is not None:
            object.__setattr__(
                self,
                "observation_fingerprint",
                _normalize_required_text(
                    self.observation_fingerprint,
                    "observation_fingerprint",
                ),
            )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""

        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "parameters": _serialize_mapping(self.parameters),
            "observation_fingerprint": self.observation_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class MarketState:
    """Point-in-time interpretation of a market observation."""

    symbol: str
    interval: str
    as_of: datetime
    provenance: StateModelProvenance
    directional_regime: DirectionalRegime
    trend_regime: TrendRegime
    momentum_regime: MomentumRegime
    volatility_regime: VolatilityRegime
    structure_state: StructureState
    quality: StateQuality
    missing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(
            self,
            "interval",
            _normalize_required_text(self.interval, "interval"),
        )
        object.__setattr__(self, "as_of", _normalize_timestamp(self.as_of, "as_of"))
        if not isinstance(self.provenance, StateModelProvenance):
            raise TypeError("provenance must be a StateModelProvenance")
        _require_enum(
            self.directional_regime,
            DirectionalRegime,
            "directional_regime",
        )
        _require_enum(self.trend_regime, TrendRegime, "trend_regime")
        _require_enum(self.momentum_regime, MomentumRegime, "momentum_regime")
        _require_enum(
            self.volatility_regime,
            VolatilityRegime,
            "volatility_regime",
        )
        _require_enum(self.structure_state, StructureState, "structure_state")
        _require_enum(self.quality, StateQuality, "quality")
        missing_inputs = _normalize_text_tuple(self.missing_inputs, "missing_inputs")
        if self.quality is StateQuality.COMPLETE and missing_inputs:
            raise ValueError("complete state must not contain missing_inputs")
        object.__setattr__(self, "missing_inputs", missing_inputs)

    def to_dict(self) -> dict[str, object]:
        """Return a nested JSON-compatible representation."""

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "as_of": self.as_of.isoformat(),
            "provenance": self.provenance.to_dict(),
            "directional_regime": self.directional_regime.value,
            "trend_regime": self.trend_regime.value,
            "momentum_regime": self.momentum_regime.value,
            "volatility_regime": self.volatility_regime.value,
            "structure_state": self.structure_state.value,
            "quality": self.quality.value,
            "missing_inputs": list(self.missing_inputs),
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


def _require_enum[EnumT: StrEnum](
    value: object,
    enum_type: type[EnumT],
    field_name: str,
) -> EnumT:
    if not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be a {enum_type.__name__}")
    return value


def _normalize_text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, tuple):
        container = value
    elif isinstance(value, list):
        container = tuple(value)
    else:
        raise TypeError(f"{field_name} must be a tuple or list")
    normalized = tuple(
        _normalize_required_text(item, f"{field_name} element") for item in container
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _freeze_parameters(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("parameters must be a mapping")
    frozen: dict[str, object] = {}
    for raw_key, parameter_value in value.items():
        key = _normalize_required_text(raw_key, "parameters key")
        if key in frozen:
            raise ValueError("parameters keys must be unique after normalization")
        frozen[key] = _freeze_parameter_value(parameter_value)
    return MappingProxyType(frozen)


def _freeze_parameter_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_parameters(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_parameter_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("parameters numeric values must be finite")
        return numeric
    raise TypeError("parameters values must be JSON-compatible")


def _serialize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _serialize_value(item) for key, item in value.items()}


def _serialize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _serialize_mapping(value)
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value
