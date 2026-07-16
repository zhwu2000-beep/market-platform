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
class StateSignalEvidence:
    """Immutable evidence for one normalized directional component."""

    name: str
    raw_value: float | None
    normalized_score: float | None
    normalization_scale: float
    configured_weight: float
    normalized_weight: float | None
    weighted_contribution: float | None
    interpreted_state: str
    methodology: str
    source_parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_required_text(self.name, "name"))
        object.__setattr__(
            self,
            "raw_value",
            _normalize_optional_finite_number(self.raw_value, "raw_value"),
        )
        object.__setattr__(
            self,
            "normalized_score",
            _normalize_optional_unit_score(
                self.normalized_score,
                "normalized_score",
            ),
        )
        object.__setattr__(
            self,
            "normalization_scale",
            _require_positive_finite_number(
                self.normalization_scale,
                "normalization_scale",
            ),
        )
        object.__setattr__(
            self,
            "configured_weight",
            _require_positive_finite_number(
                self.configured_weight,
                "configured_weight",
            ),
        )
        object.__setattr__(
            self,
            "normalized_weight",
            _normalize_optional_non_negative_number(
                self.normalized_weight,
                "normalized_weight",
            ),
        )
        object.__setattr__(
            self,
            "weighted_contribution",
            _normalize_optional_finite_number(
                self.weighted_contribution,
                "weighted_contribution",
            ),
        )
        object.__setattr__(
            self,
            "interpreted_state",
            _normalize_required_text(
                self.interpreted_state,
                "interpreted_state",
            ),
        )
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        object.__setattr__(
            self,
            "source_parameters",
            _freeze_parameters(self.source_parameters),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible evidence representation."""

        return {
            "name": self.name,
            "raw_value": self.raw_value,
            "normalized_score": self.normalized_score,
            "normalization_scale": self.normalization_scale,
            "configured_weight": self.configured_weight,
            "normalized_weight": self.normalized_weight,
            "weighted_contribution": self.weighted_contribution,
            "interpreted_state": self.interpreted_state,
            "methodology": self.methodology,
            "source_parameters": _serialize_mapping(self.source_parameters),
        }


@dataclass(frozen=True, slots=True)
class StateClassificationThresholdEvidence:
    """Classification thresholds used during a state evaluation."""

    strong_bearish: float
    bearish: float
    bullish: float
    strong_bullish: float

    def __post_init__(self) -> None:
        values = (
            _require_unit_score(self.strong_bearish, "strong_bearish"),
            _require_unit_score(self.bearish, "bearish"),
            _require_unit_score(self.bullish, "bullish"),
            _require_unit_score(self.strong_bullish, "strong_bullish"),
        )
        if not values[0] < values[1] < values[2] < values[3]:
            raise ValueError("classification thresholds must be strictly increasing")
        object.__setattr__(self, "strong_bearish", values[0])
        object.__setattr__(self, "bearish", values[1])
        object.__setattr__(self, "bullish", values[2])
        object.__setattr__(self, "strong_bullish", values[3])

    def to_dict(self) -> dict[str, object]:
        """Return classification thresholds as JSON-compatible data."""

        return {
            "strong_bearish": self.strong_bearish,
            "bearish": self.bearish,
            "bullish": self.bullish,
            "strong_bullish": self.strong_bullish,
        }


@dataclass(frozen=True, slots=True)
class StateCompositeEvidence:
    """Immutable evidence for the evaluated directional composite."""

    score: float | None
    classification: str | None
    methodology: str
    formula: str
    thresholds: StateClassificationThresholdEvidence
    component_order: tuple[str, ...]
    included_signals: tuple[str, ...]
    missing_signals: tuple[str, ...]

    def __post_init__(self) -> None:
        score = _normalize_optional_unit_score(self.score, "score")
        classification = (
            None
            if self.classification is None
            else _normalize_required_text(
                self.classification,
                "classification",
            )
        )
        if (score is None) != (classification is None):
            raise ValueError(
                "score and classification must either both be present or both be None"
            )
        if not isinstance(
            self.thresholds,
            StateClassificationThresholdEvidence,
        ):
            raise TypeError(
                "thresholds must be a StateClassificationThresholdEvidence"
            )
        component_order = _normalize_text_tuple(
            self.component_order,
            "component_order",
        )
        if not component_order:
            raise ValueError("component_order must not be empty")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "classification", classification)
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        object.__setattr__(
            self,
            "formula",
            _normalize_required_text(self.formula, "formula"),
        )
        object.__setattr__(self, "component_order", component_order)
        object.__setattr__(
            self,
            "included_signals",
            _normalize_text_tuple(self.included_signals, "included_signals"),
        )
        object.__setattr__(
            self,
            "missing_signals",
            _normalize_text_tuple(self.missing_signals, "missing_signals"),
        )

    def to_dict(self) -> dict[str, object]:
        """Return composite evidence as JSON-compatible data."""

        return {
            "score": self.score,
            "classification": self.classification,
            "methodology": self.methodology,
            "formula": self.formula,
            "thresholds": self.thresholds.to_dict(),
            "component_order": list(self.component_order),
            "included_signals": list(self.included_signals),
            "missing_signals": list(self.missing_signals),
        }


@dataclass(frozen=True, slots=True)
class StateVolatilityEvidence:
    """Immutable evidence for the evaluated volatility regime."""

    raw_value: float | None
    low_threshold: float
    high_threshold: float
    regime: VolatilityRegime
    methodology: str

    def __post_init__(self) -> None:
        raw_value = _normalize_optional_finite_number(
            self.raw_value,
            "raw_value",
        )
        low = _normalize_non_negative_number(
            self.low_threshold,
            "low_threshold",
        )
        high = _normalize_non_negative_number(
            self.high_threshold,
            "high_threshold",
        )
        if low >= high:
            raise ValueError("low_threshold must be less than high_threshold")
        _require_enum(self.regime, VolatilityRegime, "regime")
        object.__setattr__(self, "raw_value", raw_value)
        object.__setattr__(self, "low_threshold", low)
        object.__setattr__(self, "high_threshold", high)
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )

    def to_dict(self) -> dict[str, object]:
        """Return volatility evidence as JSON-compatible data."""

        return {
            "raw_value": self.raw_value,
            "low_threshold": self.low_threshold,
            "high_threshold": self.high_threshold,
            "regime": self.regime.value,
            "methodology": self.methodology,
        }


@dataclass(frozen=True, slots=True)
class StateEvaluationEvidence:
    """Immutable non-predictive evidence produced during state evaluation."""

    directional_components: tuple[StateSignalEvidence, ...]
    composite: StateCompositeEvidence
    volatility: StateVolatilityEvidence

    def __post_init__(self) -> None:
        components = _normalize_evidence_tuple(
            self.directional_components,
            "directional_components",
            StateSignalEvidence,
        )
        if not isinstance(self.composite, StateCompositeEvidence):
            raise TypeError("composite must be a StateCompositeEvidence")
        if not isinstance(self.volatility, StateVolatilityEvidence):
            raise TypeError("volatility must be a StateVolatilityEvidence")
        if tuple(component.name for component in components) != (
            self.composite.component_order
        ):
            raise ValueError(
                "directional component names must match composite component_order"
            )
        object.__setattr__(self, "directional_components", components)

    def to_dict(self) -> dict[str, object]:
        """Return evaluation evidence as JSON-compatible data."""

        return {
            "directional_components": [
                component.to_dict()
                for component in self.directional_components
            ],
            "composite": self.composite.to_dict(),
            "volatility": self.volatility.to_dict(),
        }


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
    evaluation_evidence: StateEvaluationEvidence | None = None

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
        if self.evaluation_evidence is not None and not isinstance(
            self.evaluation_evidence,
            StateEvaluationEvidence,
        ):
            raise TypeError(
                "evaluation_evidence must be a StateEvaluationEvidence or None"
            )

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
            "evaluation_evidence": (
                self.evaluation_evidence.to_dict()
                if self.evaluation_evidence is not None
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


def _normalize_evidence_tuple[EvidenceT](
    value: object,
    field_name: str,
    evidence_type: type[EvidenceT],
) -> tuple[EvidenceT, ...]:
    if isinstance(value, tuple):
        container = value
    elif isinstance(value, list):
        container = tuple(value)
    else:
        raise TypeError(f"{field_name} must be a tuple or list")
    for item in container:
        if not isinstance(item, evidence_type):
            raise TypeError(
                f"{field_name} elements must be {evidence_type.__name__} instances"
            )
    return container


def _normalize_optional_finite_number(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _normalize_finite_number(value, field_name)


def _normalize_optional_unit_score(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _require_unit_score(value, field_name)


def _require_unit_score(value: object, field_name: str) -> float:
    numeric = _normalize_finite_number(value, field_name)
    if not -1.0 <= numeric <= 1.0:
        raise ValueError(f"{field_name} must be within [-1.0, 1.0]")
    return numeric


def _require_positive_finite_number(value: object, field_name: str) -> float:
    numeric = _normalize_finite_number(value, field_name)
    if numeric <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0")
    return numeric


def _normalize_optional_non_negative_number(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _normalize_non_negative_number(value, field_name)


def _normalize_non_negative_number(value: object, field_name: str) -> float:
    numeric = _normalize_finite_number(value, field_name)
    if numeric < 0.0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric


def _normalize_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    return numeric


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
