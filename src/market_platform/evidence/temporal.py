"""Immutable as-of freshness evaluation contracts for Evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.models import EvidenceArtifact
from market_platform.evidence.references import EvidenceArtifactReference

EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION = "evidence_freshness_rule/v1"
EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION = (
    "evidence_freshness_evaluation_record/v2"
)
EVIDENCE_FRESHNESS_EVALUATION_REFERENCE_SCHEMA_VERSION = (
    "evidence_freshness_evaluation_reference/v1"
)

_FRESHNESS_EVALUATION_RECORD_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_TEMPORAL_ANCHOR_PATTERN = re.compile(
    r"[a-z][a-z0-9._-]{0,127}",
    flags=re.ASCII,
)


@dataclass(frozen=True, slots=True)
class EvidenceFreshnessRule:
    """Identity and declared temporal context for one freshness predicate."""

    rule_id: str
    rule_version: str
    declared_temporal_anchor: str
    evaluation_scope: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "rule_id", _visible_ascii(self.rule_id, "rule_id", 256)
        )
        object.__setattr__(
            self,
            "rule_version",
            _visible_ascii(self.rule_version, "rule_version", 128),
        )
        object.__setattr__(
            self,
            "declared_temporal_anchor",
            _temporal_anchor(self.declared_temporal_anchor),
        )
        object.__setattr__(
            self,
            "evaluation_scope",
            _visible_ascii(self.evaluation_scope, "evaluation_scope", 256),
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "declared_temporal_anchor": self.declared_temporal_anchor,
            "evaluation_scope": self.evaluation_scope,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceFreshnessRule(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            declared_temporal_anchor=self.declared_temporal_anchor,
            evaluation_scope=self.evaluation_scope,
        )
        if self.schema_version != EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION:
            raise ValueError("evidence freshness rule schema_version is invalid")
        retained_fingerprint = _fingerprint(self.fingerprint, "rule fingerprint")
        if retained_fingerprint != reconstructed.fingerprint:
            raise ValueError(
                "evidence freshness rule fingerprint does not match identity"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact freshness-rule identity projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceFreshnessEvaluationReference:
    """Exact admission-facing reference to one as-of freshness evaluation."""

    artifact_reference: EvidenceArtifactReference
    freshness_rule_fingerprint: str
    evaluation_scope: str
    evaluation_as_of: datetime
    result: bool
    evaluation_fingerprint: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_FRESHNESS_EVALUATION_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.result) is not bool:
            raise TypeError("result must be an exact bool")
        object.__setattr__(
            self,
            "artifact_reference",
            _copy_artifact_reference(self.artifact_reference),
        )
        object.__setattr__(
            self,
            "freshness_rule_fingerprint",
            _fingerprint(
                self.freshness_rule_fingerprint,
                "freshness_rule_fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "evaluation_scope",
            _visible_ascii(self.evaluation_scope, "evaluation_scope", 256),
        )
        object.__setattr__(
            self,
            "evaluation_as_of",
            _timestamp(self.evaluation_as_of, "evaluation_as_of"),
        )
        object.__setattr__(
            self,
            "evaluation_fingerprint",
            _fingerprint(
                self.evaluation_fingerprint,
                "evaluation_fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_reference": self.artifact_reference.to_dict(),
            "freshness_rule_fingerprint": self.freshness_rule_fingerprint,
            "evaluation_scope": self.evaluation_scope,
            "evaluation_as_of": self.evaluation_as_of.isoformat(),
            "result": self.result,
            "evaluation_fingerprint": self.evaluation_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceFreshnessEvaluationReference(
            artifact_reference=self.artifact_reference,
            freshness_rule_fingerprint=self.freshness_rule_fingerprint,
            evaluation_scope=self.evaluation_scope,
            evaluation_as_of=_require_canonical_timestamp(
                self.evaluation_as_of,
                "evaluation_as_of",
            ),
            result=self.result,
            evaluation_fingerprint=self.evaluation_fingerprint,
        )
        if (
            self.schema_version
            != EVIDENCE_FRESHNESS_EVALUATION_REFERENCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "evidence freshness evaluation reference schema_version is invalid"
            )
        retained_fingerprint = _fingerprint(
            self.fingerprint,
            "freshness evaluation reference fingerprint",
        )
        if retained_fingerprint != reconstructed.fingerprint:
            raise ValueError(
                "evidence freshness evaluation reference fingerprint does not "
                "match identity"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact freshness-evaluation-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class EvidenceFreshnessEvaluationRecord:
    """One immutable freshness predicate result at a specific as-of time."""

    artifact_reference: EvidenceArtifactReference
    freshness_rule: EvidenceFreshnessRule
    evaluation_as_of: datetime
    evaluated_temporal_values: tuple[tuple[str, datetime], ...]
    result: bool
    findings: tuple[str, ...]
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceFreshnessEvaluationRecord must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        artifact_reference: EvidenceArtifactReference,
        freshness_rule: EvidenceFreshnessRule,
        evaluation_as_of: datetime,
        evaluated_temporal_values: tuple[tuple[str, datetime], ...],
        result: bool,
        findings: tuple[str, ...],
        seal: object,
    ) -> EvidenceFreshnessEvaluationRecord:
        if seal is not _FRESHNESS_EVALUATION_RECORD_SEAL:
            raise TypeError("EvidenceFreshnessEvaluationRecord construction is private")
        if type(result) is not bool:
            raise TypeError("result must be an exact bool")
        copied_rule = _copy_freshness_rule(freshness_rule)
        temporal_values = _temporal_value_tuple(evaluated_temporal_values)
        if not _temporal_values_cover_anchor(
            copied_rule.declared_temporal_anchor,
            temporal_values,
        ):
            raise ValueError(
                "evaluated_temporal_values must include the declared temporal anchor"
            )
        instance = object.__new__(cls)
        values: dict[str, object] = {
            "artifact_reference": _copy_artifact_reference(artifact_reference),
            "freshness_rule": copied_rule,
            "evaluation_as_of": _timestamp(
                evaluation_as_of,
                "evaluation_as_of",
            ),
            "evaluated_temporal_values": temporal_values,
            "result": result,
            "findings": _finding_tuple(findings),
            "schema_version": EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION,
        }
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        object.__setattr__(
            instance,
            "fingerprint",
            canonical_fingerprint(instance._fingerprint_payload()),
        )
        instance._validate()
        return instance

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection()

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_reference": self.artifact_reference.to_dict(),
            "freshness_rule": self.freshness_rule.to_dict(),
            "evaluation_as_of": self.evaluation_as_of.isoformat(),
            "evaluated_temporal_values": [
                {"name": name, "value": value.isoformat()}
                for name, value in self.evaluated_temporal_values
            ],
            "result": self.result,
            "findings": list(self.findings),
        }

    def _validate(self) -> None:
        try:
            artifact_reference = self.artifact_reference
            freshness_rule = self.freshness_rule
            evaluation_as_of = self.evaluation_as_of
            evaluated_temporal_values = self.evaluated_temporal_values
            result = self.result
            findings = self.findings
            schema_version = self.schema_version
            fingerprint = self.fingerprint
        except AttributeError as error:
            raise ValueError(
                "evidence freshness evaluation retained state is incomplete"
            ) from error
        _copy_artifact_reference(artifact_reference)
        copied_rule = _copy_freshness_rule(freshness_rule)
        _require_canonical_timestamp(evaluation_as_of, "evaluation_as_of")
        temporal_values = _temporal_value_tuple(
            evaluated_temporal_values,
            require_retained_tuple=True,
        )
        if not _temporal_values_cover_anchor(
            copied_rule.declared_temporal_anchor,
            temporal_values,
        ):
            raise ValueError(
                "evaluated_temporal_values must retain the declared temporal anchor"
            )
        if type(result) is not bool:
            raise ValueError("evidence freshness result is invalid")
        _finding_tuple(findings, require_retained_tuple=True)
        if schema_version != EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION:
            raise ValueError("evidence freshness evaluation schema_version is invalid")
        retained_fingerprint = _fingerprint(fingerprint, "fingerprint")
        if retained_fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError(
                "evidence freshness evaluation fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical in-memory freshness-evaluation projection."""

        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}

    def reference(self) -> EvidenceFreshnessEvaluationReference:
        """Return an exact immutable reference for admission evaluation."""

        self._validate()
        return EvidenceFreshnessEvaluationReference(
            artifact_reference=self.artifact_reference,
            freshness_rule_fingerprint=self.freshness_rule.fingerprint,
            evaluation_scope=self.freshness_rule.evaluation_scope,
            evaluation_as_of=self.evaluation_as_of,
            result=self.result,
            evaluation_fingerprint=self.fingerprint,
        )


def create_evidence_freshness_evaluation_record(
    *,
    artifact: EvidenceArtifact,
    freshness_rule: EvidenceFreshnessRule,
    evaluation_as_of: datetime,
    result: bool,
    findings: tuple[str, ...],
) -> EvidenceFreshnessEvaluationRecord:
    """Derive and record one exact artifact-bound freshness evaluation."""

    if type(artifact) is not EvidenceArtifact:
        raise TypeError("artifact must be an EvidenceArtifact")
    artifact._validate()
    copied_rule = _copy_freshness_rule(freshness_rule)
    return EvidenceFreshnessEvaluationRecord._create(
        artifact_reference=artifact.reference(),
        freshness_rule=copied_rule,
        evaluation_as_of=evaluation_as_of,
        evaluated_temporal_values=_derive_artifact_temporal_values(
            artifact,
            copied_rule.declared_temporal_anchor,
        ),
        result=result,
        findings=findings,
        seal=_FRESHNESS_EVALUATION_RECORD_SEAL,
    )


def _derive_artifact_temporal_values(
    artifact: EvidenceArtifact,
    declared_temporal_anchor: str,
) -> tuple[tuple[str, datetime], ...]:
    """Return the exact retained artifact value for one declared anchor."""

    if type(artifact) is not EvidenceArtifact:
        raise TypeError("artifact must be an EvidenceArtifact")
    artifact._validate()
    anchor = _temporal_anchor(declared_temporal_anchor)
    temporal = artifact.temporal_identity
    if anchor == "observation_period":
        start = temporal.observation_period_start
        end = temporal.observation_period_end
        if start is None or end is None:
            raise ValueError(
                "artifact does not retain the required observation_period anchor"
            )
        return _temporal_value_tuple(
            (
                ("observation_period_start", start),
                ("observation_period_end", end),
            )
        )
    if anchor == "effective_interval":
        start = temporal.effective_from
        end = temporal.effective_until
        if start is None or end is None:
            raise ValueError(
                "artifact does not retain the required effective_interval anchor"
            )
        return _temporal_value_tuple(
            (
                ("effective_from", start),
                ("effective_until", end),
            )
        )
    values = {
        "observed_at": temporal.observed_at,
        "observation_period_start": temporal.observation_period_start,
        "observation_period_end": temporal.observation_period_end,
        "effective_from": temporal.effective_from,
        "effective_until": temporal.effective_until,
        "published_at": temporal.published_at,
        "platform_received_at": temporal.platform_received_at,
        "artifact_created_at": temporal.artifact_created_at,
    }
    if anchor not in values:
        raise ValueError(f"unsupported EvidenceArtifact temporal anchor: {anchor}")
    value = values[anchor]
    if value is None:
        raise ValueError(
            f"artifact does not retain the required {anchor} temporal anchor"
        )
    return ((anchor, value),)


def _copy_artifact_reference(value: object) -> EvidenceArtifactReference:
    if type(value) is not EvidenceArtifactReference:
        raise TypeError("artifact_reference must be an EvidenceArtifactReference")
    reference = value
    reference._validate()
    return EvidenceArtifactReference(
        artifact_id=reference.artifact_id,
        artifact_version=reference.artifact_version,
        artifact_fingerprint=reference.artifact_fingerprint,
        information_class=reference.information_class,
        authority=reference.authority,
    )


def _copy_freshness_rule(value: object) -> EvidenceFreshnessRule:
    if type(value) is not EvidenceFreshnessRule:
        raise TypeError("freshness_rule must be an EvidenceFreshnessRule")
    rule = value
    rule._validate()
    return EvidenceFreshnessRule(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        declared_temporal_anchor=rule.declared_temporal_anchor,
        evaluation_scope=rule.evaluation_scope,
    )


def _temporal_value_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
) -> tuple[tuple[str, datetime], ...]:
    if type(value) is not tuple:
        message = (
            "must be physically stored as a tuple"
            if require_retained_tuple
            else "must be an exact tuple"
        )
        raise TypeError(f"evaluated_temporal_values {message}")
    temporal_values = tuple(
        _temporal_value(item, index)
        for index, item in enumerate(cast(tuple[object, ...], value))
    )
    if not temporal_values:
        raise ValueError("evaluated_temporal_values requires at least one value")
    names = tuple(name for name, _ in temporal_values)
    if len(set(names)) != len(names):
        raise ValueError("evaluated_temporal_values must use unique names")
    ordered = tuple(sorted(temporal_values, key=lambda item: item[0]))
    if require_retained_tuple and temporal_values != ordered:
        raise ValueError("evaluated_temporal_values retained ordering is not canonical")
    return ordered


def _temporal_values_cover_anchor(
    anchor: str,
    temporal_values: tuple[tuple[str, datetime], ...],
) -> bool:
    names = {name for name, _ in temporal_values}
    if anchor == "observation_period":
        return names == {"observation_period_start", "observation_period_end"}
    if anchor == "effective_interval":
        return names == {"effective_from", "effective_until"}
    return anchor in names


def _temporal_value(value: object, index: int) -> tuple[str, datetime]:
    if type(value) is not tuple or len(value) != 2:
        raise TypeError(
            f"evaluated_temporal_values[{index}] must be an exact name/value tuple"
        )
    name, timestamp = cast(tuple[object, object], value)
    return _temporal_anchor(name), _timestamp(
        timestamp,
        f"evaluated_temporal_values[{index}][1]",
    )


def _finding_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        message = (
            "must be physically stored as a tuple"
            if require_retained_tuple
            else "must be an exact tuple"
        )
        raise TypeError(f"findings {message}")
    findings = tuple(
        _finding(item, index)
        for index, item in enumerate(cast(tuple[object, ...], value))
    )
    if not findings:
        raise ValueError("findings requires at least one finding")
    return findings


def _finding(value: object, index: int) -> str:
    if type(value) is not str:
        raise TypeError(f"findings[{index}] must be a string")
    if not value or value != value.strip():
        raise ValueError(f"findings[{index}] must be nonempty without edge whitespace")
    if len(value) > 2048:
        raise ValueError(f"findings[{index}] exceeds maximum length 2048")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError(f"findings[{index}] must not contain control characters")
    return value


def _temporal_anchor(value: object) -> str:
    if type(value) is not str or _TEMPORAL_ANCHOR_PATTERN.fullmatch(value) is None:
        raise ValueError("declared temporal anchors must match [a-z][a-z0-9._-]{0,127}")
    return value


def _visible_ascii(value: object, field_name: str, maximum_length: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > maximum_length:
        raise ValueError(f"{field_name} exceeds maximum length {maximum_length}")
    if any(not 0x21 <= ord(character) <= 0x7E for character in value):
        raise ValueError(f"{field_name} must contain visible ASCII without whitespace")
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be a datetime")
    timestamp = value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return timestamp.astimezone(UTC)


def _require_canonical_timestamp(value: object, field_name: str) -> datetime:
    canonical = _timestamp(value, field_name)
    retained = cast(datetime, value)
    if retained.tzinfo is not UTC or retained.isoformat() != canonical.isoformat():
        raise ValueError(f"{field_name} must retain canonical UTC state")
    return canonical


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


__all__ = [
    "EVIDENCE_FRESHNESS_EVALUATION_RECORD_SCHEMA_VERSION",
    "EVIDENCE_FRESHNESS_EVALUATION_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_FRESHNESS_RULE_SCHEMA_VERSION",
    "EvidenceFreshnessEvaluationRecord",
    "EvidenceFreshnessEvaluationReference",
    "EvidenceFreshnessRule",
    "create_evidence_freshness_evaluation_record",
]
