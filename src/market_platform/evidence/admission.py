"""Immutable Evidence admission decisions and compatibility-only evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.models import EvidenceArtifact
from market_platform.evidence.policy import (
    EvidenceAdmissionRuleSet,
    EvidenceAdmissionRuleSetReference,
    EvidenceValidationRequirement,
    _requirement_tuple,
)
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)
from market_platform.evidence.temporal import (
    EvidenceFreshnessEvaluationRecord,
    EvidenceFreshnessEvaluationReference,
)
from market_platform.evidence.validation import (
    EvidenceValidationConcern,
    EvidenceValidationDisposition,
    EvidenceValidationRecord,
    EvidenceValidationRecordReference,
)
from market_platform.evidence.validity import (
    EvidenceValidityEvent,
    EvidenceValidityReference,
    EvidenceValidityStatus,
)

EVIDENCE_ADMISSION_RECORD_REFERENCE_SCHEMA_VERSION = (
    "evidence_admission_record_reference/v1"
)
EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION = "evidence_admission_record/v3"
EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION = "evidence_admission_state/v3"

_ADMISSION_RECORD_SEAL = object()
_ADMISSION_STATE_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)


class EvidenceAdmissionDisposition(StrEnum):
    """The complete set of Evidence admission outcomes."""

    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class EvidenceAdmissionRecordReference:
    """Exact immutable reference to one admission decision."""

    admission_record_id: str
    artifact_reference: EvidenceArtifactReference
    admission_scope: str
    admission_ruleset_reference: EvidenceAdmissionRuleSetReference
    disposition: EvidenceAdmissionDisposition
    admission_record_fingerprint: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_ADMISSION_RECORD_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.disposition) is not EvidenceAdmissionDisposition:
            raise TypeError("disposition must be an exact EvidenceAdmissionDisposition")
        object.__setattr__(
            self,
            "admission_record_id",
            _visible_ascii(self.admission_record_id, "admission_record_id", 256),
        )
        object.__setattr__(
            self,
            "artifact_reference",
            _copy_artifact_reference(self.artifact_reference),
        )
        object.__setattr__(
            self,
            "admission_scope",
            _visible_ascii(self.admission_scope, "admission_scope", 256),
        )
        object.__setattr__(
            self,
            "admission_ruleset_reference",
            _copy_ruleset_reference(self.admission_ruleset_reference),
        )
        object.__setattr__(
            self,
            "admission_record_fingerprint",
            _fingerprint(
                self.admission_record_fingerprint,
                "admission_record_fingerprint",
            ),
        )
        if self.admission_ruleset_reference.admission_scope != self.admission_scope:
            raise ValueError("admission record reference ruleset scope mismatch")
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "admission_record_id": self.admission_record_id,
            "artifact_reference": self.artifact_reference.to_dict(),
            "admission_scope": self.admission_scope,
            "admission_ruleset_reference": self.admission_ruleset_reference.to_dict(),
            "disposition": self.disposition.value,
            "admission_record_fingerprint": self.admission_record_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceAdmissionRecordReference(
            admission_record_id=self.admission_record_id,
            artifact_reference=self.artifact_reference,
            admission_scope=self.admission_scope,
            admission_ruleset_reference=self.admission_ruleset_reference,
            disposition=self.disposition,
            admission_record_fingerprint=self.admission_record_fingerprint,
        )
        if self.schema_version != EVIDENCE_ADMISSION_RECORD_REFERENCE_SCHEMA_VERSION:
            raise ValueError("evidence admission record reference schema is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != reconstructed.fingerprint:
            raise ValueError(
                "evidence admission record reference fingerprint does not match"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact immutable admission-record reference."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class EvidenceAdmissionRecord:
    """One append-only admission decision for an exact artifact and ruleset."""

    admission_record_id: str
    artifact_reference: EvidenceArtifactReference
    admission_ruleset_reference: EvidenceAdmissionRuleSetReference
    admission_scope: str
    selected_validation_record_references: tuple[
        EvidenceValidationRecordReference,
        ...,
    ]
    admission_freshness_evaluation_reference: (
        EvidenceFreshnessEvaluationReference | None
    )
    deciding_actor_identity: EvidenceIdentityReference
    deciding_capability_identity: EvidenceIdentityReference | None
    predecessor_admission_record_reference: EvidenceAdmissionRecordReference | None
    disposition: EvidenceAdmissionDisposition
    recorded_at: datetime
    effective_at: datetime
    findings: tuple[str, ...]
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceAdmissionRecord must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        admission_record_id: str,
        artifact_reference: EvidenceArtifactReference,
        admission_ruleset_reference: EvidenceAdmissionRuleSetReference,
        selected_validation_record_references: tuple[
            EvidenceValidationRecordReference,
            ...,
        ],
        admission_freshness_evaluation_reference: (
            EvidenceFreshnessEvaluationReference | None
        ),
        deciding_actor_identity: EvidenceIdentityReference,
        deciding_capability_identity: EvidenceIdentityReference | None,
        predecessor_admission_record_reference: (
            EvidenceAdmissionRecordReference | None
        ),
        disposition: EvidenceAdmissionDisposition,
        recorded_at: datetime,
        effective_at: datetime,
        findings: tuple[str, ...],
        seal: object,
    ) -> EvidenceAdmissionRecord:
        if seal is not _ADMISSION_RECORD_SEAL:
            raise TypeError("EvidenceAdmissionRecord construction is private")
        if type(disposition) is not EvidenceAdmissionDisposition:
            raise TypeError("disposition must be an exact EvidenceAdmissionDisposition")
        artifact = _copy_artifact_reference(artifact_reference)
        ruleset_reference = _copy_ruleset_reference(admission_ruleset_reference)
        scope = ruleset_reference.admission_scope
        validations = _validation_reference_tuple(selected_validation_record_references)
        for reference in validations:
            if reference.artifact_reference != artifact:
                raise ValueError(
                    "selected validation references must bind the admitted artifact"
                )
            if reference.scope != scope:
                raise ValueError(
                    "selected validation references must bind the admission scope"
                )
        freshness = _copy_optional_freshness_reference(
            admission_freshness_evaluation_reference
        )
        if freshness is not None:
            if freshness.artifact_reference != artifact:
                raise ValueError(
                    "admission freshness reference must bind the admitted artifact"
                )
            if freshness.evaluation_scope != scope:
                raise ValueError(
                    "admission freshness reference must bind the admission scope"
                )
        recorded = _timestamp(recorded_at, "recorded_at")
        predecessor_reference = _copy_optional_admission_reference(
            predecessor_admission_record_reference
        )
        if predecessor_reference is not None:
            if predecessor_reference.artifact_reference != artifact:
                raise ValueError("admission predecessor must bind the same artifact")
            if predecessor_reference.admission_scope != scope:
                raise ValueError("admission predecessor must bind the same scope")
            if predecessor_reference.admission_record_id == admission_record_id:
                raise ValueError("admission predecessor must be a distinct record")
        instance = object.__new__(cls)
        values: dict[str, object] = {
            "admission_record_id": _visible_ascii(
                admission_record_id, "admission_record_id", 256
            ),
            "artifact_reference": artifact,
            "admission_ruleset_reference": ruleset_reference,
            "admission_scope": scope,
            "selected_validation_record_references": validations,
            "admission_freshness_evaluation_reference": freshness,
            "deciding_actor_identity": _copy_identity_reference(
                deciding_actor_identity, "deciding_actor_identity"
            ),
            "deciding_capability_identity": _copy_optional_identity_reference(
                deciding_capability_identity, "deciding_capability_identity"
            ),
            "predecessor_admission_record_reference": predecessor_reference,
            "disposition": disposition,
            "recorded_at": recorded,
            "effective_at": _timestamp(effective_at, "effective_at"),
            "findings": _finding_tuple(findings),
            "schema_version": EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION,
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

    @property
    def selected_freshness_evaluation_reference(
        self,
    ) -> EvidenceFreshnessEvaluationReference | None:
        """Compatibility alias for the historical admission-time reference."""

        return self.admission_freshness_evaluation_reference

    @property
    def admission_rule_id(self) -> str:
        return self.admission_ruleset_reference.ruleset_id

    @property
    def admission_rule_version(self) -> str:
        return self.admission_ruleset_reference.ruleset_version

    def _fingerprint_payload(self) -> dict[str, object]:
        freshness = self.admission_freshness_evaluation_reference
        return {
            "schema_version": self.schema_version,
            "admission_record_id": self.admission_record_id,
            "artifact_reference": self.artifact_reference.to_dict(),
            "admission_ruleset_reference": self.admission_ruleset_reference.to_dict(),
            "admission_scope": self.admission_scope,
            "selected_validation_record_references": [
                reference.to_dict()
                for reference in self.selected_validation_record_references
            ],
            "admission_freshness_evaluation_reference": (
                None if freshness is None else freshness.to_dict()
            ),
            "deciding_actor_identity": self.deciding_actor_identity.to_dict(),
            "deciding_capability_identity": (
                None
                if self.deciding_capability_identity is None
                else self.deciding_capability_identity.to_dict()
            ),
            "predecessor_admission_record_reference": (
                None
                if self.predecessor_admission_record_reference is None
                else self.predecessor_admission_record_reference.to_dict()
            ),
            "disposition": self.disposition.value,
            "recorded_at": self.recorded_at.isoformat(),
            "effective_at": self.effective_at.isoformat(),
            "findings": list(self.findings),
        }

    def _validate(self) -> None:
        _visible_ascii(self.admission_record_id, "admission_record_id", 256)
        artifact = _copy_artifact_reference(self.artifact_reference)
        ruleset = _copy_ruleset_reference(self.admission_ruleset_reference)
        if self.admission_scope != ruleset.admission_scope:
            raise ValueError("admission record ruleset scope correspondence is invalid")
        validations = _validation_reference_tuple(
            self.selected_validation_record_references,
            require_retained_tuple=True,
        )
        if any(
            reference.artifact_reference != artifact
            or reference.scope != self.admission_scope
            for reference in validations
        ):
            raise ValueError("admission validation reference correspondence is invalid")
        freshness = _copy_optional_freshness_reference(
            self.admission_freshness_evaluation_reference
        )
        if freshness is not None and (
            freshness.artifact_reference != artifact
            or freshness.evaluation_scope != self.admission_scope
        ):
            raise ValueError("admission freshness reference correspondence is invalid")
        _copy_identity_reference(
            self.deciding_actor_identity, "deciding_actor_identity"
        )
        _copy_optional_identity_reference(
            self.deciding_capability_identity, "deciding_capability_identity"
        )
        predecessor_reference = _copy_optional_admission_reference(
            self.predecessor_admission_record_reference
        )
        if predecessor_reference is not None:
            if predecessor_reference.artifact_reference != artifact:
                raise ValueError(
                    "admission predecessor must retain artifact correspondence"
                )
            if predecessor_reference.admission_scope != self.admission_scope:
                raise ValueError(
                    "admission predecessor must retain scope correspondence"
                )
            if predecessor_reference.admission_record_id == self.admission_record_id:
                raise ValueError("admission predecessor must remain distinct")
        _require_admission_disposition(self.disposition)
        _require_canonical_timestamp(self.recorded_at, "recorded_at")
        _require_canonical_timestamp(self.effective_at, "effective_at")
        _finding_tuple(self.findings, require_retained_tuple=True)
        if self.schema_version != EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION:
            raise ValueError("evidence admission record schema_version is invalid")
        if _fingerprint(self.fingerprint, "fingerprint") != canonical_fingerprint(
            self._fingerprint_payload()
        ):
            raise ValueError(
                "evidence admission record fingerprint does not match content"
            )

    def reference(self) -> EvidenceAdmissionRecordReference:
        self._validate()
        return EvidenceAdmissionRecordReference(
            admission_record_id=self.admission_record_id,
            artifact_reference=self.artifact_reference,
            admission_scope=self.admission_scope,
            admission_ruleset_reference=self.admission_ruleset_reference,
            disposition=self.disposition,
            admission_record_fingerprint=self.fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def _copy_artifact_reference(value: object) -> EvidenceArtifactReference:
    if type(value) is not EvidenceArtifactReference:
        raise TypeError("artifact_reference must be an EvidenceArtifactReference")
    value._validate()
    return EvidenceArtifactReference(
        artifact_id=value.artifact_id,
        artifact_version=value.artifact_version,
        artifact_fingerprint=value.artifact_fingerprint,
        information_class=value.information_class,
        authority=value.authority,
    )


def _copy_identity_reference(
    value: object,
    field_name: str,
) -> EvidenceIdentityReference:
    if type(value) is not EvidenceIdentityReference:
        raise TypeError(f"{field_name} must be an EvidenceIdentityReference")
    value._validate()
    return EvidenceIdentityReference(
        namespace=value.namespace,
        identity_id=value.identity_id,
        identity_version=value.identity_version,
        identity_fingerprint=value.identity_fingerprint,
    )


def _copy_optional_identity_reference(
    value: object,
    field_name: str,
) -> EvidenceIdentityReference | None:
    if value is None:
        return None
    return _copy_identity_reference(value, field_name)


def _copy_ruleset_reference(
    value: object,
) -> EvidenceAdmissionRuleSetReference:
    if type(value) is not EvidenceAdmissionRuleSetReference:
        raise TypeError(
            "admission_ruleset_reference must be an EvidenceAdmissionRuleSetReference"
        )
    value._validate()
    return EvidenceAdmissionRuleSetReference(
        ruleset_id=value.ruleset_id,
        ruleset_version=value.ruleset_version,
        admission_scope=value.admission_scope,
        ruleset_fingerprint=value.ruleset_fingerprint,
    )


def _copy_optional_ruleset_reference(
    value: object,
) -> EvidenceAdmissionRuleSetReference | None:
    if value is None:
        return None
    return _copy_ruleset_reference(value)


def _copy_validation_reference(
    value: object,
) -> EvidenceValidationRecordReference:
    if type(value) is not EvidenceValidationRecordReference:
        raise TypeError(
            "validation references must be EvidenceValidationRecordReference values"
        )
    value._validate()
    return EvidenceValidationRecordReference(
        validation_record_id=value.validation_record_id,
        artifact_reference=value.artifact_reference,
        concern=value.concern,
        scope=value.scope,
        disposition=value.disposition,
        ruleset_id=value.ruleset_id,
        ruleset_version=value.ruleset_version,
        validation_record_fingerprint=value.validation_record_fingerprint,
    )


def _copy_optional_freshness_reference(
    value: object,
) -> EvidenceFreshnessEvaluationReference | None:
    if value is None:
        return None
    if type(value) is not EvidenceFreshnessEvaluationReference:
        raise TypeError(
            "freshness reference must be an EvidenceFreshnessEvaluationReference"
        )
    value._validate()
    return EvidenceFreshnessEvaluationReference(
        artifact_reference=value.artifact_reference,
        freshness_rule_fingerprint=value.freshness_rule_fingerprint,
        evaluation_scope=value.evaluation_scope,
        evaluation_as_of=value.evaluation_as_of,
        result=value.result,
        evaluation_fingerprint=value.evaluation_fingerprint,
    )


def _copy_optional_admission_reference(
    value: object,
) -> EvidenceAdmissionRecordReference | None:
    if value is None:
        return None
    return _copy_admission_reference(value)


def _copy_admission_reference(
    value: object,
) -> EvidenceAdmissionRecordReference:
    if type(value) is not EvidenceAdmissionRecordReference:
        raise TypeError(
            "admission record references must be EvidenceAdmissionRecordReference "
            "values"
        )
    value._validate()
    return EvidenceAdmissionRecordReference(
        admission_record_id=value.admission_record_id,
        artifact_reference=value.artifact_reference,
        admission_scope=value.admission_scope,
        admission_ruleset_reference=value.admission_ruleset_reference,
        disposition=value.disposition,
        admission_record_fingerprint=value.admission_record_fingerprint,
    )


def _copy_optional_validity_reference(
    value: object,
) -> EvidenceValidityReference | None:
    if value is None:
        return None
    return _copy_validity_reference(value)


def _copy_validity_reference(
    value: object,
) -> EvidenceValidityReference:
    if type(value) is not EvidenceValidityReference:
        raise TypeError("validity references must be EvidenceValidityReference values")
    value._validate()
    return EvidenceValidityReference(
        validity_event_id=value.validity_event_id,
        artifact_reference=value.artifact_reference,
        status=value.status,
        scope=value.scope,
        recorded_at=value.recorded_at,
        effective_at=value.effective_at,
        validity_event_fingerprint=value.validity_event_fingerprint,
    )


def _validation_reference_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
    allow_duplicate_concerns: bool = False,
) -> tuple[EvidenceValidationRecordReference, ...]:
    if type(value) is not tuple:
        raise TypeError("validation references must be an exact tuple")
    references = tuple(
        _copy_validation_reference(item) for item in cast(tuple[object, ...], value)
    )
    if not allow_duplicate_concerns and len(
        {reference.concern for reference in references}
    ) != len(references):
        raise ValueError("validation references must not duplicate a concern")
    ordered = tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.concern.value,
                reference.validation_record_id,
                reference.validation_record_fingerprint,
            ),
        )
    )
    if require_retained_tuple and references != ordered:
        raise ValueError("validation reference ordering is not canonical")
    return ordered


def _admission_record_tuple(value: object) -> tuple[EvidenceAdmissionRecord, ...]:
    if type(value) is not tuple:
        raise TypeError("admission_records must be an exact tuple")
    records: list[EvidenceAdmissionRecord] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceAdmissionRecord:
            raise TypeError(
                "admission_records must contain EvidenceAdmissionRecord values"
            )
        item._validate()
        records.append(item)
    identities = tuple(record.admission_record_id for record in records)
    if len(set(identities)) != len(identities):
        raise ValueError("admission_records must not duplicate record identities")
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.artifact_reference.artifact_id,
                record.admission_scope,
                record.effective_at,
                record.recorded_at,
                record.admission_record_id,
            ),
        )
    )


def _validation_concern_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
    allow_empty: bool = False,
) -> tuple[EvidenceValidationConcern, ...]:
    if type(value) is not tuple:
        raise TypeError("required_validation_concerns must be an exact tuple")
    raw = cast(tuple[object, ...], value)
    if any(type(item) is not EvidenceValidationConcern for item in raw):
        raise TypeError(
            "required_validation_concerns must contain EvidenceValidationConcern"
        )
    concerns = cast(tuple[EvidenceValidationConcern, ...], raw)
    if not allow_empty and not concerns:
        raise ValueError("required_validation_concerns must not be empty")
    if len(set(concerns)) != len(concerns):
        raise ValueError("required_validation_concerns must not contain duplicates")
    ordered = tuple(sorted(concerns, key=lambda concern: concern.value))
    if require_retained_tuple and concerns != ordered:
        raise ValueError("required validation concern ordering is not canonical")
    return ordered


def _admission_reference_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
) -> tuple[EvidenceAdmissionRecordReference, ...]:
    if type(value) is not tuple:
        raise TypeError("admission predecessor references must be an exact tuple")
    references = tuple(
        _copy_admission_reference(item) for item in cast(tuple[object, ...], value)
    )
    if len(set(references)) != len(references):
        raise ValueError("admission predecessor references must be unique")
    ordered = tuple(sorted(references, key=lambda item: item.fingerprint))
    if require_retained_tuple and references != ordered:
        raise ValueError("admission predecessor reference ordering is not canonical")
    return ordered


def _validity_reference_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
) -> tuple[EvidenceValidityReference, ...]:
    if type(value) is not tuple:
        raise TypeError("validity predecessor references must be an exact tuple")
    references = tuple(
        _copy_validity_reference(item) for item in cast(tuple[object, ...], value)
    )
    if len(set(references)) != len(references):
        raise ValueError("validity predecessor references must be unique")
    ordered = tuple(sorted(references, key=lambda item: item.fingerprint))
    if require_retained_tuple and references != ordered:
        raise ValueError("validity predecessor reference ordering is not canonical")
    return ordered


def _require_admission_disposition(value: object) -> EvidenceAdmissionDisposition:
    if type(value) is not EvidenceAdmissionDisposition:
        raise TypeError("disposition must be an exact EvidenceAdmissionDisposition")
    return value


def _finding_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise TypeError("findings must be an exact tuple")
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
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


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
    "EVIDENCE_ADMISSION_RECORD_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_ADMISSION_RECORD_SCHEMA_VERSION",
    "EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION",
    "EvidenceAdmissionDisposition",
    "EvidenceAdmissionRecord",
    "EvidenceAdmissionRecordReference",
    "EvidenceAdmissionState",
    "create_evidence_admission_record",
    "evaluate_evidence_admission_state",
]


def create_evidence_admission_record(
    *,
    admission_record_id: str,
    artifact_reference: EvidenceArtifactReference,
    admission_ruleset: EvidenceAdmissionRuleSet,
    selected_validation_record_references: tuple[
        EvidenceValidationRecordReference,
        ...,
    ],
    admission_freshness_evaluation_reference: (
        EvidenceFreshnessEvaluationReference | None
    ),
    deciding_actor_identity: EvidenceIdentityReference,
    disposition: EvidenceAdmissionDisposition,
    recorded_at: datetime,
    effective_at: datetime,
    findings: tuple[str, ...],
    deciding_capability_identity: EvidenceIdentityReference | None = None,
    predecessor: EvidenceAdmissionRecord | None = None,
) -> EvidenceAdmissionRecord:
    """Create a policy-bound admission record without mutating prerequisites."""

    if type(admission_ruleset) is not EvidenceAdmissionRuleSet:
        raise TypeError("admission_ruleset must be an EvidenceAdmissionRuleSet")
    admission_ruleset._validate()
    validations = _validation_reference_tuple(selected_validation_record_references)
    freshness = _copy_optional_freshness_reference(
        admission_freshness_evaluation_reference
    )
    predecessor_reference: EvidenceAdmissionRecordReference | None = None
    if predecessor is not None:
        if type(predecessor) is not EvidenceAdmissionRecord:
            raise TypeError("predecessor must be an EvidenceAdmissionRecord")
        predecessor._validate()
        if predecessor.recorded_at > _timestamp(recorded_at, "recorded_at"):
            raise ValueError("admission predecessor must already be recorded")
        predecessor_reference = predecessor.reference()
    if disposition is EvidenceAdmissionDisposition.ADMITTED:
        selected_concerns = tuple(reference.concern for reference in validations)
        if selected_concerns != admission_ruleset.mandatory_validation_concerns:
            raise ValueError(
                "an admitted record must select the exact mandatory concern set"
            )
        if any(
            reference.disposition is not EvidenceValidationDisposition.PASSED
            for reference in validations
        ):
            raise ValueError("all mandatory validation records must pass")
        requirements_by_concern = {
            requirement.concern: requirement
            for requirement in admission_ruleset.mandatory_validation_requirements
        }
        if any(
            reference.scope != requirements_by_concern[reference.concern].scope
            or reference.ruleset_id
            != requirements_by_concern[reference.concern].ruleset_id
            or reference.ruleset_version
            != requirements_by_concern[reference.concern].ruleset_version
            for reference in validations
        ):
            raise ValueError(
                "mandatory validation records must match exact policy requirements"
            )
        if admission_ruleset.admission_freshness_required:
            if freshness is None:
                raise ValueError("required admission-time freshness is missing")
            rule = admission_ruleset.admission_freshness_rule
            assert rule is not None
            if (
                freshness.freshness_rule_fingerprint != rule.fingerprint
                or freshness.evaluation_scope != rule.evaluation_scope
            ):
                raise ValueError("admission-time freshness does not match policy")
            if not freshness.result:
                raise ValueError("required admission-time freshness must pass")
        elif freshness is not None:
            raise ValueError(
                "admission-time freshness must be absent when policy does not "
                "require it"
            )
    return EvidenceAdmissionRecord._create(
        admission_record_id=admission_record_id,
        artifact_reference=artifact_reference,
        admission_ruleset_reference=admission_ruleset.reference(),
        selected_validation_record_references=validations,
        admission_freshness_evaluation_reference=freshness,
        deciding_actor_identity=deciding_actor_identity,
        deciding_capability_identity=deciding_capability_identity,
        predecessor_admission_record_reference=predecessor_reference,
        disposition=disposition,
        recorded_at=recorded_at,
        effective_at=effective_at,
        findings=findings,
        seal=_ADMISSION_RECORD_SEAL,
    )


def evaluate_evidence_admission_state(
    *,
    artifact_reference: EvidenceArtifactReference,
    admission_scope: str,
    admission_records: tuple[EvidenceAdmissionRecord, ...],
    required_validation_concerns: tuple[EvidenceValidationConcern, ...],
    freshness_required: bool,
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> EvidenceAdmissionState:
    """Low-level reference inspection; never establishes final consumability."""

    artifact = _copy_artifact_reference(artifact_reference)
    scope = _visible_ascii(admission_scope, "admission_scope", 256)
    records = _admission_record_tuple(admission_records)
    concerns = _validation_concern_tuple(
        required_validation_concerns,
        allow_empty=True,
    )
    if type(freshness_required) is not bool:
        raise TypeError("freshness_required must be an exact bool")
    knowledge = _timestamp(knowledge_as_of, "knowledge_as_of")
    effective = _timestamp(effective_as_of, "effective_as_of")
    eligible = tuple(
        record
        for record in records
        if record.artifact_reference == artifact
        and record.admission_scope == scope
        and record.recorded_at <= knowledge
        and record.effective_at <= effective
    )
    selected: EvidenceAdmissionRecord | None = None
    disposition = EvidenceAdmissionDisposition.REJECTED
    finding = "No effective admission record exists for the as-of cutoffs."
    if eligible:
        precedence = max(
            (record.effective_at, record.recorded_at) for record in eligible
        )
        co_precedent = tuple(
            record
            for record in eligible
            if (record.effective_at, record.recorded_at) == precedence
        )
        if len(co_precedent) != 1:
            finding = "Conflicting co-precedent admission records fail closed."
        else:
            selected = co_precedent[0]
            disposition, finding = _inspect_embedded_references(
                selected,
                concerns,
                freshness_required,
            )
            if disposition is EvidenceAdmissionDisposition.ADMITTED:
                disposition = EvidenceAdmissionDisposition.REJECTED
                finding = (
                    "Reference-only inspection cannot establish an ADMITTED state."
                )
    return _create_evidence_admission_state_from_resolution(
        artifact=None,
        artifact_reference=artifact,
        admission_scope=scope,
        knowledge_as_of=knowledge,
        effective_as_of=effective,
        ruleset=None,
        disposition=disposition,
        selected_validations=(),
        admission_freshness=None,
        task_freshness=None,
        selected_admission=selected,
        selected_validity=None,
        validation_supersession_references=(),
        admission_predecessor_references=(),
        validity_predecessor_references=(),
        findings=(
            finding,
            "Reference-only evaluation cannot establish Evidence consumability.",
        ),
        legacy_concerns=concerns,
        legacy_freshness_required=freshness_required,
    )


def _inspect_embedded_references(
    record: EvidenceAdmissionRecord,
    concerns: tuple[EvidenceValidationConcern, ...],
    freshness_required: bool,
) -> tuple[EvidenceAdmissionDisposition, str]:
    if record.disposition is EvidenceAdmissionDisposition.REJECTED:
        return EvidenceAdmissionDisposition.REJECTED, "Admission record is rejected."
    references = {
        reference.concern: reference
        for reference in record.selected_validation_record_references
    }
    if any(
        concern not in references
        or references[concern].disposition is not EvidenceValidationDisposition.PASSED
        for concern in concerns
    ):
        return (
            EvidenceAdmissionDisposition.REJECTED,
            "Embedded validation references do not satisfy the requested concerns.",
        )
    freshness = record.admission_freshness_evaluation_reference
    if freshness_required and (freshness is None or not freshness.result):
        return (
            EvidenceAdmissionDisposition.REJECTED,
            "Embedded admission freshness reference does not pass.",
        )
    return (
        EvidenceAdmissionDisposition.ADMITTED,
        "Embedded references appear consistent at this low-level boundary.",
    )


def _create_evidence_admission_state_from_resolution(
    *,
    artifact: EvidenceArtifact | None,
    artifact_reference: EvidenceArtifactReference | None = None,
    admission_scope: str,
    knowledge_as_of: datetime,
    effective_as_of: datetime,
    ruleset: EvidenceAdmissionRuleSet | None,
    disposition: EvidenceAdmissionDisposition,
    selected_validations: tuple[EvidenceValidationRecord, ...],
    admission_freshness: EvidenceFreshnessEvaluationRecord | None,
    task_freshness: EvidenceFreshnessEvaluationRecord | None,
    selected_admission: EvidenceAdmissionRecord | None,
    selected_validity: EvidenceValidityEvent | None,
    validation_supersession_references: tuple[
        EvidenceValidationRecordReference,
        ...,
    ],
    admission_predecessor_references: tuple[
        EvidenceAdmissionRecordReference,
        ...,
    ],
    validity_predecessor_references: tuple[EvidenceValidityReference, ...],
    findings: tuple[str, ...],
    legacy_concerns: tuple[EvidenceValidationConcern, ...] = (),
    legacy_freshness_required: bool = False,
) -> EvidenceAdmissionState:
    """Create state from package-internal deterministic resolution."""

    if ruleset is None:
        if artifact is not None:
            raise ValueError("reference-only resolution must not receive an artifact")
        if artifact_reference is None:
            raise ValueError("reference-only resolution requires an artifact reference")
        resolved_artifact_reference = _copy_artifact_reference(artifact_reference)
        concerns = legacy_concerns
        requirements: tuple[EvidenceValidationRequirement, ...] = ()
        admission_freshness_required = legacy_freshness_required
        task_freshness_required = False
        active_validity_required = False
        ruleset_reference = None
        admission_freshness_rule_fingerprint = None
        task_freshness_rule_fingerprint = None
    else:
        if type(artifact) is not EvidenceArtifact:
            raise TypeError("full record resolution requires an EvidenceArtifact")
        artifact._validate()
        resolved_artifact_reference = artifact.reference()
        if artifact_reference is not None:
            raise ValueError(
                "full record resolution derives rather than accepts artifact_reference"
            )
        ruleset._validate()
        concerns = ruleset.mandatory_validation_concerns
        requirements = ruleset.mandatory_validation_requirements
        admission_freshness_required = ruleset.admission_freshness_required
        task_freshness_required = ruleset.task_freshness_required
        active_validity_required = ruleset.active_validity_required
        ruleset_reference = ruleset.reference()
        admission_freshness_rule_fingerprint = (
            None
            if ruleset.admission_freshness_rule is None
            else ruleset.admission_freshness_rule.fingerprint
        )
        task_freshness_rule_fingerprint = (
            None
            if ruleset.task_freshness_rule is None
            else ruleset.task_freshness_rule.fingerprint
        )
    validation_references: list[EvidenceValidationRecordReference] = []
    for record in selected_validations:
        if type(record) is not EvidenceValidationRecord:
            raise TypeError(
                "selected_validations must contain EvidenceValidationRecord values"
            )
        record.to_dict()
        validation_references.append(record.reference())
    for freshness_record, field_name in (
        (admission_freshness, "admission_freshness"),
        (task_freshness, "task_freshness"),
    ):
        if freshness_record is not None:
            if type(freshness_record) is not EvidenceFreshnessEvaluationRecord:
                raise TypeError(
                    f"{field_name} must be an EvidenceFreshnessEvaluationRecord"
                )
            freshness_record.to_dict()
    if selected_admission is not None:
        if type(selected_admission) is not EvidenceAdmissionRecord:
            raise TypeError("selected_admission must be an EvidenceAdmissionRecord")
        selected_admission.to_dict()
    if selected_validity is not None:
        if type(selected_validity) is not EvidenceValidityEvent:
            raise TypeError("selected_validity must be an EvidenceValidityEvent")
        selected_validity.to_dict()
    return EvidenceAdmissionState._create(
        artifact_reference=resolved_artifact_reference,
        admission_scope=admission_scope,
        knowledge_as_of=knowledge_as_of,
        effective_as_of=effective_as_of,
        ruleset_reference=ruleset_reference,
        required_validation_concerns=concerns,
        required_validation_requirements=requirements,
        admission_freshness_required=admission_freshness_required,
        task_freshness_required=task_freshness_required,
        active_validity_required=active_validity_required,
        admission_freshness_rule_fingerprint=(admission_freshness_rule_fingerprint),
        task_freshness_rule_fingerprint=task_freshness_rule_fingerprint,
        disposition=disposition,
        selected_validation_record_references=tuple(validation_references),
        admission_freshness_evaluation_reference=(
            None if admission_freshness is None else admission_freshness.reference()
        ),
        task_freshness_evaluation_reference=(
            None if task_freshness is None else task_freshness.reference()
        ),
        selected_admission_record_reference=(
            None if selected_admission is None else selected_admission.reference()
        ),
        selected_validity_reference=(
            None if selected_validity is None else selected_validity.reference()
        ),
        resolved_validation_supersession_references=(
            validation_supersession_references
        ),
        resolved_admission_predecessor_references=(admission_predecessor_references),
        resolved_validity_predecessor_references=(validity_predecessor_references),
        findings=findings,
        seal=_ADMISSION_STATE_SEAL,
    )


@dataclass(frozen=True, slots=True, init=False)
class EvidenceAdmissionState:
    """Derived fail-closed result with exact resolved record provenance."""

    artifact_reference: EvidenceArtifactReference
    admission_scope: str
    knowledge_as_of: datetime
    effective_as_of: datetime
    ruleset_reference: EvidenceAdmissionRuleSetReference | None
    required_validation_concerns: tuple[EvidenceValidationConcern, ...]
    required_validation_requirements: tuple[EvidenceValidationRequirement, ...]
    admission_freshness_required: bool
    task_freshness_required: bool
    active_validity_required: bool
    admission_freshness_rule_fingerprint: str | None
    task_freshness_rule_fingerprint: str | None
    disposition: EvidenceAdmissionDisposition
    selected_validation_record_references: tuple[
        EvidenceValidationRecordReference,
        ...,
    ]
    admission_freshness_evaluation_reference: (
        EvidenceFreshnessEvaluationReference | None
    )
    task_freshness_evaluation_reference: EvidenceFreshnessEvaluationReference | None
    selected_admission_record_reference: EvidenceAdmissionRecordReference | None
    selected_validity_reference: EvidenceValidityReference | None
    resolved_validation_supersession_references: tuple[
        EvidenceValidationRecordReference,
        ...,
    ]
    resolved_admission_predecessor_references: tuple[
        EvidenceAdmissionRecordReference,
        ...,
    ]
    resolved_validity_predecessor_references: tuple[EvidenceValidityReference, ...]
    findings: tuple[str, ...]
    schema_version: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceAdmissionState must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        artifact_reference: EvidenceArtifactReference,
        admission_scope: str,
        knowledge_as_of: datetime,
        effective_as_of: datetime,
        ruleset_reference: EvidenceAdmissionRuleSetReference | None,
        required_validation_concerns: tuple[EvidenceValidationConcern, ...],
        required_validation_requirements: tuple[
            EvidenceValidationRequirement,
            ...,
        ],
        admission_freshness_required: bool,
        task_freshness_required: bool,
        active_validity_required: bool,
        admission_freshness_rule_fingerprint: str | None,
        task_freshness_rule_fingerprint: str | None,
        disposition: EvidenceAdmissionDisposition,
        selected_validation_record_references: tuple[
            EvidenceValidationRecordReference,
            ...,
        ],
        admission_freshness_evaluation_reference: (
            EvidenceFreshnessEvaluationReference | None
        ),
        task_freshness_evaluation_reference: (
            EvidenceFreshnessEvaluationReference | None
        ),
        selected_admission_record_reference: (EvidenceAdmissionRecordReference | None),
        selected_validity_reference: EvidenceValidityReference | None,
        resolved_validation_supersession_references: tuple[
            EvidenceValidationRecordReference,
            ...,
        ],
        resolved_admission_predecessor_references: tuple[
            EvidenceAdmissionRecordReference,
            ...,
        ],
        resolved_validity_predecessor_references: tuple[
            EvidenceValidityReference,
            ...,
        ],
        findings: tuple[str, ...],
        seal: object,
    ) -> EvidenceAdmissionState:
        if seal is not _ADMISSION_STATE_SEAL:
            raise TypeError("EvidenceAdmissionState construction is private")
        for flag_name, flag_value in (
            ("admission_freshness_required", admission_freshness_required),
            ("task_freshness_required", task_freshness_required),
            ("active_validity_required", active_validity_required),
        ):
            if type(flag_value) is not bool:
                raise TypeError(f"{flag_name} must be an exact bool")
        instance = object.__new__(cls)
        values: dict[str, object] = {
            "artifact_reference": _copy_artifact_reference(artifact_reference),
            "admission_scope": _visible_ascii(admission_scope, "admission_scope", 256),
            "knowledge_as_of": _timestamp(knowledge_as_of, "knowledge_as_of"),
            "effective_as_of": _timestamp(effective_as_of, "effective_as_of"),
            "ruleset_reference": _copy_optional_ruleset_reference(ruleset_reference),
            "required_validation_concerns": _validation_concern_tuple(
                required_validation_concerns,
                allow_empty=ruleset_reference is None,
            ),
            "required_validation_requirements": _requirement_tuple(
                required_validation_requirements,
                allow_empty=ruleset_reference is None,
            ),
            "admission_freshness_required": admission_freshness_required,
            "task_freshness_required": task_freshness_required,
            "active_validity_required": active_validity_required,
            "admission_freshness_rule_fingerprint": (
                None
                if admission_freshness_rule_fingerprint is None
                else _fingerprint(
                    admission_freshness_rule_fingerprint,
                    "admission_freshness_rule_fingerprint",
                )
            ),
            "task_freshness_rule_fingerprint": (
                None
                if task_freshness_rule_fingerprint is None
                else _fingerprint(
                    task_freshness_rule_fingerprint,
                    "task_freshness_rule_fingerprint",
                )
            ),
            "disposition": _require_admission_disposition(disposition),
            "selected_validation_record_references": _validation_reference_tuple(
                selected_validation_record_references
            ),
            "admission_freshness_evaluation_reference": (
                _copy_optional_freshness_reference(
                    admission_freshness_evaluation_reference
                )
            ),
            "task_freshness_evaluation_reference": (
                _copy_optional_freshness_reference(task_freshness_evaluation_reference)
            ),
            "selected_admission_record_reference": (
                _copy_optional_admission_reference(selected_admission_record_reference)
            ),
            "selected_validity_reference": _copy_optional_validity_reference(
                selected_validity_reference
            ),
            "resolved_validation_supersession_references": (
                _validation_reference_tuple(
                    resolved_validation_supersession_references,
                    allow_duplicate_concerns=True,
                )
            ),
            "resolved_admission_predecessor_references": (
                _admission_reference_tuple(resolved_admission_predecessor_references)
            ),
            "resolved_validity_predecessor_references": (
                _validity_reference_tuple(resolved_validity_predecessor_references)
            ),
            "findings": _finding_tuple(findings),
            "schema_version": EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION,
        }
        for name, value in values.items():
            object.__setattr__(instance, name, value)
        instance._validate()
        if instance.disposition is EvidenceAdmissionDisposition.ADMITTED:
            failure = instance._consumability_failure()
            if failure is not None:
                raise ValueError(f"ADMITTED state is incomplete: {failure}")
        return instance

    @property
    def freshness_required(self) -> bool:
        return self.admission_freshness_required

    @property
    def selected_admission_record_id(self) -> str | None:
        reference = self.selected_admission_record_reference
        return None if reference is None else reference.admission_record_id

    @property
    def selected_admission_record_fingerprint(self) -> str | None:
        reference = self.selected_admission_record_reference
        return None if reference is None else reference.admission_record_fingerprint

    @property
    def is_admitted(self) -> bool:
        """Return the admission disposition, not a consumability guarantee."""

        return self.disposition is EvidenceAdmissionDisposition.ADMITTED

    @property
    def is_consumable(self) -> bool:
        """Return the invariant established by exact retained constituents."""

        return self._consumability_failure() is None

    def _consumability_failure(self) -> str | None:
        if self.disposition is not EvidenceAdmissionDisposition.ADMITTED:
            return "disposition is not ADMITTED"
        if self.ruleset_reference is None:
            return "no resolved admission ruleset"
        requirements = {
            requirement.concern: requirement
            for requirement in self.required_validation_requirements
        }
        validations = {
            reference.concern: reference
            for reference in self.selected_validation_record_references
        }
        if tuple(requirements) != self.required_validation_concerns:
            return "validation requirements do not match required concerns"
        if set(validations) != set(requirements):
            return "mandatory validation records are incomplete"
        for concern, requirement in requirements.items():
            reference = validations[concern]
            if reference.disposition is not EvidenceValidationDisposition.PASSED:
                return "a mandatory validation did not pass"
            if (
                reference.scope != requirement.scope
                or reference.ruleset_id != requirement.ruleset_id
                or reference.ruleset_version != requirement.ruleset_version
            ):
                return "a mandatory validation does not match policy"
        admission_freshness = self.admission_freshness_evaluation_reference
        if self.admission_freshness_required and (
            admission_freshness is None
            or not admission_freshness.result
            or admission_freshness.freshness_rule_fingerprint
            != self.admission_freshness_rule_fingerprint
        ):
            return "admission-time freshness is incomplete"
        task_freshness = self.task_freshness_evaluation_reference
        if self.task_freshness_required and (
            task_freshness is None
            or not task_freshness.result
            or task_freshness.freshness_rule_fingerprint
            != self.task_freshness_rule_fingerprint
        ):
            return "task-time freshness is incomplete"
        admission = self.selected_admission_record_reference
        if (
            admission is None
            or admission.disposition is not EvidenceAdmissionDisposition.ADMITTED
            or admission.admission_ruleset_reference != self.ruleset_reference
        ):
            return "admission record is incomplete"
        validity = self.selected_validity_reference
        if self.active_validity_required and (
            validity is None or validity.status is not EvidenceValidityStatus.ACTIVE
        ):
            return "ACTIVE validity is incomplete"
        return None

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_reference": self.artifact_reference.to_dict(),
            "admission_scope": self.admission_scope,
            "knowledge_as_of": self.knowledge_as_of.isoformat(),
            "effective_as_of": self.effective_as_of.isoformat(),
            "ruleset_reference": (
                None
                if self.ruleset_reference is None
                else self.ruleset_reference.to_dict()
            ),
            "required_validation_concerns": [
                concern.value for concern in self.required_validation_concerns
            ],
            "required_validation_requirements": [
                requirement.to_dict()
                for requirement in self.required_validation_requirements
            ],
            "admission_freshness_required": self.admission_freshness_required,
            "task_freshness_required": self.task_freshness_required,
            "active_validity_required": self.active_validity_required,
            "admission_freshness_rule_fingerprint": (
                self.admission_freshness_rule_fingerprint
            ),
            "task_freshness_rule_fingerprint": self.task_freshness_rule_fingerprint,
            "disposition": self.disposition.value,
            "selected_validation_record_references": [
                reference.to_dict()
                for reference in self.selected_validation_record_references
            ],
            "admission_freshness_evaluation_reference": (
                None
                if self.admission_freshness_evaluation_reference is None
                else self.admission_freshness_evaluation_reference.to_dict()
            ),
            "task_freshness_evaluation_reference": (
                None
                if self.task_freshness_evaluation_reference is None
                else self.task_freshness_evaluation_reference.to_dict()
            ),
            "selected_admission_record_reference": (
                None
                if self.selected_admission_record_reference is None
                else self.selected_admission_record_reference.to_dict()
            ),
            "selected_validity_reference": (
                None
                if self.selected_validity_reference is None
                else self.selected_validity_reference.to_dict()
            ),
            "resolved_validation_supersession_references": [
                reference.to_dict()
                for reference in self.resolved_validation_supersession_references
            ],
            "resolved_admission_predecessor_references": [
                reference.to_dict()
                for reference in self.resolved_admission_predecessor_references
            ],
            "resolved_validity_predecessor_references": [
                reference.to_dict()
                for reference in self.resolved_validity_predecessor_references
            ],
            "findings": list(self.findings),
        }

    def _validate(self) -> None:
        artifact = _copy_artifact_reference(self.artifact_reference)
        _visible_ascii(self.admission_scope, "admission_scope", 256)
        _require_canonical_timestamp(self.knowledge_as_of, "knowledge_as_of")
        _require_canonical_timestamp(self.effective_as_of, "effective_as_of")
        ruleset_reference = _copy_optional_ruleset_reference(self.ruleset_reference)
        if ruleset_reference is not None and (
            ruleset_reference.admission_scope != self.admission_scope
        ):
            raise ValueError("state ruleset must retain scope correspondence")
        for flag_name in (
            "admission_freshness_required",
            "task_freshness_required",
            "active_validity_required",
        ):
            if type(getattr(self, flag_name)) is not bool:
                raise ValueError(f"state {flag_name} is invalid")
        _require_admission_disposition(self.disposition)
        _validation_concern_tuple(
            self.required_validation_concerns,
            require_retained_tuple=True,
            allow_empty=ruleset_reference is None,
        )
        _requirement_tuple(
            self.required_validation_requirements,
            require_retained_tuple=True,
            allow_empty=ruleset_reference is None,
        )
        selected_validations = _validation_reference_tuple(
            self.selected_validation_record_references,
            require_retained_tuple=True,
        )
        if any(
            reference.artifact_reference != artifact
            or reference.scope != self.admission_scope
            for reference in selected_validations
        ):
            raise ValueError("state validation provenance correspondence is invalid")
        for freshness in (
            _copy_optional_freshness_reference(
                self.admission_freshness_evaluation_reference
            ),
            _copy_optional_freshness_reference(
                self.task_freshness_evaluation_reference
            ),
        ):
            if freshness is not None and (
                freshness.artifact_reference != artifact
                or freshness.evaluation_scope != self.admission_scope
            ):
                raise ValueError("state freshness provenance correspondence is invalid")
        selected_admission = _copy_optional_admission_reference(
            self.selected_admission_record_reference
        )
        if selected_admission is not None and (
            selected_admission.artifact_reference != artifact
            or selected_admission.admission_scope != self.admission_scope
        ):
            raise ValueError("state admission provenance correspondence is invalid")
        selected_validity = _copy_optional_validity_reference(
            self.selected_validity_reference
        )
        if selected_validity is not None and (
            selected_validity.artifact_reference != artifact
            or selected_validity.scope != self.admission_scope
        ):
            raise ValueError("state validity provenance correspondence is invalid")
        _validation_reference_tuple(
            self.resolved_validation_supersession_references,
            require_retained_tuple=True,
            allow_duplicate_concerns=True,
        )
        admission_lineage = _admission_reference_tuple(
            self.resolved_admission_predecessor_references,
            require_retained_tuple=True,
        )
        if any(
            reference.artifact_reference != artifact
            or reference.admission_scope != self.admission_scope
            for reference in admission_lineage
        ):
            raise ValueError("state admission predecessor correspondence is invalid")
        validity_lineage = _validity_reference_tuple(
            self.resolved_validity_predecessor_references,
            require_retained_tuple=True,
        )
        if any(
            reference.artifact_reference != artifact
            or reference.scope != self.admission_scope
            for reference in validity_lineage
        ):
            raise ValueError("state validity predecessor correspondence is invalid")
        for fingerprint_name in (
            "admission_freshness_rule_fingerprint",
            "task_freshness_rule_fingerprint",
        ):
            fingerprint = getattr(self, fingerprint_name)
            if fingerprint is not None:
                _fingerprint(fingerprint, fingerprint_name)
        _finding_tuple(self.findings, require_retained_tuple=True)
        if self.schema_version != EVIDENCE_ADMISSION_STATE_SCHEMA_VERSION:
            raise ValueError("evidence admission state schema_version is invalid")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return self._projection()
