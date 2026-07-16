"""Immutable strategy evaluation domain models."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType


class StrategyEvaluationStatus(StrEnum):
    """Outcome of evaluating whether a strategy applies to current inputs."""

    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_DATA = "insufficient_data"


class StrategyEvidenceSource(StrEnum):
    """Upstream domain from which strategy evidence was read."""

    MARKET_STATE = "market_state"
    MARKET_OBSERVATION = "market_observation"


type StrategyEvidenceValue = str | int | float | bool | datetime | None


@dataclass(frozen=True, slots=True)
class StrategyEvidence:
    """Typed record of one fact or state used by a strategy evaluation."""

    source: StrategyEvidenceSource
    field: str
    observed_value: StrategyEvidenceValue
    rationale: str
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, StrategyEvidenceSource):
            raise TypeError("source must be a StrategyEvidenceSource")
        object.__setattr__(
            self,
            "field",
            _normalize_required_text(self.field, "field"),
        )
        object.__setattr__(
            self,
            "observed_value",
            _normalize_evidence_value(self.observed_value),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_required_text(self.rationale, "rationale"),
        )
        if self.observed_at is not None:
            object.__setattr__(
                self,
                "observed_at",
                _normalize_timestamp(self.observed_at, "observed_at"),
            )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible evidence representation."""

        observed_value: object = self.observed_value
        if isinstance(observed_value, datetime):
            observed_value = observed_value.isoformat()
        return {
            "source": self.source.value,
            "field": self.field,
            "observed_value": observed_value,
            "rationale": self.rationale,
            "observed_at": (
                self.observed_at.isoformat() if self.observed_at is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class StrategyProvenance:
    """Immutable strategy identity, configuration, and input provenance."""

    strategy_id: str
    strategy_version: str
    parameters: Mapping[str, object]
    observation_fingerprint: str | None
    state_model_id: str
    state_model_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strategy_id",
            _normalize_required_text(self.strategy_id, "strategy_id"),
        )
        object.__setattr__(
            self,
            "strategy_version",
            _normalize_required_text(self.strategy_version, "strategy_version"),
        )
        object.__setattr__(self, "parameters", _freeze_parameters(self.parameters))
        if self.observation_fingerprint is not None:
            object.__setattr__(
                self,
                "observation_fingerprint",
                _normalize_required_text(
                    self.observation_fingerprint,
                    "observation_fingerprint",
                ),
            )
        object.__setattr__(
            self,
            "state_model_id",
            _normalize_required_text(self.state_model_id, "state_model_id"),
        )
        object.__setattr__(
            self,
            "state_model_version",
            _normalize_required_text(
                self.state_model_version,
                "state_model_version",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible provenance representation."""

        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "parameters": _serialize_mapping(self.parameters),
            "observation_fingerprint": self.observation_fingerprint,
            "state_model_id": self.state_model_id,
            "state_model_version": self.state_model_version,
        }


@dataclass(frozen=True, slots=True)
class StrategyEvaluation:
    """Point-in-time, non-executable evaluation produced by a strategy."""

    symbol: str
    interval: str
    as_of: datetime
    provenance: StrategyProvenance
    status: StrategyEvaluationStatus
    rationale: str
    required_inputs: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    evidence: tuple[StrategyEvidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(
            self,
            "interval",
            _normalize_required_text(self.interval, "interval"),
        )
        as_of = _normalize_timestamp(self.as_of, "as_of")
        object.__setattr__(self, "as_of", as_of)
        if not isinstance(self.provenance, StrategyProvenance):
            raise TypeError("provenance must be a StrategyProvenance")
        if not isinstance(self.status, StrategyEvaluationStatus):
            raise TypeError("status must be a StrategyEvaluationStatus")
        object.__setattr__(
            self,
            "rationale",
            _normalize_required_text(self.rationale, "rationale"),
        )
        required_inputs = _normalize_text_tuple(
            self.required_inputs,
            "required_inputs",
        )
        missing_inputs = _normalize_text_tuple(
            self.missing_inputs,
            "missing_inputs",
        )
        if not set(missing_inputs).issubset(required_inputs):
            raise ValueError("missing_inputs must be a subset of required_inputs")
        if (
            self.status
            in {
                StrategyEvaluationStatus.APPLICABLE,
                StrategyEvaluationStatus.NOT_APPLICABLE,
            }
            and missing_inputs
        ):
            raise ValueError(
                f"{self.status.value} evaluation must not have missing_inputs"
            )
        if (
            self.status is StrategyEvaluationStatus.INSUFFICIENT_DATA
            and not missing_inputs
        ):
            raise ValueError("insufficient_data evaluation must have missing_inputs")
        evidence = _normalize_evidence_tuple(self.evidence)
        if any(
            item.observed_at is not None and item.observed_at > as_of
            for item in evidence
        ):
            raise ValueError("evidence observed_at must not be later than as_of")
        object.__setattr__(self, "required_inputs", required_inputs)
        object.__setattr__(self, "missing_inputs", missing_inputs)
        object.__setattr__(self, "evidence", evidence)

    def to_dict(self) -> dict[str, object]:
        """Return a nested JSON-compatible evaluation representation."""

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "as_of": self.as_of.isoformat(),
            "provenance": self.provenance.to_dict(),
            "status": self.status.value,
            "rationale": self.rationale,
            "required_inputs": list(self.required_inputs),
            "missing_inputs": list(self.missing_inputs),
            "evidence": [item.to_dict() for item in self.evidence],
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


def _normalize_evidence_value(value: object) -> StrategyEvidenceValue:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("observed_value float must be finite")
        return value
    if isinstance(value, datetime):
        return _normalize_timestamp(value, "observed_value")
    raise TypeError("observed_value must be a str, int, float, bool, datetime, or None")


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


def _normalize_evidence_tuple(value: object) -> tuple[StrategyEvidence, ...]:
    if isinstance(value, tuple):
        container = value
    elif isinstance(value, list):
        container = tuple(value)
    else:
        raise TypeError("evidence must be a tuple or list")
    for item in container:
        if not isinstance(item, StrategyEvidence):
            raise TypeError("evidence elements must be StrategyEvidence instances")
    return container


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
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parameters numeric values must be finite")
        return value
    raise TypeError("parameters values must be JSON-compatible")


def _serialize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _serialize_value(item) for key, item in value.items()}


def _serialize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _serialize_mapping(value)
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value
