"""Pure Radar contracts. Fingerprints establish correspondence, never authority.

Configuration strings are inert data, never implementation/import selectors.
No value here admits Evidence, recommends a trade, or authorizes execution.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from market_platform._fingerprint import canonical_fingerprint

RADAR_GATE_IDENTITY_SCHEMA = "radar_gate_identity/v1"
RADAR_PROFILE_SCHEMA = "radar_profile/v1"


class RadarGateDisposition(StrEnum):
    """PASS continues; DROP filters; ATTENTION prevents ordinary filtering.

    DROP and ATTENTION terminate the instrument's remaining Gate sequence.
    Unexpected exceptions are execution failures, never Gate dispositions.
    """

    PASS = "PASS"
    DROP = "DROP"
    ATTENTION = "ATTENTION"


class RadarPipelineOutcome(StrEnum):
    """SELECTED means only all required Gates passed under the chosen Profile.

    FILTERED corresponds to DROP; ATTENTION to Gate ATTENTION; FAILED to an
    unexpected execution failure. None is an investment or authority decision.
    """

    SELECTED = "SELECTED"
    FILTERED = "FILTERED"
    ATTENTION = "ATTENTION"
    FAILED = "FAILED"


def _required_text(value: object, name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _freeze_mapping(
    value: object, ancestors: tuple[int, ...] = ()
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("configuration must be a mapping")
    if id(value) in ancestors:
        raise ValueError("configuration must not contain cycles")
    ancestors = (*ancestors, id(value))
    frozen: dict[str, object] = {}
    for key, item in value.items():
        _required_text(key, "configuration key")
        frozen[key] = _freeze_value(item, ancestors)
    return MappingProxyType(frozen)


def _freeze_value(value: object, ancestors: tuple[int, ...]) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value, ancestors)
    if isinstance(value, (list, tuple)):
        if id(value) in ancestors:
            raise ValueError("configuration must not contain cycles")
        return tuple(_freeze_value(item, (*ancestors, id(value))) for item in value)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("configuration numbers must be finite")
        return 0.0 if value == 0.0 else value
    raise TypeError("configuration values must be JSON scalars, mappings or sequences")


def _serialize(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _serialize(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RadarGateIdentity:
    """Versioned Gate definition with detached, deeply immutable configuration."""

    gate_id: str
    behavioral_revision: str
    configuration_schema: str
    configuration: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = field(init=False, default=RADAR_GATE_IDENTITY_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("gate_id", "behavioral_revision", "configuration_schema"):
            _required_text(getattr(self, name), name)
        object.__setattr__(self, "configuration", _freeze_mapping(self.configuration))
        object.__setattr__(self, "fingerprint", canonical_fingerprint(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "gate_id": self.gate_id,
            "behavioral_revision": self.behavioral_revision,
            "configuration_schema": self.configuration_schema,
            "configuration": _serialize(self.configuration),
        }

    def to_dict(self) -> dict[str, object]:
        """Return detached JSON-compatible identity content and fingerprint."""
        return {**self._payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class RadarGateOccurrence:
    """Profile-local step identity; position is independently set by Profile order."""

    occurrence_id: str
    gate_identity: RadarGateIdentity

    def __post_init__(self) -> None:
        _required_text(self.occurrence_id, "occurrence_id")
        if type(self.gate_identity) is not RadarGateIdentity:
            raise TypeError("gate_identity must be a RadarGateIdentity")

    def to_dict(self) -> dict[str, object]:
        return {
            "occurrence_id": self.occurrence_id,
            "gate_identity": self.gate_identity.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class RadarProfile:
    """Passive behavior identity binding exact Gate order, not resolved evaluators.

    Validation is structural only; Gate requirements and resolution are deferred.
    """

    profile_id: str
    behavioral_revision: str
    configuration_schema: str
    gates: tuple[RadarGateOccurrence, ...]
    configuration: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = field(init=False, default=RADAR_PROFILE_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("profile_id", "behavioral_revision", "configuration_schema"):
            _required_text(getattr(self, name), name)
        if type(self.gates) not in (tuple, list):
            raise TypeError("gates must be an ordered tuple or list")
        gates = tuple(self.gates)
        if not gates:
            raise ValueError("profile must contain at least one Gate occurrence")
        if any(type(gate) is not RadarGateOccurrence for gate in gates):
            raise TypeError("gates must contain RadarGateOccurrence values")
        if len({gate.occurrence_id for gate in gates}) != len(gates):
            raise ValueError("occurrence IDs must be unique within a Profile")
        object.__setattr__(self, "gates", gates)
        object.__setattr__(self, "configuration", _freeze_mapping(self.configuration))
        object.__setattr__(self, "fingerprint", canonical_fingerprint(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "behavioral_revision": self.behavioral_revision,
            "configuration_schema": self.configuration_schema,
            "configuration": _serialize(self.configuration),
            "gates": [gate.to_dict() for gate in self.gates],
        }

    def to_dict(self) -> dict[str, object]:
        """Return detached JSON-compatible content, preserving exact Gate order."""
        return {**self._payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class RadarGateResult:
    """Descriptive occurrence result; reason_code is semantic, detail is diagnostic.

    Codes are Gate-owned stable ASCII identifiers, not free-form messages.
    Detail is optional and bounded to 1024 characters. No execution identity or
    result fingerprint is introduced before the input/context contract exists.
    """

    occurrence: RadarGateOccurrence
    disposition: RadarGateDisposition
    reason_code: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if type(self.occurrence) is not RadarGateOccurrence:
            raise TypeError("occurrence must be a RadarGateOccurrence")
        if type(self.disposition) is not RadarGateDisposition:
            raise TypeError("disposition must be a RadarGateDisposition")
        _required_text(self.reason_code, "reason_code")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", self.reason_code) is None:
            raise ValueError("reason_code must be a stable ASCII identifier")
        if self.detail is not None:
            if type(self.detail) is not str:
                raise TypeError("detail must be a string or None")
            if len(self.detail) > 1024:
                raise ValueError("detail must contain at most 1024 characters")


class RadarGate[ContextT](Protocol):
    """Narrow evaluator contract; the caller supplies the future context type.

    A resolved occurrence's evaluator returns its exact occurrence and definition
    identity. Context schema, fact acquisition and execution remain separate work.
    """

    @property
    def identity(self) -> RadarGateIdentity: ...

    def evaluate(self, context: ContextT) -> RadarGateResult: ...
