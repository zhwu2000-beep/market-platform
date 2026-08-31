"""Role-specific immutable references for Evidence identity and lineage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)

EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION = "evidence_identity_reference/v1"
EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION = "evidence_artifact_reference/v2"
EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION = "evidence_source_reference/v2"
EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION = "evidence_subject_reference/v1"
EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION = "evidence_contract_reference/v2"

_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_NAMESPACE_PATTERN = re.compile(
    r"[a-z][a-z0-9._-]{0,63}",
    flags=re.ASCII,
)


@dataclass(frozen=True, slots=True)
class EvidenceIdentityReference:
    """Generic versioned identity for producers and transformation steps."""

    namespace: str
    identity_id: str
    identity_version: str
    identity_fingerprint: str | None = None
    schema_version: str = field(
        init=False,
        default=EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", _namespace(self.namespace))
        object.__setattr__(
            self,
            "identity_id",
            _visible_ascii(self.identity_id, "identity_id", 256),
        )
        object.__setattr__(
            self,
            "identity_version",
            _visible_ascii(self.identity_version, "identity_version", 128),
        )
        object.__setattr__(
            self,
            "identity_fingerprint",
            _optional_fingerprint(
                self.identity_fingerprint,
                "identity_fingerprint",
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
            "namespace": self.namespace,
            "identity_id": self.identity_id,
            "identity_version": self.identity_version,
            "identity_fingerprint": self.identity_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceIdentityReference(
            namespace=self.namespace,
            identity_id=self.identity_id,
            identity_version=self.identity_version,
            identity_fingerprint=self.identity_fingerprint,
        )
        _require_correspondence(
            self.schema_version,
            EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION,
            self.fingerprint,
            reconstructed.fingerprint,
            "identity reference",
        )

    def to_dict(self) -> dict[str, object]:
        """Return the exact versioned identity-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceArtifactReference:
    """Stable reference to one exact immutable Evidence Artifact version."""

    artifact_id: str
    artifact_version: str
    artifact_fingerprint: str
    information_class: EvidenceInformationClass
    authority: EvidenceAuthority
    schema_version: str = field(
        init=False,
        default=EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_information_class(self.information_class)
        _require_authority(self.authority)
        object.__setattr__(
            self,
            "artifact_id",
            _visible_ascii(self.artifact_id, "artifact_id", 256),
        )
        object.__setattr__(
            self,
            "artifact_version",
            _visible_ascii(self.artifact_version, "artifact_version", 128),
        )
        object.__setattr__(
            self,
            "artifact_fingerprint",
            _fingerprint(self.artifact_fingerprint, "artifact_fingerprint"),
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_version": self.artifact_version,
            "artifact_fingerprint": self.artifact_fingerprint,
            "information_class": self.information_class.value,
            "authority": self.authority.value,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceArtifactReference(
            artifact_id=self.artifact_id,
            artifact_version=self.artifact_version,
            artifact_fingerprint=self.artifact_fingerprint,
            information_class=self.information_class,
            authority=self.authority,
        )
        _require_correspondence(
            self.schema_version,
            EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION,
            self.fingerprint,
            reconstructed.fingerprint,
            "artifact reference",
        )

    def to_dict(self) -> dict[str, object]:
        """Return the exact artifact-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceSourceReference:
    """Versioned identity of a source responsible for represented material."""

    namespace: str
    source_id: str
    source_version: str
    authority: EvidenceAuthority
    source_fingerprint: str | None = None
    schema_version: str = field(
        init=False,
        default=EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_authority(self.authority)
        object.__setattr__(self, "namespace", _namespace(self.namespace))
        object.__setattr__(
            self,
            "source_id",
            _visible_ascii(self.source_id, "source_id", 256),
        )
        object.__setattr__(
            self,
            "source_version",
            _visible_ascii(self.source_version, "source_version", 128),
        )
        object.__setattr__(
            self,
            "source_fingerprint",
            _optional_fingerprint(self.source_fingerprint, "source_fingerprint"),
        )
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "authority": self.authority.value,
            "source_fingerprint": self.source_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceSourceReference(
            namespace=self.namespace,
            source_id=self.source_id,
            source_version=self.source_version,
            authority=self.authority,
            source_fingerprint=self.source_fingerprint,
        )
        _require_correspondence(
            self.schema_version,
            EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION,
            self.fingerprint,
            reconstructed.fingerprint,
            "source reference",
        )

    def to_dict(self) -> dict[str, object]:
        """Return the exact source-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceSubjectReference:
    """Versioned canonical identity of one subject described by Evidence."""

    namespace: str
    subject_id: str
    subject_version: str
    subject_fingerprint: str | None = None
    schema_version: str = field(
        init=False,
        default=EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", _namespace(self.namespace))
        object.__setattr__(
            self,
            "subject_id",
            _visible_ascii(self.subject_id, "subject_id", 256),
        )
        object.__setattr__(
            self,
            "subject_version",
            _visible_ascii(self.subject_version, "subject_version", 128),
        )
        object.__setattr__(
            self,
            "subject_fingerprint",
            _optional_fingerprint(
                self.subject_fingerprint,
                "subject_fingerprint",
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
            "namespace": self.namespace,
            "subject_id": self.subject_id,
            "subject_version": self.subject_version,
            "subject_fingerprint": self.subject_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceSubjectReference(
            namespace=self.namespace,
            subject_id=self.subject_id,
            subject_version=self.subject_version,
            subject_fingerprint=self.subject_fingerprint,
        )
        _require_correspondence(
            self.schema_version,
            EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION,
            self.fingerprint,
            reconstructed.fingerprint,
            "subject reference",
        )

    def to_dict(self) -> dict[str, object]:
        """Return the exact subject-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceContractReference:
    """Versioned identity of the contract governing one Evidence Artifact."""

    namespace: str
    contract_id: str
    contract_version: str
    information_class: EvidenceInformationClass
    contract_fingerprint: str | None = None
    schema_version: str = field(
        init=False,
        default=EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_information_class(self.information_class)
        object.__setattr__(self, "namespace", _namespace(self.namespace))
        object.__setattr__(
            self,
            "contract_id",
            _visible_ascii(self.contract_id, "contract_id", 256),
        )
        object.__setattr__(
            self,
            "contract_version",
            _visible_ascii(self.contract_version, "contract_version", 128),
        )
        object.__setattr__(
            self,
            "contract_fingerprint",
            _optional_fingerprint(
                self.contract_fingerprint,
                "contract_fingerprint",
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
            "namespace": self.namespace,
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "information_class": self.information_class.value,
            "contract_fingerprint": self.contract_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceContractReference(
            namespace=self.namespace,
            contract_id=self.contract_id,
            contract_version=self.contract_version,
            information_class=self.information_class,
            contract_fingerprint=self.contract_fingerprint,
        )
        _require_correspondence(
            self.schema_version,
            EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION,
            self.fingerprint,
            reconstructed.fingerprint,
            "contract reference",
        )

    def to_dict(self) -> dict[str, object]:
        """Return the exact governing-contract projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def _namespace(value: object) -> str:
    if type(value) is not str or _NAMESPACE_PATTERN.fullmatch(value) is None:
        raise ValueError("namespace must match [a-z][a-z0-9._-]{0,63}")
    return value


def _require_information_class(value: object) -> EvidenceInformationClass:
    if type(value) is not EvidenceInformationClass:
        raise TypeError("information_class must be an exact EvidenceInformationClass")
    return value


def _require_authority(value: object) -> EvidenceAuthority:
    if type(value) is not EvidenceAuthority:
        raise TypeError("authority must be an exact EvidenceAuthority")
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


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


def _optional_fingerprint(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _fingerprint(value, field_name)


def _require_correspondence(
    schema_version: object,
    expected_schema_version: str,
    fingerprint: object,
    expected_fingerprint: str,
    subject: str,
) -> None:
    if schema_version != expected_schema_version:
        raise ValueError(f"{subject} schema_version is invalid")
    retained_fingerprint = _fingerprint(fingerprint, f"{subject} fingerprint")
    if retained_fingerprint != expected_fingerprint:
        raise ValueError(f"{subject} fingerprint does not match identity")


__all__ = [
    "EVIDENCE_ARTIFACT_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_CONTRACT_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_IDENTITY_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_SOURCE_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_SUBJECT_REFERENCE_SCHEMA_VERSION",
    "EvidenceArtifactReference",
    "EvidenceAuthority",
    "EvidenceContractReference",
    "EvidenceIdentityReference",
    "EvidenceInformationClass",
    "EvidenceSourceReference",
    "EvidenceSubjectReference",
]
