"""Immutable validation records for exact Evidence Artifact versions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)

EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION = "evidence_validation_record/v2"
EVIDENCE_VALIDATION_RECORD_REFERENCE_SCHEMA_VERSION = (
    "evidence_validation_record_reference/v2"
)

_VALIDATION_RECORD_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)


class EvidenceValidationConcern(StrEnum):
    """The complete Evidence Validation concern boundary."""

    IDENTITY = "identity"
    INTEGRITY = "integrity"
    PROVENANCE = "provenance"
    AUTHORITY = "authority"
    SCHEMA = "schema"
    TEMPORAL_COHERENCE = "temporal_coherence"
    FRESHNESS_CONTRACT = "freshness_contract"
    SOURCE_QUALITY = "source_quality"


class EvidenceValidationDisposition(StrEnum):
    """The complete set of fail-closed Evidence Validation dispositions."""

    PASSED = "PASSED"
    REJECTED = "REJECTED"
    UNABLE_TO_VALIDATE = "UNABLE_TO_VALIDATE"


@dataclass(frozen=True, slots=True)
class EvidenceValidationRecordReference:
    """Exact admission-facing reference to one validation record."""

    validation_record_id: str
    artifact_reference: EvidenceArtifactReference
    concern: EvidenceValidationConcern
    scope: str
    disposition: EvidenceValidationDisposition
    ruleset_id: str
    ruleset_version: str
    validation_record_fingerprint: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_VALIDATION_RECORD_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.concern) is not EvidenceValidationConcern:
            raise TypeError("concern must be an exact EvidenceValidationConcern")
        if type(self.disposition) is not EvidenceValidationDisposition:
            raise TypeError(
                "disposition must be an exact EvidenceValidationDisposition"
            )
        object.__setattr__(
            self,
            "validation_record_id",
            _visible_ascii(
                self.validation_record_id,
                "validation_record_id",
                256,
            ),
        )
        object.__setattr__(
            self,
            "artifact_reference",
            _copy_artifact_reference(self.artifact_reference),
        )
        object.__setattr__(self, "scope", _visible_ascii(self.scope, "scope", 256))
        object.__setattr__(
            self,
            "ruleset_id",
            _visible_ascii(self.ruleset_id, "ruleset_id", 256),
        )
        object.__setattr__(
            self,
            "ruleset_version",
            _visible_ascii(self.ruleset_version, "ruleset_version", 128),
        )
        object.__setattr__(
            self,
            "validation_record_fingerprint",
            _fingerprint(
                self.validation_record_fingerprint,
                "validation_record_fingerprint",
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
            "validation_record_id": self.validation_record_id,
            "artifact_reference": self.artifact_reference.to_dict(),
            "concern": self.concern.value,
            "scope": self.scope,
            "disposition": self.disposition.value,
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "validation_record_fingerprint": self.validation_record_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceValidationRecordReference(
            validation_record_id=self.validation_record_id,
            artifact_reference=self.artifact_reference,
            concern=self.concern,
            scope=self.scope,
            disposition=self.disposition,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.ruleset_version,
            validation_record_fingerprint=self.validation_record_fingerprint,
        )
        if self.schema_version != EVIDENCE_VALIDATION_RECORD_REFERENCE_SCHEMA_VERSION:
            raise ValueError(
                "evidence validation record reference schema_version is invalid"
            )
        retained_fingerprint = _fingerprint(
            self.fingerprint,
            "validation record reference fingerprint",
        )
        if retained_fingerprint != reconstructed.fingerprint:
            raise ValueError(
                "evidence validation record reference fingerprint does not "
                "match identity"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact validation-record-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class EvidenceValidationRecord:
    """One immutable validation conclusion for an exact artifact and scope."""

    validation_record_id: str
    artifact_reference: EvidenceArtifactReference
    concern: EvidenceValidationConcern
    scope: str
    disposition: EvidenceValidationDisposition
    validator_identity: EvidenceIdentityReference
    validator_capability_identity: EvidenceIdentityReference | None
    ruleset_id: str
    ruleset_version: str
    predecessor_validation_record_reference: EvidenceValidationRecordReference | None
    recorded_at: datetime
    effective_at: datetime
    findings: tuple[str, ...]
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceValidationRecord must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        validation_record_id: str,
        artifact_reference: EvidenceArtifactReference,
        concern: EvidenceValidationConcern,
        scope: str,
        disposition: EvidenceValidationDisposition,
        validator_identity: EvidenceIdentityReference,
        validator_capability_identity: EvidenceIdentityReference | None,
        ruleset_id: str,
        ruleset_version: str,
        predecessor_validation_record_reference: (
            EvidenceValidationRecordReference | None
        ),
        recorded_at: datetime,
        effective_at: datetime,
        findings: tuple[str, ...],
        seal: object,
    ) -> EvidenceValidationRecord:
        if seal is not _VALIDATION_RECORD_SEAL:
            raise TypeError("EvidenceValidationRecord construction is private")
        if type(concern) is not EvidenceValidationConcern:
            raise TypeError("concern must be an exact EvidenceValidationConcern")
        if type(disposition) is not EvidenceValidationDisposition:
            raise TypeError(
                "disposition must be an exact EvidenceValidationDisposition"
            )
        copied_artifact = _copy_artifact_reference(artifact_reference)
        copied_scope = _visible_ascii(scope, "scope", 256)
        predecessor_reference = _copy_optional_validation_reference(
            predecessor_validation_record_reference
        )
        if predecessor_reference is not None:
            if predecessor_reference.artifact_reference != copied_artifact:
                raise ValueError("validation predecessor must bind the same artifact")
            if predecessor_reference.concern is not concern:
                raise ValueError("validation predecessor must bind the same concern")
            if predecessor_reference.scope != copied_scope:
                raise ValueError("validation predecessor must bind the same scope")
            if predecessor_reference.validation_record_id == validation_record_id:
                raise ValueError("validation predecessor must be a distinct record")
        result = object.__new__(cls)
        values: dict[str, object] = {
            "validation_record_id": _visible_ascii(
                validation_record_id,
                "validation_record_id",
                256,
            ),
            "artifact_reference": copied_artifact,
            "concern": concern,
            "scope": copied_scope,
            "disposition": disposition,
            "validator_identity": _copy_identity_reference(validator_identity),
            "validator_capability_identity": _copy_optional_identity_reference(
                validator_capability_identity,
                "validator_capability_identity",
            ),
            "ruleset_id": _visible_ascii(ruleset_id, "ruleset_id", 256),
            "ruleset_version": _visible_ascii(
                ruleset_version,
                "ruleset_version",
                128,
            ),
            "predecessor_validation_record_reference": predecessor_reference,
            "recorded_at": _timestamp(recorded_at, "recorded_at"),
            "effective_at": _timestamp(effective_at, "effective_at"),
            "findings": _finding_tuple(findings),
            "schema_version": EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION,
        }
        for name, value in values.items():
            object.__setattr__(result, name, value)
        object.__setattr__(
            result,
            "fingerprint",
            canonical_fingerprint(result._fingerprint_payload()),
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection()

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "validation_record_id": self.validation_record_id,
            "artifact_reference": self.artifact_reference.to_dict(),
            "concern": self.concern.value,
            "scope": self.scope,
            "disposition": self.disposition.value,
            "validator_identity": self.validator_identity.to_dict(),
            "validator_capability_identity": (
                None
                if self.validator_capability_identity is None
                else self.validator_capability_identity.to_dict()
            ),
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "predecessor_validation_record_reference": (
                None
                if self.predecessor_validation_record_reference is None
                else self.predecessor_validation_record_reference.to_dict()
            ),
            "recorded_at": self.recorded_at.isoformat(),
            "effective_at": self.effective_at.isoformat(),
            "findings": list(self.findings),
        }

    def _validate(self) -> None:
        try:
            validation_record_id = self.validation_record_id
            artifact_reference = self.artifact_reference
            concern = self.concern
            scope = self.scope
            disposition = self.disposition
            validator_identity = self.validator_identity
            validator_capability_identity = self.validator_capability_identity
            ruleset_id = self.ruleset_id
            ruleset_version = self.ruleset_version
            predecessor_reference = self.predecessor_validation_record_reference
            recorded_at = self.recorded_at
            effective_at = self.effective_at
            findings = self.findings
            schema_version = self.schema_version
            fingerprint = self.fingerprint
        except AttributeError as error:
            raise ValueError(
                "evidence validation record retained state is incomplete"
            ) from error
        _visible_ascii(validation_record_id, "validation_record_id", 256)
        _copy_artifact_reference(artifact_reference)
        if type(concern) is not EvidenceValidationConcern:
            raise ValueError("evidence validation concern is invalid")
        _visible_ascii(scope, "scope", 256)
        if type(disposition) is not EvidenceValidationDisposition:
            raise ValueError("evidence validation disposition is invalid")
        _copy_identity_reference(validator_identity)
        _copy_optional_identity_reference(
            validator_capability_identity,
            "validator_capability_identity",
        )
        _visible_ascii(ruleset_id, "ruleset_id", 256)
        _visible_ascii(ruleset_version, "ruleset_version", 128)
        copied_predecessor = _copy_optional_validation_reference(predecessor_reference)
        if copied_predecessor is not None:
            if copied_predecessor.artifact_reference != self.artifact_reference:
                raise ValueError(
                    "validation predecessor must retain artifact correspondence"
                )
            if copied_predecessor.concern is not concern:
                raise ValueError(
                    "validation predecessor must retain concern correspondence"
                )
            if copied_predecessor.scope != scope:
                raise ValueError(
                    "validation predecessor must retain scope correspondence"
                )
            if copied_predecessor.validation_record_id == validation_record_id:
                raise ValueError("validation predecessor must remain distinct")
        _require_canonical_timestamp(recorded_at, "recorded_at")
        _require_canonical_timestamp(effective_at, "effective_at")
        _finding_tuple(findings, require_retained_tuple=True)
        if schema_version != EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION:
            raise ValueError("evidence validation record schema_version is invalid")
        retained_fingerprint = _fingerprint(fingerprint, "fingerprint")
        if retained_fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError(
                "evidence validation record fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical in-memory validation-record projection."""

        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}

    def reference(self) -> EvidenceValidationRecordReference:
        """Return an exact immutable reference for admission evaluation."""

        self._validate()
        return EvidenceValidationRecordReference(
            validation_record_id=self.validation_record_id,
            artifact_reference=self.artifact_reference,
            concern=self.concern,
            scope=self.scope,
            disposition=self.disposition,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.ruleset_version,
            validation_record_fingerprint=self.fingerprint,
        )


def create_evidence_validation_record(
    *,
    validation_record_id: str,
    artifact_reference: EvidenceArtifactReference,
    concern: EvidenceValidationConcern,
    scope: str,
    disposition: EvidenceValidationDisposition,
    validator_identity: EvidenceIdentityReference,
    ruleset_id: str,
    ruleset_version: str,
    recorded_at: datetime,
    effective_at: datetime,
    findings: tuple[str, ...],
    validator_capability_identity: EvidenceIdentityReference | None = None,
    predecessor: EvidenceValidationRecord | None = None,
) -> EvidenceValidationRecord:
    """Create one validation record without mutating or admitting its artifact."""

    predecessor_reference: EvidenceValidationRecordReference | None = None
    if predecessor is not None:
        if type(predecessor) is not EvidenceValidationRecord:
            raise TypeError("predecessor must be an EvidenceValidationRecord")
        predecessor._validate()
        predecessor_reference = predecessor.reference()
        if predecessor.recorded_at > _timestamp(recorded_at, "recorded_at"):
            raise ValueError("validation predecessor must already be recorded")
    return EvidenceValidationRecord._create(
        validation_record_id=validation_record_id,
        artifact_reference=artifact_reference,
        concern=concern,
        scope=scope,
        disposition=disposition,
        validator_identity=validator_identity,
        validator_capability_identity=validator_capability_identity,
        ruleset_id=ruleset_id,
        ruleset_version=ruleset_version,
        predecessor_validation_record_reference=predecessor_reference,
        recorded_at=recorded_at,
        effective_at=effective_at,
        findings=findings,
        seal=_VALIDATION_RECORD_SEAL,
    )


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


def _copy_identity_reference(value: object) -> EvidenceIdentityReference:
    if type(value) is not EvidenceIdentityReference:
        raise TypeError("validator_identity must be an EvidenceIdentityReference")
    reference = value
    reference._validate()
    return EvidenceIdentityReference(
        namespace=reference.namespace,
        identity_id=reference.identity_id,
        identity_version=reference.identity_version,
        identity_fingerprint=reference.identity_fingerprint,
    )


def _copy_optional_identity_reference(
    value: object,
    field_name: str,
) -> EvidenceIdentityReference | None:
    if value is None:
        return None
    if type(value) is not EvidenceIdentityReference:
        raise TypeError(f"{field_name} must be an EvidenceIdentityReference")
    return _copy_identity_reference(value)


def _copy_optional_validation_reference(
    value: object,
) -> EvidenceValidationRecordReference | None:
    if value is None:
        return None
    if type(value) is not EvidenceValidationRecordReference:
        raise TypeError(
            "predecessor_validation_record_reference must be an "
            "EvidenceValidationRecordReference"
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
    "EVIDENCE_VALIDATION_RECORD_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_VALIDATION_RECORD_SCHEMA_VERSION",
    "EvidenceValidationConcern",
    "EvidenceValidationDisposition",
    "EvidenceValidationRecord",
    "EvidenceValidationRecordReference",
    "create_evidence_validation_record",
]
