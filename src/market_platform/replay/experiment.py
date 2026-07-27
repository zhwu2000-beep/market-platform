"""Deterministic in-memory comparison of historical replay artifacts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from market_platform._fingerprint import canonical_fingerprint, canonical_float
from market_platform.replay.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    HistoricalReplayArtifact,
)
from market_platform.replay.models import ReplayStrategyIdentity
from market_platform.replay.provenance import (
    HistoricalReplayRunProvenance,
    SoftwareRevision,
)
from market_platform.state.models import MarketState
from market_platform.strategy.models import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
)

EXPERIMENT_SCHEMA_VERSION = "historical_replay_experiment/v1"
COMPARISON_POLICY_SCHEMA_VERSION = "historical_replay_comparison_policy/v1"
COMPARISON_SCHEMA_VERSION = "historical_replay_comparison/v1"

_STATE_FIELD_ORDER = (
    "directional_regime",
    "trend_regime",
    "momentum_regime",
    "volatility_regime",
    "structure_state",
    "quality",
    "missing_inputs",
)
_STATUS_ORDER = tuple(StrategyEvaluationStatus)


class HistoricalReplayComparisonIncompatibilityReason(StrEnum):
    """Stable reason codes for analytically incompatible replay artifacts."""

    SYMBOL_MISMATCH = "symbol_mismatch"
    INTERVAL_MISMATCH = "interval_mismatch"
    DATASET_CONTENT_FINGERPRINT_MISMATCH = "dataset_content_fingerprint_mismatch"
    EVALUATION_TIMESTAMPS_MISMATCH = "evaluation_timestamps_mismatch"
    OBSERVATION_FINGERPRINTS_MISMATCH = "observation_fingerprints_mismatch"


@dataclass(frozen=True, slots=True)
class HistoricalReplayComparisonMemberFacts:
    """Compatibility-relevant facts for one verified replay artifact."""

    artifact_schema_version: str
    symbol: str
    interval: str
    dataset_content_fingerprint: str
    provider: str
    evaluation_timestamps: tuple[datetime, ...]
    observation_fingerprints: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "artifact_schema_version",
            "symbol",
            "interval",
            "dataset_content_fingerprint",
            "provider",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if self.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported replay artifact schema version")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(
            self,
            "dataset_content_fingerprint",
            _fingerprint(
                self.dataset_content_fingerprint,
                "dataset_content_fingerprint",
            ),
        )
        timestamps = _timestamp_tuple(
            self.evaluation_timestamps,
            "evaluation_timestamps",
        )
        fingerprints = _text_tuple(
            self.observation_fingerprints,
            "observation_fingerprints",
        )
        fingerprints = tuple(
            _fingerprint(value, "observation_fingerprint")
            for value in fingerprints
        )
        if len(timestamps) != len(fingerprints):
            raise ValueError(
                "evaluation timestamps and observation fingerprints must align"
            )
        if not timestamps:
            raise ValueError("evaluation timestamps must not be empty")
        if any(
            timestamps[index] <= timestamps[index - 1]
            for index in range(1, len(timestamps))
        ):
            raise ValueError("evaluation timestamps must be strictly ordered")
        object.__setattr__(self, "evaluation_timestamps", timestamps)
        object.__setattr__(self, "observation_fingerprints", fingerprints)

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_schema_version": self.artifact_schema_version,
            "symbol": self.symbol,
            "interval": self.interval,
            "dataset_content_fingerprint": self.dataset_content_fingerprint,
            "provider": self.provider,
            "evaluation_timestamps": [
                value.isoformat() for value in self.evaluation_timestamps
            ],
            "observation_fingerprints": list(self.observation_fingerprints),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayComparisonCompatibility:
    """Deterministic compatibility verdict and the facts supporting it."""

    baseline: HistoricalReplayComparisonMemberFacts
    candidate: HistoricalReplayComparisonMemberFacts
    reasons: tuple[HistoricalReplayComparisonIncompatibilityReason, ...]
    compatible: bool = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, HistoricalReplayComparisonMemberFacts):
            raise TypeError("baseline must be comparison member facts")
        if not isinstance(self.candidate, HistoricalReplayComparisonMemberFacts):
            raise TypeError("candidate must be comparison member facts")
        reasons = _reason_tuple(self.reasons)
        expected_reasons = _canonical_incompatibility_reasons(
            self.baseline,
            self.candidate,
        )
        if reasons != expected_reasons:
            raise ValueError(
                "compatibility reasons must match baseline and candidate facts"
            )
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "compatible", not reasons)

    def to_dict(self) -> dict[str, object]:
        return {
            "compatible": self.compatible,
            "reasons": [reason.value for reason in self.reasons],
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayExecutionDifference:
    """One explicit baseline/candidate execution fact difference."""

    field: str
    baseline: object
    candidate: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "field", _required_text(self.field, "field"))
        object.__setattr__(self, "baseline", _freeze_value(self.baseline))
        object.__setattr__(self, "candidate", _freeze_value(self.candidate))
        if _typed_comparison_value(self.baseline) == _typed_comparison_value(
            self.candidate
        ):
            raise ValueError("execution difference values must differ")

    def to_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "baseline": _json_value(self.baseline),
            "candidate": _json_value(self.candidate),
        }


@dataclass(frozen=True, slots=True, order=True)
class HistoricalReplayStrategyMemberKey:
    """Stable strategy alignment key supporting duplicate strategy IDs."""

    strategy_id: str
    occurrence_index: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strategy_id",
            _required_text(self.strategy_id, "strategy_id"),
        )
        if (
            isinstance(self.occurrence_index, bool)
            or not isinstance(self.occurrence_index, int)
        ):
            raise TypeError("occurrence_index must be an integer")
        if self.occurrence_index < 0:
            raise ValueError("occurrence_index must not be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "occurrence_index": self.occurrence_index,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayStateFieldDifference:
    """One changed semantic MarketState field."""

    field: str
    baseline: str | tuple[str, ...]
    candidate: str | tuple[str, ...]

    def __post_init__(self) -> None:
        if self.field not in _STATE_FIELD_ORDER:
            raise ValueError(f"unsupported state field: {self.field}")
        object.__setattr__(
            self,
            "baseline",
            _state_field_value(self.baseline, "baseline"),
        )
        object.__setattr__(
            self,
            "candidate",
            _state_field_value(self.candidate, "candidate"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "baseline": _json_value(self.baseline),
            "candidate": _json_value(self.candidate),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayStateDifference:
    """Field-directed structural difference between two MarketState values."""

    baseline: MarketState
    candidate: MarketState
    field_differences: tuple[HistoricalReplayStateFieldDifference, ...]
    provenance_changed: bool
    evaluation_evidence_changed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, MarketState):
            raise TypeError("baseline must be a MarketState")
        if not isinstance(self.candidate, MarketState):
            raise TypeError("candidate must be a MarketState")
        differences = _typed_tuple(
            self.field_differences,
            HistoricalReplayStateFieldDifference,
            "field_differences",
        )
        field_names = tuple(item.field for item in differences)
        expected_order = tuple(
            name for name in _STATE_FIELD_ORDER if name in field_names
        )
        if field_names != expected_order or len(set(field_names)) != len(field_names):
            raise ValueError("state field differences must be unique and ordered")
        _require_bool(self.provenance_changed, "provenance_changed")
        _require_bool(
            self.evaluation_evidence_changed,
            "evaluation_evidence_changed",
        )
        if not (
            differences
            or self.provenance_changed
            or self.evaluation_evidence_changed
        ):
            raise ValueError("state difference must contain a change")
        baseline_values = _state_semantic_values(self.baseline)
        candidate_values = _state_semantic_values(self.candidate)
        expected_differences = tuple(
            HistoricalReplayStateFieldDifference(
                field=name,
                baseline=baseline_values[name],
                candidate=candidate_values[name],
            )
            for name in _STATE_FIELD_ORDER
            if baseline_values[name] != candidate_values[name]
        )
        expected_provenance_changed = _typed_comparison_value(
            self.baseline.provenance.to_dict()
        ) != _typed_comparison_value(self.candidate.provenance.to_dict())
        baseline_evidence = (
            self.baseline.evaluation_evidence.to_dict()
            if self.baseline.evaluation_evidence is not None
            else None
        )
        candidate_evidence = (
            self.candidate.evaluation_evidence.to_dict()
            if self.candidate.evaluation_evidence is not None
            else None
        )
        expected_evidence_changed = _typed_comparison_value(
            baseline_evidence
        ) != _typed_comparison_value(candidate_evidence)
        if differences != expected_differences:
            raise ValueError("state field differences must match stored states")
        if self.provenance_changed != expected_provenance_changed:
            raise ValueError("state provenance change must match stored states")
        if self.evaluation_evidence_changed != expected_evidence_changed:
            raise ValueError("state evidence change must match stored states")
        object.__setattr__(self, "field_differences", differences)

    @property
    def semantic_fields_changed(self) -> bool:
        return bool(self.field_differences)

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline": _state_payload(self.baseline),
            "candidate": _state_payload(self.candidate),
            "field_differences": [
                difference.to_dict() for difference in self.field_differences
            ],
            "provenance_changed": self.provenance_changed,
            "evaluation_evidence_changed": self.evaluation_evidence_changed,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayStrategyDifference:
    """One changed aligned strategy member at one replay timestamp."""

    member_key: HistoricalReplayStrategyMemberKey
    baseline_identity: ReplayStrategyIdentity | None
    candidate_identity: ReplayStrategyIdentity | None
    baseline_evaluation: StrategyEvaluation | None
    candidate_evaluation: StrategyEvaluation | None
    member_added: bool
    member_removed: bool
    identity_version_changed: bool
    configuration_fingerprint_changed: bool
    status_changed: bool
    rationale_changed: bool
    required_inputs_changed: bool
    missing_inputs_changed: bool
    evidence_changed: bool
    provenance_changed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.member_key, HistoricalReplayStrategyMemberKey):
            raise TypeError("member_key must be a strategy member key")
        _optional_type(
            self.baseline_identity,
            ReplayStrategyIdentity,
            "baseline_identity",
        )
        _optional_type(
            self.candidate_identity,
            ReplayStrategyIdentity,
            "candidate_identity",
        )
        _optional_type(
            self.baseline_evaluation,
            StrategyEvaluation,
            "baseline_evaluation",
        )
        _optional_type(
            self.candidate_evaluation,
            StrategyEvaluation,
            "candidate_evaluation",
        )
        for name in (
            "member_added",
            "member_removed",
            "identity_version_changed",
            "configuration_fingerprint_changed",
            "status_changed",
            "rationale_changed",
            "required_inputs_changed",
            "missing_inputs_changed",
            "evidence_changed",
            "provenance_changed",
        ):
            _require_bool(getattr(self, name), name)
        if self.member_added != (self.baseline_identity is None):
            raise ValueError("member_added must match absent baseline identity")
        if self.member_removed != (self.candidate_identity is None):
            raise ValueError("member_removed must match absent candidate identity")
        if self.member_added and self.member_removed:
            raise ValueError("strategy member cannot be both added and removed")
        if (self.baseline_identity is None) != (self.baseline_evaluation is None):
            raise ValueError("baseline identity and evaluation presence must match")
        if (self.candidate_identity is None) != (self.candidate_evaluation is None):
            raise ValueError("candidate identity and evaluation presence must match")
        if not any(
            getattr(self, name)
            for name in (
                "member_added",
                "member_removed",
                "identity_version_changed",
                "configuration_fingerprint_changed",
                "status_changed",
                "rationale_changed",
                "required_inputs_changed",
                "missing_inputs_changed",
                "evidence_changed",
                "provenance_changed",
            )
        ):
            raise ValueError("strategy difference must contain a change")
        expected_flags = {
            "member_added": self.baseline_identity is None,
            "member_removed": self.candidate_identity is None,
            "identity_version_changed": (
                self.baseline_identity is not None
                and self.candidate_identity is not None
                and self.baseline_identity.strategy_version
                != self.candidate_identity.strategy_version
            ),
            "configuration_fingerprint_changed": (
                self.baseline_identity is not None
                and self.candidate_identity is not None
                and self.baseline_identity.configuration_fingerprint
                != self.candidate_identity.configuration_fingerprint
            ),
            "status_changed": _evaluation_field_changed(
                self.baseline_evaluation,
                self.candidate_evaluation,
                "status",
            ),
            "rationale_changed": _evaluation_field_changed(
                self.baseline_evaluation,
                self.candidate_evaluation,
                "rationale",
            ),
            "required_inputs_changed": _evaluation_field_changed(
                self.baseline_evaluation,
                self.candidate_evaluation,
                "required_inputs",
            ),
            "missing_inputs_changed": _evaluation_field_changed(
                self.baseline_evaluation,
                self.candidate_evaluation,
                "missing_inputs",
            ),
            "evidence_changed": _evaluation_field_changed(
                self.baseline_evaluation,
                self.candidate_evaluation,
                "evidence",
            ),
            "provenance_changed": _evaluation_field_changed(
                self.baseline_evaluation,
                self.candidate_evaluation,
                "provenance",
            ),
        }
        for name, expected in expected_flags.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} must match stored strategy values")

    def to_dict(self) -> dict[str, object]:
        return {
            "member_key": self.member_key.to_dict(),
            "baseline_identity": _identity_payload(self.baseline_identity),
            "candidate_identity": _identity_payload(self.candidate_identity),
            "baseline_evaluation": _evaluation_payload(self.baseline_evaluation),
            "candidate_evaluation": _evaluation_payload(self.candidate_evaluation),
            "member_added": self.member_added,
            "member_removed": self.member_removed,
            "identity_version_changed": self.identity_version_changed,
            "configuration_fingerprint_changed": (
                self.configuration_fingerprint_changed
            ),
            "status_changed": self.status_changed,
            "rationale_changed": self.rationale_changed,
            "required_inputs_changed": self.required_inputs_changed,
            "missing_inputs_changed": self.missing_inputs_changed,
            "evidence_changed": self.evidence_changed,
            "provenance_changed": self.provenance_changed,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayChangedStep:
    """Changed structural output for one exactly aligned timestamp."""

    as_of: datetime
    state_difference: HistoricalReplayStateDifference | None
    strategy_differences: tuple[HistoricalReplayStrategyDifference, ...]
    structural_output_changed: bool = field(init=False, default=True)

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", _timestamp(self.as_of, "as_of"))
        _optional_type(
            self.state_difference,
            HistoricalReplayStateDifference,
            "state_difference",
        )
        differences = _typed_tuple(
            self.strategy_differences,
            HistoricalReplayStrategyDifference,
            "strategy_differences",
        )
        if self.state_difference is None and not differences:
            raise ValueError("changed step must contain state or strategy differences")
        member_keys = tuple(difference.member_key for difference in differences)
        if len(set(member_keys)) != len(member_keys):
            raise ValueError("strategy differences must use unique member keys")
        object.__setattr__(self, "strategy_differences", differences)

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat(),
            "state_difference": (
                self.state_difference.to_dict()
                if self.state_difference is not None
                else None
            ),
            "strategy_differences": [
                difference.to_dict() for difference in self.strategy_differences
            ],
            "structural_output_changed": self.structural_output_changed,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayNamedCount:
    """One deterministic named non-negative count."""

    name: str
    count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        _non_negative_int(self.count, "count")

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "count": self.count}


@dataclass(frozen=True, slots=True)
class HistoricalReplayStrategyMemberSummary:
    """Aggregate structural comparison for one aligned strategy member key."""

    member_key: HistoricalReplayStrategyMemberKey
    baseline_identity: ReplayStrategyIdentity | None
    candidate_identity: ReplayStrategyIdentity | None
    baseline_status_distribution: tuple[HistoricalReplayNamedCount, ...]
    candidate_status_distribution: tuple[HistoricalReplayNamedCount, ...]
    changed_step_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.member_key, HistoricalReplayStrategyMemberKey):
            raise TypeError("member_key must be a strategy member key")
        _optional_type(
            self.baseline_identity,
            ReplayStrategyIdentity,
            "baseline_identity",
        )
        _optional_type(
            self.candidate_identity,
            ReplayStrategyIdentity,
            "candidate_identity",
        )
        if self.baseline_identity is None and self.candidate_identity is None:
            raise ValueError("strategy member must exist in baseline or candidate")
        for identity, label in (
            (self.baseline_identity, "baseline_identity"),
            (self.candidate_identity, "candidate_identity"),
        ):
            if (
                identity is not None
                and identity.strategy_id != self.member_key.strategy_id
            ):
                raise ValueError(f"{label} strategy_id must match member key")
        for name in (
            "baseline_status_distribution",
            "candidate_status_distribution",
        ):
            values = _typed_tuple(
                getattr(self, name),
                HistoricalReplayNamedCount,
                name,
            )
            expected_names = tuple(status.value for status in _STATUS_ORDER)
            if tuple(item.name for item in values) != expected_names:
                raise ValueError(f"{name} must follow strategy status order")
            object.__setattr__(self, name, values)
        _non_negative_int(self.changed_step_count, "changed_step_count")

    def to_dict(self) -> dict[str, object]:
        return {
            "member_key": self.member_key.to_dict(),
            "baseline_identity": _identity_payload(self.baseline_identity),
            "candidate_identity": _identity_payload(self.candidate_identity),
            "baseline_status_distribution": [
                value.to_dict() for value in self.baseline_status_distribution
            ],
            "candidate_status_distribution": [
                value.to_dict() for value in self.candidate_status_distribution
            ],
            "changed_step_count": self.changed_step_count,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayComparisonSummary:
    """Complete aggregate counts for one compatible pairwise comparison."""

    total_aligned_steps: int
    unchanged_step_count: int
    changed_step_count: int
    state_semantic_change_count: int
    state_provenance_change_count: int
    state_evaluation_evidence_change_count: int
    state_field_change_counts: tuple[HistoricalReplayNamedCount, ...]
    total_strategy_member_comparisons: int
    status_change_count: int
    rationale_change_count: int
    required_input_change_count: int
    missing_input_change_count: int
    evidence_change_count: int
    strategy_provenance_change_count: int
    identity_version_change_count: int
    configuration_fingerprint_change_count: int
    added_strategy_member_count: int
    removed_strategy_member_count: int
    strategy_members: tuple[HistoricalReplayStrategyMemberSummary, ...]
    first_differing_as_of: datetime | None
    last_differing_as_of: datetime | None

    def __post_init__(self) -> None:
        count_fields = (
            "total_aligned_steps",
            "unchanged_step_count",
            "changed_step_count",
            "state_semantic_change_count",
            "state_provenance_change_count",
            "state_evaluation_evidence_change_count",
            "total_strategy_member_comparisons",
            "status_change_count",
            "rationale_change_count",
            "required_input_change_count",
            "missing_input_change_count",
            "evidence_change_count",
            "strategy_provenance_change_count",
            "identity_version_change_count",
            "configuration_fingerprint_change_count",
            "added_strategy_member_count",
            "removed_strategy_member_count",
        )
        for name in count_fields:
            _non_negative_int(getattr(self, name), name)
        if (
            self.unchanged_step_count + self.changed_step_count
            != self.total_aligned_steps
        ):
            raise ValueError("unchanged and changed steps must sum to aligned steps")
        for name in (
            "state_semantic_change_count",
            "state_provenance_change_count",
            "state_evaluation_evidence_change_count",
        ):
            if getattr(self, name) > self.total_aligned_steps:
                raise ValueError(f"{name} must not exceed aligned steps")
        field_counts = _typed_tuple(
            self.state_field_change_counts,
            HistoricalReplayNamedCount,
            "state_field_change_counts",
        )
        if tuple(item.name for item in field_counts) != _STATE_FIELD_ORDER:
            raise ValueError("state field counts must follow state field order")
        if any(item.count > self.total_aligned_steps for item in field_counts):
            raise ValueError("state field counts must not exceed aligned steps")
        members = _typed_tuple(
            self.strategy_members,
            HistoricalReplayStrategyMemberSummary,
            "strategy_members",
        )
        member_keys = tuple(member.member_key for member in members)
        if len(set(member_keys)) != len(member_keys):
            raise ValueError("strategy member summaries must use unique keys")
        for member in members:
            if member.changed_step_count > self.total_aligned_steps:
                raise ValueError("member changed steps must not exceed aligned steps")
            baseline_total = sum(
                value.count for value in member.baseline_status_distribution
            )
            candidate_total = sum(
                value.count for value in member.candidate_status_distribution
            )
            expected_baseline = (
                self.total_aligned_steps
                if member.baseline_identity is not None
                else 0
            )
            expected_candidate = (
                self.total_aligned_steps
                if member.candidate_identity is not None
                else 0
            )
            if baseline_total != expected_baseline:
                raise ValueError("baseline status distribution total is inconsistent")
            if candidate_total != expected_candidate:
                raise ValueError("candidate status distribution total is inconsistent")
        expected_member_comparisons = self.total_aligned_steps * len(members)
        if self.total_strategy_member_comparisons != expected_member_comparisons:
            raise ValueError("total strategy member comparisons is inconsistent")
        strategy_change_fields = (
            "status_change_count",
            "rationale_change_count",
            "required_input_change_count",
            "missing_input_change_count",
            "evidence_change_count",
            "strategy_provenance_change_count",
            "identity_version_change_count",
            "configuration_fingerprint_change_count",
        )
        if any(
            getattr(self, name) > self.total_strategy_member_comparisons
            for name in strategy_change_fields
        ):
            raise ValueError("strategy change counts must not exceed comparisons")
        expected_added = sum(
            member.baseline_identity is None
            and member.candidate_identity is not None
            for member in members
        )
        expected_removed = sum(
            member.baseline_identity is not None
            and member.candidate_identity is None
            for member in members
        )
        if self.added_strategy_member_count != expected_added:
            raise ValueError("added strategy member count is inconsistent")
        if self.removed_strategy_member_count != expected_removed:
            raise ValueError("removed strategy member count is inconsistent")
        first = _optional_timestamp(
            self.first_differing_as_of,
            "first_differing_as_of",
        )
        last = _optional_timestamp(
            self.last_differing_as_of,
            "last_differing_as_of",
        )
        if (first is None) != (last is None):
            raise ValueError("first and last differing timestamps must both be set")
        if self.changed_step_count == 0 and first is not None:
            raise ValueError("unchanged comparison must not have differing bounds")
        if self.changed_step_count > 0 and first is None:
            raise ValueError("changed comparison must have differing bounds")
        if first is not None and last is not None and first > last:
            raise ValueError("first differing timestamp must not follow last")
        object.__setattr__(self, "state_field_change_counts", field_counts)
        object.__setattr__(self, "strategy_members", members)
        object.__setattr__(self, "first_differing_as_of", first)
        object.__setattr__(self, "last_differing_as_of", last)

    def to_dict(self) -> dict[str, object]:
        return {
            "total_aligned_steps": self.total_aligned_steps,
            "unchanged_step_count": self.unchanged_step_count,
            "changed_step_count": self.changed_step_count,
            "state_semantic_change_count": self.state_semantic_change_count,
            "state_provenance_change_count": self.state_provenance_change_count,
            "state_evaluation_evidence_change_count": (
                self.state_evaluation_evidence_change_count
            ),
            "state_field_change_counts": [
                value.to_dict() for value in self.state_field_change_counts
            ],
            "total_strategy_member_comparisons": (
                self.total_strategy_member_comparisons
            ),
            "status_change_count": self.status_change_count,
            "rationale_change_count": self.rationale_change_count,
            "required_input_change_count": self.required_input_change_count,
            "missing_input_change_count": self.missing_input_change_count,
            "evidence_change_count": self.evidence_change_count,
            "strategy_provenance_change_count": (
                self.strategy_provenance_change_count
            ),
            "identity_version_change_count": self.identity_version_change_count,
            "configuration_fingerprint_change_count": (
                self.configuration_fingerprint_change_count
            ),
            "added_strategy_member_count": self.added_strategy_member_count,
            "removed_strategy_member_count": self.removed_strategy_member_count,
            "strategy_members": [
                member.to_dict() for member in self.strategy_members
            ],
            "first_differing_as_of": (
                self.first_differing_as_of.isoformat()
                if self.first_differing_as_of is not None
                else None
            ),
            "last_differing_as_of": (
                self.last_differing_as_of.isoformat()
                if self.last_differing_as_of is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayExperimentSpecification:
    """One baseline, ordered candidates, and fixed structural comparison policy."""

    baseline: HistoricalReplayArtifact
    candidates: tuple[HistoricalReplayArtifact, ...]
    software_revision: SoftwareRevision
    schema_version: str = field(init=False, default=EXPERIMENT_SCHEMA_VERSION)
    comparison_policy_version: str = field(
        init=False,
        default=COMPARISON_POLICY_SCHEMA_VERSION,
    )
    experiment_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, HistoricalReplayArtifact):
            raise TypeError("baseline must be a HistoricalReplayArtifact")
        candidates = _typed_tuple(
            self.candidates,
            HistoricalReplayArtifact,
            "candidates",
        )
        if not candidates:
            raise ValueError("candidates must not be empty")
        if not isinstance(self.software_revision, SoftwareRevision):
            raise TypeError("software_revision must be a SoftwareRevision")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(
            self,
            "experiment_fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": EXPERIMENT_SCHEMA_VERSION,
            "comparison_policy": _comparison_policy_payload(),
            "baseline": _artifact_identity_payload(self.baseline),
            "candidates": [
                {
                    "candidate_index": index,
                    **_artifact_identity_payload(candidate),
                }
                for index, candidate in enumerate(self.candidates)
            ],
            "software_revision": self.software_revision.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._fingerprint_payload(),
            "experiment_fingerprint": self.experiment_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayComparisonResult:
    """One deterministic baseline/candidate structural comparison."""

    experiment_fingerprint: str
    candidate_index: int
    baseline_run_fingerprint: str
    baseline_result_fingerprint: str
    candidate_run_fingerprint: str
    candidate_result_fingerprint: str
    compatibility: HistoricalReplayComparisonCompatibility
    execution_differences: tuple[HistoricalReplayExecutionDifference, ...]
    summary: HistoricalReplayComparisonSummary | None
    changed_steps: tuple[HistoricalReplayChangedStep, ...]
    schema_version: str = field(init=False, default=COMPARISON_SCHEMA_VERSION)
    comparison_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "experiment_fingerprint",
            "baseline_run_fingerprint",
            "baseline_result_fingerprint",
            "candidate_run_fingerprint",
            "candidate_result_fingerprint",
        ):
            object.__setattr__(self, name, _fingerprint(getattr(self, name), name))
        _non_negative_int(self.candidate_index, "candidate_index")
        if not isinstance(
            self.compatibility,
            HistoricalReplayComparisonCompatibility,
        ):
            raise TypeError("compatibility must be comparison compatibility")
        differences = _typed_tuple(
            self.execution_differences,
            HistoricalReplayExecutionDifference,
            "execution_differences",
        )
        difference_fields = tuple(difference.field for difference in differences)
        if len(set(difference_fields)) != len(difference_fields):
            raise ValueError("execution differences must use unique fields")
        changed_steps = _typed_tuple(
            self.changed_steps,
            HistoricalReplayChangedStep,
            "changed_steps",
        )
        if self.compatibility.compatible:
            if not isinstance(self.summary, HistoricalReplayComparisonSummary):
                raise TypeError("compatible comparison requires a summary")
            if len(changed_steps) != self.summary.changed_step_count:
                raise ValueError("changed step detail must match summary count")
            evaluation_timestamps = self.compatibility.baseline.evaluation_timestamps
            if self.summary.total_aligned_steps != len(evaluation_timestamps):
                raise ValueError("summary aligned steps must match compatibility facts")
            changed_as_of = tuple(step.as_of for step in changed_steps)
            if any(
                changed_as_of[index] <= changed_as_of[index - 1]
                for index in range(1, len(changed_as_of))
            ):
                raise ValueError("changed steps must be strictly ordered")
            evaluation_set = frozenset(evaluation_timestamps)
            if any(as_of not in evaluation_set for as_of in changed_as_of):
                raise ValueError("changed step timestamp must be aligned")
            _validate_summary_against_changed_steps(self.summary, changed_steps)
        else:
            if self.summary is not None or changed_steps:
                raise ValueError(
                    "incompatible comparison must not contain aligned detail"
                )
        object.__setattr__(self, "execution_differences", differences)
        object.__setattr__(self, "changed_steps", changed_steps)
        object.__setattr__(
            self,
            "comparison_fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": COMPARISON_SCHEMA_VERSION,
            "comparison_policy": _comparison_policy_payload(),
            "experiment_fingerprint": self.experiment_fingerprint,
            "candidate_index": self.candidate_index,
            "baseline": {
                "run_fingerprint": self.baseline_run_fingerprint,
                "result_fingerprint": self.baseline_result_fingerprint,
            },
            "candidate": {
                "run_fingerprint": self.candidate_run_fingerprint,
                "result_fingerprint": self.candidate_result_fingerprint,
            },
            "compatibility": self.compatibility.to_dict(),
            "execution_differences": [
                difference.to_dict() for difference in self.execution_differences
            ],
            "summary": self.summary.to_dict() if self.summary is not None else None,
            "changed_steps": [step.to_dict() for step in self.changed_steps],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._fingerprint_payload(),
            "comparison_fingerprint": self.comparison_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayExperiment:
    """Immutable aggregate of ordered baseline/candidate comparisons."""

    specification: HistoricalReplayExperimentSpecification
    comparisons: tuple[HistoricalReplayComparisonResult, ...]
    experiment_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(
            self.specification,
            HistoricalReplayExperimentSpecification,
        ):
            raise TypeError("specification must be an experiment specification")
        comparisons = _typed_tuple(
            self.comparisons,
            HistoricalReplayComparisonResult,
            "comparisons",
        )
        if len(comparisons) != len(self.specification.candidates):
            raise ValueError("comparison count must match candidate count")
        baseline = self.specification.baseline
        for index, (comparison, candidate) in enumerate(
            zip(comparisons, self.specification.candidates, strict=True)
        ):
            if comparison.candidate_index != index:
                raise ValueError("comparison candidate indices must be contiguous")
            if (
                comparison.experiment_fingerprint
                != self.specification.experiment_fingerprint
            ):
                raise ValueError("comparison belongs to another experiment")
            _validate_comparison_member_identity(
                comparison,
                baseline,
                candidate,
            )
            expected = _compare_pair(self.specification, candidate, index)
            if comparison != expected:
                raise ValueError(
                    "comparison does not match canonical experiment result"
                )
        object.__setattr__(self, "comparisons", comparisons)
        object.__setattr__(
            self,
            "experiment_fingerprint",
            self.specification.experiment_fingerprint,
        )


def create_historical_replay_experiment(
    specification: HistoricalReplayExperimentSpecification,
) -> HistoricalReplayExperiment:
    """Compare each loaded candidate with the loaded baseline without replay or I/O."""

    if not isinstance(
        specification,
        HistoricalReplayExperimentSpecification,
    ):
        raise TypeError("specification must be an experiment specification")
    comparisons = tuple(
        _compare_pair(specification, candidate, index)
        for index, candidate in enumerate(specification.candidates)
    )
    return HistoricalReplayExperiment(
        specification=specification,
        comparisons=comparisons,
    )


def compare_historical_replay_artifacts(
    baseline: HistoricalReplayArtifact,
    candidate: HistoricalReplayArtifact,
    *,
    software_revision: SoftwareRevision,
) -> HistoricalReplayComparisonResult:
    """Compare one verified pair through a one-candidate experiment identity."""

    specification = HistoricalReplayExperimentSpecification(
        baseline=baseline,
        candidates=(candidate,),
        software_revision=software_revision,
    )
    return create_historical_replay_experiment(specification).comparisons[0]


def _compare_pair(
    specification: HistoricalReplayExperimentSpecification,
    candidate: HistoricalReplayArtifact,
    candidate_index: int,
) -> HistoricalReplayComparisonResult:
    baseline = specification.baseline
    compatibility = _build_compatibility(baseline, candidate)
    execution_differences = _build_execution_differences(baseline, candidate)
    summary: HistoricalReplayComparisonSummary | None = None
    changed_steps: tuple[HistoricalReplayChangedStep, ...] = ()
    if compatibility.compatible:
        summary, changed_steps = _compare_compatible_results(baseline, candidate)
    return HistoricalReplayComparisonResult(
        experiment_fingerprint=specification.experiment_fingerprint,
        candidate_index=candidate_index,
        baseline_run_fingerprint=baseline.execution.run_fingerprint,
        baseline_result_fingerprint=baseline.result_fingerprint,
        candidate_run_fingerprint=candidate.execution.run_fingerprint,
        candidate_result_fingerprint=candidate.result_fingerprint,
        compatibility=compatibility,
        execution_differences=execution_differences,
        summary=summary,
        changed_steps=changed_steps,
    )


def _build_compatibility(
    baseline: HistoricalReplayArtifact,
    candidate: HistoricalReplayArtifact,
) -> HistoricalReplayComparisonCompatibility:
    baseline_facts = _member_facts(baseline)
    candidate_facts = _member_facts(candidate)
    reasons = _canonical_incompatibility_reasons(
        baseline_facts,
        candidate_facts,
    )
    return HistoricalReplayComparisonCompatibility(
        baseline=baseline_facts,
        candidate=candidate_facts,
        reasons=reasons,
    )


def _canonical_incompatibility_reasons(
    baseline_facts: HistoricalReplayComparisonMemberFacts,
    candidate_facts: HistoricalReplayComparisonMemberFacts,
) -> tuple[HistoricalReplayComparisonIncompatibilityReason, ...]:
    checks = (
        (
            baseline_facts.symbol == candidate_facts.symbol,
            HistoricalReplayComparisonIncompatibilityReason.SYMBOL_MISMATCH,
        ),
        (
            baseline_facts.interval == candidate_facts.interval,
            HistoricalReplayComparisonIncompatibilityReason.INTERVAL_MISMATCH,
        ),
        (
            baseline_facts.dataset_content_fingerprint
            == candidate_facts.dataset_content_fingerprint,
            HistoricalReplayComparisonIncompatibilityReason
            .DATASET_CONTENT_FINGERPRINT_MISMATCH,
        ),
        (
            baseline_facts.evaluation_timestamps
            == candidate_facts.evaluation_timestamps,
            HistoricalReplayComparisonIncompatibilityReason
            .EVALUATION_TIMESTAMPS_MISMATCH,
        ),
        (
            baseline_facts.observation_fingerprints
            == candidate_facts.observation_fingerprints,
            HistoricalReplayComparisonIncompatibilityReason
            .OBSERVATION_FINGERPRINTS_MISMATCH,
        ),
    )
    return tuple(
        reason
        for matched, reason in checks
        if not matched
    )


def _member_facts(
    artifact: HistoricalReplayArtifact,
) -> HistoricalReplayComparisonMemberFacts:
    result = artifact.execution.result
    provenance = artifact.execution.provenance
    return HistoricalReplayComparisonMemberFacts(
        artifact_schema_version=artifact.schema_version,
        symbol=result.symbol,
        interval=result.interval,
        dataset_content_fingerprint=provenance.dataset_content_fingerprint,
        provider=provenance.provider,
        evaluation_timestamps=tuple(step.as_of for step in result.steps),
        observation_fingerprints=tuple(
            step.observation_fingerprint for step in result.steps
        ),
    )


def _build_execution_differences(
    baseline: HistoricalReplayArtifact,
    candidate: HistoricalReplayArtifact,
) -> tuple[HistoricalReplayExecutionDifference, ...]:
    baseline_provenance = baseline.execution.provenance
    candidate_provenance = candidate.execution.provenance
    facts: tuple[tuple[str, object, object], ...] = (
        (
            "run_fingerprint",
            baseline.execution.run_fingerprint,
            candidate.execution.run_fingerprint,
        ),
        (
            "result_fingerprint",
            baseline.result_fingerprint,
            candidate.result_fingerprint,
        ),
        (
            "requested_specification",
            baseline_provenance.specification.to_dict(),
            candidate_provenance.specification.to_dict(),
        ),
        (
            "actual_context",
            _actual_context_payload(baseline_provenance),
            _actual_context_payload(candidate_provenance),
        ),
        (
            "actual_evaluation",
            _actual_evaluation_payload(baseline_provenance),
            _actual_evaluation_payload(candidate_provenance),
        ),
        (
            "dataset_content_fingerprint",
            baseline_provenance.dataset_content_fingerprint,
            candidate_provenance.dataset_content_fingerprint,
        ),
        ("provider", baseline_provenance.provider, candidate_provenance.provider),
        (
            "signal_derivation",
            baseline_provenance.signal_derivation.to_dict(),
            candidate_provenance.signal_derivation.to_dict(),
        ),
        (
            "structure_derivation",
            baseline_provenance.structure_derivation.to_dict(),
            candidate_provenance.structure_derivation.to_dict(),
        ),
        (
            "state_model",
            _state_model_identity_payload(baseline_provenance),
            _state_model_identity_payload(candidate_provenance),
        ),
        (
            "strategies",
            [identity.to_dict() for identity in baseline_provenance.strategies],
            [identity.to_dict() for identity in candidate_provenance.strategies],
        ),
        (
            "replay_software_revision",
            baseline_provenance.software_revision.to_dict(),
            candidate_provenance.software_revision.to_dict(),
        ),
    )
    return tuple(
        HistoricalReplayExecutionDifference(
            field=name,
            baseline=baseline_value,
            candidate=candidate_value,
        )
        for name, baseline_value, candidate_value in facts
        if baseline_value != candidate_value
    )


def _compare_compatible_results(
    baseline: HistoricalReplayArtifact,
    candidate: HistoricalReplayArtifact,
) -> tuple[
    HistoricalReplayComparisonSummary,
    tuple[HistoricalReplayChangedStep, ...],
]:
    baseline_result = baseline.execution.result
    candidate_result = candidate.execution.result
    alignment = _strategy_alignment(
        baseline_result.strategies,
        candidate_result.strategies,
    )
    member_statuses: dict[
        HistoricalReplayStrategyMemberKey,
        tuple[Counter[StrategyEvaluationStatus], Counter[StrategyEvaluationStatus]],
    ] = {
        entry[0]: (Counter(), Counter()) for entry in alignment
    }
    changed_steps: list[HistoricalReplayChangedStep] = []

    for baseline_step, candidate_step in zip(
        baseline_result.steps,
        candidate_result.steps,
        strict=True,
    ):
        state_difference = _compare_state(
            baseline_step.state,
            candidate_step.state,
        )

        strategy_differences: list[HistoricalReplayStrategyDifference] = []
        for key, baseline_member, candidate_member in alignment:
            baseline_index, baseline_identity = baseline_member
            candidate_index, candidate_identity = candidate_member
            baseline_evaluation = (
                baseline_step.strategy_result.evaluations[baseline_index]
                if baseline_index is not None
                else None
            )
            candidate_evaluation = (
                candidate_step.strategy_result.evaluations[candidate_index]
                if candidate_index is not None
                else None
            )
            baseline_statuses, candidate_statuses = member_statuses[key]
            if baseline_evaluation is not None:
                baseline_statuses[baseline_evaluation.status] += 1
            if candidate_evaluation is not None:
                candidate_statuses[candidate_evaluation.status] += 1
            strategy_difference = _compare_strategy_member(
                key,
                baseline_identity,
                candidate_identity,
                baseline_evaluation,
                candidate_evaluation,
            )
            if strategy_difference is not None:
                strategy_differences.append(strategy_difference)

        if state_difference is not None or strategy_differences:
            changed_steps.append(
                HistoricalReplayChangedStep(
                    as_of=baseline_step.as_of,
                    state_difference=state_difference,
                    strategy_differences=tuple(strategy_differences),
                )
            )

    changed_steps_tuple = tuple(changed_steps)
    counters, field_counts, member_change_counts = _derive_changed_detail_counts(
        changed_steps_tuple
    )
    baseline_keys = {
        key for key, baseline_member, _ in alignment if baseline_member[0] is not None
    }
    candidate_keys = {
        key for key, _, candidate_member in alignment if candidate_member[0] is not None
    }
    member_summaries = tuple(
        HistoricalReplayStrategyMemberSummary(
            member_key=key,
            baseline_identity=baseline_member[1],
            candidate_identity=candidate_member[1],
            baseline_status_distribution=_status_distribution(
                member_statuses[key][0]
            ),
            candidate_status_distribution=_status_distribution(
                member_statuses[key][1]
            ),
            changed_step_count=member_change_counts[key],
        )
        for key, baseline_member, candidate_member in alignment
    )
    step_count = baseline_result.step_count
    summary = HistoricalReplayComparisonSummary(
        total_aligned_steps=step_count,
        unchanged_step_count=step_count - len(changed_steps),
        changed_step_count=len(changed_steps),
        state_semantic_change_count=counters["state_semantic_change_count"],
        state_provenance_change_count=counters["state_provenance_change_count"],
        state_evaluation_evidence_change_count=counters[
            "state_evaluation_evidence_change_count"
        ],
        state_field_change_counts=tuple(
            HistoricalReplayNamedCount(name=name, count=field_counts[name])
            for name in _STATE_FIELD_ORDER
        ),
        total_strategy_member_comparisons=step_count * len(alignment),
        status_change_count=counters["status_change_count"],
        rationale_change_count=counters["rationale_change_count"],
        required_input_change_count=counters["required_input_change_count"],
        missing_input_change_count=counters["missing_input_change_count"],
        evidence_change_count=counters["evidence_change_count"],
        strategy_provenance_change_count=counters[
            "strategy_provenance_change_count"
        ],
        identity_version_change_count=counters["identity_version_change_count"],
        configuration_fingerprint_change_count=counters[
            "configuration_fingerprint_change_count"
        ],
        added_strategy_member_count=len(candidate_keys - baseline_keys),
        removed_strategy_member_count=len(baseline_keys - candidate_keys),
        strategy_members=member_summaries,
        first_differing_as_of=changed_steps[0].as_of if changed_steps else None,
        last_differing_as_of=changed_steps[-1].as_of if changed_steps else None,
    )
    return summary, changed_steps_tuple


def _compare_state(
    baseline: MarketState,
    candidate: MarketState,
) -> HistoricalReplayStateDifference | None:
    baseline_values = _state_semantic_values(baseline)
    candidate_values = _state_semantic_values(candidate)
    field_differences = tuple(
        HistoricalReplayStateFieldDifference(
            field=name,
            baseline=baseline_values[name],
            candidate=candidate_values[name],
        )
        for name in _STATE_FIELD_ORDER
        if baseline_values[name] != candidate_values[name]
    )
    provenance_changed = _typed_comparison_value(
        baseline.provenance.to_dict()
    ) != _typed_comparison_value(candidate.provenance.to_dict())
    baseline_evidence = (
        baseline.evaluation_evidence.to_dict()
        if baseline.evaluation_evidence is not None
        else None
    )
    candidate_evidence = (
        candidate.evaluation_evidence.to_dict()
        if candidate.evaluation_evidence is not None
        else None
    )
    evidence_changed = _typed_comparison_value(
        baseline_evidence
    ) != _typed_comparison_value(candidate_evidence)
    if not (field_differences or provenance_changed or evidence_changed):
        return None
    return HistoricalReplayStateDifference(
        baseline=baseline,
        candidate=candidate,
        field_differences=field_differences,
        provenance_changed=provenance_changed,
        evaluation_evidence_changed=evidence_changed,
    )


def _state_semantic_values(
    state: MarketState,
) -> dict[str, str | tuple[str, ...]]:
    return {
        "directional_regime": state.directional_regime.value,
        "trend_regime": state.trend_regime.value,
        "momentum_regime": state.momentum_regime.value,
        "volatility_regime": state.volatility_regime.value,
        "structure_state": state.structure_state.value,
        "quality": state.quality.value,
        "missing_inputs": state.missing_inputs,
    }


type _AlignedMember = tuple[int | None, ReplayStrategyIdentity | None]
type _AlignmentEntry = tuple[
    HistoricalReplayStrategyMemberKey,
    _AlignedMember,
    _AlignedMember,
]


def _strategy_alignment(
    baseline: tuple[ReplayStrategyIdentity, ...],
    candidate: tuple[ReplayStrategyIdentity, ...],
) -> tuple[_AlignmentEntry, ...]:
    baseline_members = _strategy_members(baseline)
    candidate_members = _strategy_members(candidate)
    baseline_by_key = {
        key: (index, identity) for key, index, identity in baseline_members
    }
    candidate_by_key = {
        key: (index, identity) for key, index, identity in candidate_members
    }
    ordered_keys = [key for key, _, _ in baseline_members]
    ordered_keys.extend(
        key for key, _, _ in candidate_members if key not in baseline_by_key
    )
    return tuple(
        (
            key,
            baseline_by_key.get(key, (None, None)),
            candidate_by_key.get(key, (None, None)),
        )
        for key in ordered_keys
    )


def _strategy_members(
    identities: tuple[ReplayStrategyIdentity, ...],
) -> tuple[tuple[HistoricalReplayStrategyMemberKey, int, ReplayStrategyIdentity], ...]:
    occurrences: Counter[str] = Counter()
    members = []
    for index, identity in enumerate(identities):
        occurrence = occurrences[identity.strategy_id]
        occurrences[identity.strategy_id] += 1
        members.append(
            (
                HistoricalReplayStrategyMemberKey(
                    strategy_id=identity.strategy_id,
                    occurrence_index=occurrence,
                ),
                index,
                identity,
            )
        )
    return tuple(members)


def _compare_strategy_member(
    key: HistoricalReplayStrategyMemberKey,
    baseline_identity: ReplayStrategyIdentity | None,
    candidate_identity: ReplayStrategyIdentity | None,
    baseline_evaluation: StrategyEvaluation | None,
    candidate_evaluation: StrategyEvaluation | None,
) -> HistoricalReplayStrategyDifference | None:
    member_added = baseline_identity is None
    member_removed = candidate_identity is None
    version_changed = (
        baseline_identity is not None
        and candidate_identity is not None
        and baseline_identity.strategy_version != candidate_identity.strategy_version
    )
    configuration_changed = (
        baseline_identity is not None
        and candidate_identity is not None
        and baseline_identity.configuration_fingerprint
        != candidate_identity.configuration_fingerprint
    )
    status_changed = _evaluation_field_changed(
        baseline_evaluation,
        candidate_evaluation,
        "status",
    )
    rationale_changed = _evaluation_field_changed(
        baseline_evaluation,
        candidate_evaluation,
        "rationale",
    )
    required_inputs_changed = _evaluation_field_changed(
        baseline_evaluation,
        candidate_evaluation,
        "required_inputs",
    )
    missing_inputs_changed = _evaluation_field_changed(
        baseline_evaluation,
        candidate_evaluation,
        "missing_inputs",
    )
    evidence_changed = _evaluation_field_changed(
        baseline_evaluation,
        candidate_evaluation,
        "evidence",
    )
    provenance_changed = _evaluation_field_changed(
        baseline_evaluation,
        candidate_evaluation,
        "provenance",
    )
    if not any(
        (
            member_added,
            member_removed,
            version_changed,
            configuration_changed,
            status_changed,
            rationale_changed,
            required_inputs_changed,
            missing_inputs_changed,
            evidence_changed,
            provenance_changed,
        )
    ):
        return None
    return HistoricalReplayStrategyDifference(
        member_key=key,
        baseline_identity=baseline_identity,
        candidate_identity=candidate_identity,
        baseline_evaluation=baseline_evaluation,
        candidate_evaluation=candidate_evaluation,
        member_added=member_added,
        member_removed=member_removed,
        identity_version_changed=version_changed,
        configuration_fingerprint_changed=configuration_changed,
        status_changed=status_changed,
        rationale_changed=rationale_changed,
        required_inputs_changed=required_inputs_changed,
        missing_inputs_changed=missing_inputs_changed,
        evidence_changed=evidence_changed,
        provenance_changed=provenance_changed,
    )


def _evaluation_field_changed(
    baseline: StrategyEvaluation | None,
    candidate: StrategyEvaluation | None,
    field_name: str,
) -> bool:
    if baseline is None or candidate is None:
        return baseline is not candidate
    if field_name == 'status':
        return baseline.status != candidate.status
    if field_name == 'rationale':
        return baseline.rationale != candidate.rationale
    if field_name == 'required_inputs':
        return baseline.required_inputs != candidate.required_inputs
    if field_name == 'missing_inputs':
        return baseline.missing_inputs != candidate.missing_inputs
    if field_name == 'evidence':
        return tuple(_evidence_payload(value) for value in baseline.evidence) != tuple(
            _evidence_payload(value) for value in candidate.evidence
        )
    if field_name == 'provenance':
        return _typed_comparison_value(
            baseline.provenance.to_dict()
        ) != _typed_comparison_value(candidate.provenance.to_dict())
    raise ValueError(f'unsupported evaluation comparison field: {field_name}')


def _count_strategy_difference(
    counters: Counter[str],
    difference: HistoricalReplayStrategyDifference,
) -> None:
    fields = (
        ("status_changed", "status_change_count"),
        ("rationale_changed", "rationale_change_count"),
        ("required_inputs_changed", "required_input_change_count"),
        ("missing_inputs_changed", "missing_input_change_count"),
        ("evidence_changed", "evidence_change_count"),
        ("provenance_changed", "strategy_provenance_change_count"),
        ("identity_version_changed", "identity_version_change_count"),
        (
            "configuration_fingerprint_changed",
            "configuration_fingerprint_change_count",
        ),
    )
    for attribute, counter_name in fields:
        if getattr(difference, attribute):
            counters[counter_name] += 1


def _derive_changed_detail_counts(
    changed_steps: tuple[HistoricalReplayChangedStep, ...],
) -> tuple[
    Counter[str],
    dict[str, int],
    Counter[HistoricalReplayStrategyMemberKey],
]:
    counters: Counter[str] = Counter()
    field_counts = dict.fromkeys(_STATE_FIELD_ORDER, 0)
    member_change_counts: Counter[HistoricalReplayStrategyMemberKey] = Counter()
    for step in changed_steps:
        state_difference = step.state_difference
        if state_difference is not None:
            if state_difference.semantic_fields_changed:
                counters["state_semantic_change_count"] += 1
                for state_field_difference in state_difference.field_differences:
                    field_counts[state_field_difference.field] += 1
            if state_difference.provenance_changed:
                counters["state_provenance_change_count"] += 1
            if state_difference.evaluation_evidence_changed:
                counters["state_evaluation_evidence_change_count"] += 1
        for strategy_difference in step.strategy_differences:
            member_change_counts[strategy_difference.member_key] += 1
            _count_strategy_difference(counters, strategy_difference)
    return counters, field_counts, member_change_counts


def _validate_summary_against_changed_steps(
    summary: HistoricalReplayComparisonSummary,
    changed_steps: tuple[HistoricalReplayChangedStep, ...],
) -> None:
    expected_first = changed_steps[0].as_of if changed_steps else None
    expected_last = changed_steps[-1].as_of if changed_steps else None
    if summary.first_differing_as_of != expected_first:
        raise ValueError("summary first differing timestamp is inconsistent")
    if summary.last_differing_as_of != expected_last:
        raise ValueError("summary last differing timestamp is inconsistent")
    counters, field_counts, member_change_counts = _derive_changed_detail_counts(
        changed_steps
    )
    expected_counts = {
        "state_semantic_change_count": counters["state_semantic_change_count"],
        "state_provenance_change_count": counters["state_provenance_change_count"],
        "state_evaluation_evidence_change_count": counters[
            "state_evaluation_evidence_change_count"
        ],
        "status_change_count": counters["status_change_count"],
        "rationale_change_count": counters["rationale_change_count"],
        "required_input_change_count": counters["required_input_change_count"],
        "missing_input_change_count": counters["missing_input_change_count"],
        "evidence_change_count": counters["evidence_change_count"],
        "strategy_provenance_change_count": counters[
            "strategy_provenance_change_count"
        ],
        "identity_version_change_count": counters[
            "identity_version_change_count"
        ],
        "configuration_fingerprint_change_count": counters[
            "configuration_fingerprint_change_count"
        ],
    }
    for name, expected in expected_counts.items():
        if getattr(summary, name) != expected:
            raise ValueError(f"summary {name} is inconsistent with changed detail")
    if {
        value.name: value.count for value in summary.state_field_change_counts
    } != field_counts:
        raise ValueError("summary state field counts are inconsistent with detail")
    summary_members = {
        member.member_key: member for member in summary.strategy_members
    }
    member_positions = {
        member.member_key: index
        for index, member in enumerate(summary.strategy_members)
    }
    for step in changed_steps:
        try:
            positions = tuple(
                member_positions[difference.member_key]
                for difference in step.strategy_differences
            )
        except KeyError as error:
            raise ValueError(
                "changed strategy member is absent from summary"
            ) from error
        if positions != tuple(sorted(positions)):
            raise ValueError("changed strategy members must follow summary order")
    for key, member in summary_members.items():
        if member.changed_step_count != member_change_counts[key]:
            raise ValueError("member changed step count is inconsistent with detail")


def _status_distribution(
    counts: Counter[StrategyEvaluationStatus],
) -> tuple[HistoricalReplayNamedCount, ...]:
    return tuple(
        HistoricalReplayNamedCount(name=status.value, count=counts[status])
        for status in _STATUS_ORDER
    )


def _comparison_policy_payload() -> dict[str, object]:
    return {
        "schema_version": COMPARISON_POLICY_SCHEMA_VERSION,
        "symbol_alignment": "exact",
        "interval_alignment": "exact",
        "dataset_content_fingerprint_alignment": "exact",
        "evaluation_timestamp_alignment": "exact_ordered",
        "observation_fingerprint_alignment": "exact_ordered",
        "pairing": "one_baseline_to_each_ordered_candidate",
        "strategy_alignment": "strategy_id_plus_occurrence_index",
        "detail_retention": "changed_steps_only_with_complete_aggregates",
        "semantics": "structural_output_difference_without_causal_attribution",
    }


def _artifact_identity_payload(
    artifact: HistoricalReplayArtifact,
) -> dict[str, str]:
    return {
        "run_fingerprint": artifact.execution.run_fingerprint,
        "result_fingerprint": artifact.result_fingerprint,
    }


def _actual_context_payload(
    provenance: HistoricalReplayRunProvenance,
) -> dict[str, object]:
    return {
        "start": provenance.context_start.isoformat(),
        "end": provenance.context_end.isoformat(),
        "row_count": provenance.context_row_count,
    }


def _actual_evaluation_payload(
    provenance: HistoricalReplayRunProvenance,
) -> dict[str, object]:
    return {
        "start": provenance.evaluation_start.isoformat(),
        "end": provenance.evaluation_end.isoformat(),
        "step_count": provenance.evaluation_step_count,
    }


def _state_model_identity_payload(
    provenance: HistoricalReplayRunProvenance,
) -> dict[str, object]:
    return {
        "model_id": provenance.state_model_id,
        "model_version": provenance.state_model_version,
        "configuration_fingerprint": provenance.state_model_configuration_fingerprint,
    }


def _state_payload(state: MarketState) -> dict[str, object]:
    return cast(dict[str, object], _typed_comparison_value(state.to_dict()))


def _evaluation_payload(
    evaluation: StrategyEvaluation | None,
) -> dict[str, object] | None:
    if evaluation is None:
        return None
    return {
        "symbol": evaluation.symbol,
        "interval": evaluation.interval,
        "as_of": evaluation.as_of.isoformat(),
        "provenance": _typed_comparison_value(evaluation.provenance.to_dict()),
        "status": evaluation.status.value,
        "rationale": evaluation.rationale,
        "required_inputs": list(evaluation.required_inputs),
        "missing_inputs": list(evaluation.missing_inputs),
        "evidence": [_evidence_payload(value) for value in evaluation.evidence],
    }


def _evidence_payload(evidence: StrategyEvidence) -> dict[str, object]:
    return {
        "source": evidence.source.value,
        "field": evidence.field,
        "observed_value": _typed_comparison_value(evidence.observed_value),
        "rationale": evidence.rationale,
        "observed_at": (
            evidence.observed_at.isoformat()
            if evidence.observed_at is not None
            else None
        ),
    }


def _typed_comparison_value(value: object) -> object:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, StrEnum):
        return {
            "type": "enum",
            "enum_type": type(value).__name__,
            "value": value.value,
        }
    if isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": canonical_float(value)}
    if isinstance(value, datetime):
        return {
            "type": "datetime",
            "value": _timestamp(value, "comparison value").isoformat(),
        }
    if isinstance(value, Mapping):
        projected: dict[str, object] = {}
        for raw_key in sorted(value):
            key = _required_text(raw_key, "comparison mapping key")
            if key in projected:
                raise ValueError("comparison mapping keys must be unique")
            projected[key] = _typed_comparison_value(value[raw_key])
        return {"type": "mapping", "value": projected}
    if isinstance(value, (tuple, list)):
        return {
            "type": "sequence",
            "value": [_typed_comparison_value(item) for item in value],
        }
    raise TypeError("unsupported typed comparison value")


def _identity_payload(
    identity: ReplayStrategyIdentity | None,
) -> dict[str, object] | None:
    return identity.to_dict() if identity is not None else None


def _validate_comparison_member_identity(
    comparison: HistoricalReplayComparisonResult,
    baseline: HistoricalReplayArtifact,
    candidate: HistoricalReplayArtifact,
) -> None:
    expected = (
        (
            comparison.baseline_run_fingerprint,
            baseline.execution.run_fingerprint,
            "baseline run fingerprint",
        ),
        (
            comparison.baseline_result_fingerprint,
            baseline.result_fingerprint,
            "baseline result fingerprint",
        ),
        (
            comparison.candidate_run_fingerprint,
            candidate.execution.run_fingerprint,
            "candidate run fingerprint",
        ),
        (
            comparison.candidate_result_fingerprint,
            candidate.result_fingerprint,
            "candidate result fingerprint",
        ),
    )
    for actual, wanted, label in expected:
        if actual != wanted:
            raise ValueError(f"comparison {label} does not match experiment")


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                _required_text(key, "mapping key"): _freeze_value(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        canonical_float(value)
        return value
    raise TypeError("comparison values must contain canonical JSON values")


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _json_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _json_value(item) for key, item in value.items()}


def _required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _fingerprint(value: object, field_name: str) -> str:
    normalized = _required_text(value, field_name)
    prefix, separator, digest = normalized.partition(":")
    if (
        prefix != "sha256"
        or separator != ":"
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{field_name} must be a sha256 fingerprint")
    return normalized


def _timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _optional_timestamp(value: object, field_name: str) -> datetime | None:
    return None if value is None else _timestamp(value, field_name)


def _timestamp_tuple(value: object, field_name: str) -> tuple[datetime, ...]:
    values = _container_tuple(value, field_name)
    return tuple(
        _timestamp(item, f"{field_name} element") for item in values
    )


def _text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    values = _container_tuple(value, field_name)
    return tuple(
        _required_text(item, f"{field_name} element") for item in values
    )


def _reason_tuple(
    value: object,
) -> tuple[HistoricalReplayComparisonIncompatibilityReason, ...]:
    reasons = _typed_tuple(
        value,
        HistoricalReplayComparisonIncompatibilityReason,
        "reasons",
    )
    expected = tuple(
        reason
        for reason in HistoricalReplayComparisonIncompatibilityReason
        if reason in reasons
    )
    if reasons != expected or len(set(reasons)) != len(reasons):
        raise ValueError("compatibility reasons must be unique and ordered")
    return reasons


def _container_tuple(value: object, field_name: str) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError(f"{field_name} must be a tuple or list")


def _typed_tuple[T](
    value: object,
    expected_type: type[T],
    field_name: str,
) -> tuple[T, ...]:
    values = _container_tuple(value, field_name)
    for item in values:
        if not isinstance(item, expected_type):
            raise TypeError(
                f"{field_name} elements must be {expected_type.__name__}"
            )
    return tuple(cast(T, item) for item in values)


def _optional_type[T](
    value: object,
    expected_type: type[T],
    field_name: str,
) -> None:
    if value is not None and not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be {expected_type.__name__} or None")


def _require_bool(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")


def _non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _state_field_value(
    value: object,
    field_name: str,
) -> str | tuple[str, ...]:
    if isinstance(value, str):
        return _required_text(value, field_name)
    return _text_tuple(value, field_name)


__all__ = [
    "COMPARISON_POLICY_SCHEMA_VERSION",
    "COMPARISON_SCHEMA_VERSION",
    "EXPERIMENT_SCHEMA_VERSION",
    "HistoricalReplayChangedStep",
    "HistoricalReplayComparisonCompatibility",
    "HistoricalReplayComparisonIncompatibilityReason",
    "HistoricalReplayComparisonMemberFacts",
    "HistoricalReplayComparisonResult",
    "HistoricalReplayComparisonSummary",
    "HistoricalReplayExecutionDifference",
    "HistoricalReplayExperiment",
    "HistoricalReplayExperimentSpecification",
    "HistoricalReplayNamedCount",
    "HistoricalReplayStateDifference",
    "HistoricalReplayStateFieldDifference",
    "HistoricalReplayStrategyDifference",
    "HistoricalReplayStrategyMemberKey",
    "HistoricalReplayStrategyMemberSummary",
    "compare_historical_replay_artifacts",
    "create_historical_replay_experiment",
]
