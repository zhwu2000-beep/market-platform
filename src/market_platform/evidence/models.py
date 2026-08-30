"""Immutable contracts for exact, provenance-bearing Evidence artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.authorization import (
    EvidenceContractAuthorization,
    _copy_contract_authorization,
    _resolve_governed_evidence_contract_authorization,
)
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceContractReference,
    EvidenceIdentityReference,
    EvidenceSourceReference,
    EvidenceSubjectReference,
)

EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION = "evidence_temporal_identity/v1"
EVIDENCE_PROVENANCE_SCHEMA_VERSION = "evidence_provenance/v1"
EVIDENCE_ARTIFACT_SCHEMA_VERSION = "evidence_artifact/v3"

_ARTIFACT_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class EvidenceTemporalIdentity:
    """Distinct source and artifact times without task-evaluation state."""

    platform_received_at: datetime
    artifact_created_at: datetime
    observed_at: datetime | None = None
    observation_period_start: datetime | None = None
    observation_period_end: datetime | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    published_at: datetime | None = None
    source_revision: str | None = None
    schema_version: str = field(
        init=False,
        default=EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        platform_received_at = _timestamp(
            self.platform_received_at,
            "platform_received_at",
        )
        artifact_created_at = _timestamp(
            self.artifact_created_at,
            "artifact_created_at",
        )
        if artifact_created_at < platform_received_at:
            raise ValueError(
                "artifact_created_at must not be earlier than platform_received_at"
            )
        observed_at = _optional_timestamp(self.observed_at, "observed_at")
        observation_start = _optional_timestamp(
            self.observation_period_start,
            "observation_period_start",
        )
        observation_end = _optional_timestamp(
            self.observation_period_end,
            "observation_period_end",
        )
        if (observation_start is None) != (observation_end is None):
            raise ValueError(
                "observation period start and end must be supplied together"
            )
        if observation_start is not None and observation_end is not None:
            if observation_end < observation_start:
                raise ValueError(
                    "observation_period_end must not precede observation_period_start"
                )
            if observed_at is not None:
                raise ValueError(
                    "observed_at and an observation period are mutually exclusive"
                )
        effective_from = _optional_timestamp(
            self.effective_from,
            "effective_from",
        )
        effective_until = _optional_timestamp(
            self.effective_until,
            "effective_until",
        )
        if effective_until is not None and effective_from is None:
            raise ValueError("effective_until requires effective_from")
        if (
            effective_from is not None
            and effective_until is not None
            and effective_until <= effective_from
        ):
            raise ValueError("effective_until must be later than effective_from")
        published_at = _optional_timestamp(self.published_at, "published_at")
        source_revision = _optional_visible_ascii(
            self.source_revision,
            "source_revision",
            128,
        )
        values = {
            "platform_received_at": platform_received_at,
            "artifact_created_at": artifact_created_at,
            "observed_at": observed_at,
            "observation_period_start": observation_start,
            "observation_period_end": observation_end,
            "effective_from": effective_from,
            "effective_until": effective_until,
            "published_at": published_at,
            "source_revision": source_revision,
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection()

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observed_at": _timestamp_text(self.observed_at),
            "observation_period_start": _timestamp_text(self.observation_period_start),
            "observation_period_end": _timestamp_text(self.observation_period_end),
            "effective_from": _timestamp_text(self.effective_from),
            "effective_until": _timestamp_text(self.effective_until),
            "published_at": _timestamp_text(self.published_at),
            "source_revision": self.source_revision,
            "platform_received_at": self.platform_received_at.isoformat(),
            "artifact_created_at": self.artifact_created_at.isoformat(),
        }

    def _validate(self) -> None:
        reconstructed = EvidenceTemporalIdentity(
            platform_received_at=_require_canonical_timestamp(
                self.platform_received_at,
                "platform_received_at",
            ),
            artifact_created_at=_require_canonical_timestamp(
                self.artifact_created_at,
                "artifact_created_at",
            ),
            observed_at=_require_optional_canonical_timestamp(
                self.observed_at,
                "observed_at",
            ),
            observation_period_start=_require_optional_canonical_timestamp(
                self.observation_period_start,
                "observation_period_start",
            ),
            observation_period_end=_require_optional_canonical_timestamp(
                self.observation_period_end,
                "observation_period_end",
            ),
            effective_from=_require_optional_canonical_timestamp(
                self.effective_from,
                "effective_from",
            ),
            effective_until=_require_optional_canonical_timestamp(
                self.effective_until,
                "effective_until",
            ),
            published_at=_require_optional_canonical_timestamp(
                self.published_at,
                "published_at",
            ),
            source_revision=self.source_revision,
        )
        if (
            self.schema_version != EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION
            or self._projection() != reconstructed._projection()
            or self.fingerprint != reconstructed.fingerprint
        ):
            raise ValueError("evidence temporal identity retained state is invalid")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical temporal-identity projection."""

        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    """Immutable origin, producer, source, transformation, and lineage identity."""

    origin: EvidenceSourceReference
    producer: EvidenceIdentityReference
    source_references: tuple[EvidenceSourceReference, ...]
    transformations: tuple[EvidenceIdentityReference, ...] = ()
    predecessors: tuple[EvidenceArtifactReference, ...] = ()
    schema_version: str = field(
        init=False,
        default=EVIDENCE_PROVENANCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        origin = _copy_source_reference(self.origin, "origin")
        producer = _copy_identity_reference(self.producer, "producer")
        source_references = _source_reference_tuple(
            self.source_references,
            "source_references",
            minimum_count=1,
            canonical_order=True,
        )
        if origin not in source_references:
            raise ValueError("source_references must include the origin identity")
        if any(
            reference.authority is not origin.authority
            for reference in source_references
        ):
            raise ValueError("source_references must retain one exact origin authority")
        transformations = _identity_reference_tuple(
            self.transformations,
            "transformations",
            minimum_count=0,
            canonical_order=False,
        )
        predecessors = _artifact_reference_tuple(self.predecessors)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "producer", producer)
        object.__setattr__(self, "source_references", source_references)
        object.__setattr__(self, "transformations", transformations)
        object.__setattr__(self, "predecessors", predecessors)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection()

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "origin": self.origin.to_dict(),
            "producer": self.producer.to_dict(),
            "source_references": [item.to_dict() for item in self.source_references],
            "transformations": [item.to_dict() for item in self.transformations],
            "predecessors": [item.to_dict() for item in self.predecessors],
        }

    def _validate(self) -> None:
        reconstructed = EvidenceProvenance(
            origin=_copy_source_reference(self.origin, "origin"),
            producer=_copy_identity_reference(self.producer, "producer"),
            source_references=_source_reference_tuple(
                self.source_references,
                "source_references",
                minimum_count=1,
                canonical_order=True,
                require_retained_tuple=True,
            ),
            transformations=_identity_reference_tuple(
                self.transformations,
                "transformations",
                minimum_count=0,
                canonical_order=False,
                require_retained_tuple=True,
            ),
            predecessors=_artifact_reference_tuple(
                self.predecessors,
                require_retained_tuple=True,
            ),
        )
        if (
            self.schema_version != EVIDENCE_PROVENANCE_SCHEMA_VERSION
            or self._projection() != reconstructed._projection()
            or self.fingerprint != reconstructed.fingerprint
        ):
            raise ValueError("evidence provenance retained state is invalid")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical immutable provenance projection."""

        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class EvidenceArtifact:
    """One exact candidate Evidence Artifact version; not validation or truth."""

    artifact_id: str
    artifact_version: str
    evidence_type: str
    information_class: EvidenceInformationClass
    subjects: tuple[EvidenceSubjectReference, ...]
    authority: EvidenceAuthority
    temporal_identity: EvidenceTemporalIdentity
    provenance: EvidenceProvenance
    governing_contract: EvidenceContractReference
    material_schema_version: str
    contract_authorization: EvidenceContractAuthorization
    material_fingerprint: str
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceArtifact must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        artifact_id: str,
        artifact_version: str,
        subjects: tuple[EvidenceSubjectReference, ...],
        temporal_identity: EvidenceTemporalIdentity,
        provenance: EvidenceProvenance,
        contract_authorization: EvidenceContractAuthorization,
        material_fingerprint: str,
        seal: object,
    ) -> EvidenceArtifact:
        if seal is not _ARTIFACT_SEAL:
            raise TypeError("EvidenceArtifact construction is private")
        copied_provenance = _copy_provenance(provenance)
        authorization = _resolve_governed_evidence_contract_authorization(
            contract_authorization
        )
        definition = authorization.contract_definition
        copied_contract = _copy_contract_reference(definition.governing_contract)
        information_class = definition.information_class
        authority = authorization.authority
        if copied_provenance.origin != authorization.authorized_source:
            raise ValueError(
                "provenance origin must match the governed source authorization"
            )
        if any(
            reference.authority is not authority
            for reference in copied_provenance.source_references
        ):
            raise ValueError(
                "provenance source references must preserve authorized origin"
            )
        if any(
            predecessor.authority is not authority
            for predecessor in copied_provenance.predecessors
        ):
            raise ValueError("predecessor lineage must retain exact origin authority")
        if any(
            predecessor.information_class is not information_class
            for predecessor in copied_provenance.predecessors
        ):
            raise ValueError(
                "predecessor lineage must retain exact Evidence information class"
            )
        result = object.__new__(cls)
        values: dict[str, object] = {
            "artifact_id": _visible_ascii(artifact_id, "artifact_id", 256),
            "artifact_version": _visible_ascii(
                artifact_version,
                "artifact_version",
                128,
            ),
            "evidence_type": definition.evidence_type,
            "information_class": information_class,
            "subjects": _subject_reference_tuple(
                subjects,
                "subjects",
                minimum_count=1,
                canonical_order=True,
            ),
            "authority": authority,
            "temporal_identity": _copy_temporal_identity(temporal_identity),
            "provenance": copied_provenance,
            "governing_contract": copied_contract,
            "material_schema_version": definition.material_schema.schema_version_id,
            "contract_authorization": authorization,
            "material_fingerprint": _fingerprint(
                material_fingerprint,
                "material_fingerprint",
            ),
            "schema_version": EVIDENCE_ARTIFACT_SCHEMA_VERSION,
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
            "artifact_id": self.artifact_id,
            "artifact_version": self.artifact_version,
            "evidence_type": self.evidence_type,
            "information_class": self.information_class.value,
            "subjects": [item.to_dict() for item in self.subjects],
            "authority": self.authority.value,
            "temporal_identity": self.temporal_identity.to_dict(),
            "provenance": self.provenance.to_dict(),
            "governing_contract": self.governing_contract.to_dict(),
            "material_schema_version": self.material_schema_version,
            "contract_authorization": self.contract_authorization.to_dict(),
            "material_fingerprint": self.material_fingerprint,
        }

    def _validate(self) -> None:
        try:
            artifact_id = self.artifact_id
            artifact_version = self.artifact_version
            evidence_type = self.evidence_type
            information_class = self.information_class
            subjects = self.subjects
            authority = self.authority
            temporal_identity = self.temporal_identity
            provenance = self.provenance
            governing_contract = self.governing_contract
            material_schema_version = self.material_schema_version
            contract_authorization = self.contract_authorization
            material_fingerprint = self.material_fingerprint
            schema_version = self.schema_version
            fingerprint = self.fingerprint
        except AttributeError as error:
            raise ValueError(
                "evidence artifact retained state is incomplete"
            ) from error
        _visible_ascii(artifact_id, "artifact_id", 256)
        _visible_ascii(artifact_version, "artifact_version", 128)
        authorization = _copy_contract_authorization(contract_authorization)
        definition = authorization.contract_definition
        if evidence_type != definition.evidence_type:
            raise ValueError("artifact evidence type is not contract-authorized")
        if type(information_class) is not EvidenceInformationClass:
            raise ValueError("evidence artifact information_class is invalid")
        _subject_reference_tuple(
            subjects,
            "subjects",
            minimum_count=1,
            canonical_order=True,
            require_retained_tuple=True,
        )
        if type(authority) is not EvidenceAuthority:
            raise ValueError("evidence artifact authority is invalid")
        if type(temporal_identity) is not EvidenceTemporalIdentity:
            raise ValueError("evidence artifact temporal identity is invalid")
        temporal_identity._validate()
        if type(provenance) is not EvidenceProvenance:
            raise ValueError("evidence artifact provenance is invalid")
        provenance._validate()
        contract = _copy_contract_reference(governing_contract)
        if contract != definition.governing_contract:
            raise ValueError("artifact governing contract is not authorized")
        if information_class is not definition.information_class:
            raise ValueError("artifact information class is not contract-authorized")
        if authority is not authorization.authority:
            raise ValueError("artifact authority is not source-authorized")
        if provenance.origin != authorization.authorized_source:
            raise ValueError("artifact provenance origin is not source-authorized")
        if any(
            reference.authority is not authority
            for reference in provenance.source_references
        ):
            raise ValueError("artifact source authority correspondence is invalid")
        if any(
            predecessor.authority is not authority
            or predecessor.information_class is not information_class
            for predecessor in provenance.predecessors
        ):
            raise ValueError("artifact predecessor semantic authority is inconsistent")
        _visible_ascii(
            material_schema_version,
            "material_schema_version",
            128,
        )
        if material_schema_version != definition.material_schema.schema_version_id:
            raise ValueError("artifact material schema is not contract-authorized")
        _fingerprint(material_fingerprint, "material_fingerprint")
        if schema_version != EVIDENCE_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("evidence artifact schema_version is invalid")
        retained_fingerprint = _fingerprint(fingerprint, "fingerprint")
        if retained_fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("evidence artifact fingerprint does not match content")

    def reference(self) -> EvidenceArtifactReference:
        """Return an exact immutable reference to this artifact version."""

        self._validate()
        return EvidenceArtifactReference(
            artifact_id=self.artifact_id,
            artifact_version=self.artifact_version,
            artifact_fingerprint=self.fingerprint,
            information_class=self.information_class,
            authority=self.authority,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical in-memory artifact projection."""

        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


def _create_evidence_artifact(
    *,
    artifact_id: str,
    artifact_version: str,
    subjects: tuple[EvidenceSubjectReference, ...],
    temporal_identity: EvidenceTemporalIdentity,
    provenance: EvidenceProvenance,
    contract_authorization: EvidenceContractAuthorization,
    material_fingerprint: str,
) -> EvidenceArtifact:
    """Create a candidate artifact at a trusted Evidence adapter boundary."""

    return EvidenceArtifact._create(
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        subjects=subjects,
        temporal_identity=temporal_identity,
        provenance=provenance,
        contract_authorization=contract_authorization,
        material_fingerprint=material_fingerprint,
        seal=_ARTIFACT_SEAL,
    )


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


def _optional_visible_ascii(
    value: object,
    field_name: str,
    maximum_length: int,
) -> str | None:
    if value is None:
        return None
    return _visible_ascii(value, field_name, maximum_length)


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be a datetime")
    timestamp = value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return timestamp.astimezone(UTC)


def _optional_timestamp(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, field_name)


def _require_canonical_timestamp(value: object, field_name: str) -> datetime:
    canonical = _timestamp(value, field_name)
    retained = cast(datetime, value)
    if retained.tzinfo is not UTC or retained.isoformat() != canonical.isoformat():
        raise ValueError(f"{field_name} must retain canonical UTC state")
    return canonical


def _require_optional_canonical_timestamp(
    value: object,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    return _require_canonical_timestamp(value, field_name)


def _timestamp_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _copy_identity_reference(
    value: object,
    field_name: str,
) -> EvidenceIdentityReference:
    if type(value) is not EvidenceIdentityReference:
        raise TypeError(f"{field_name} must be an EvidenceIdentityReference")
    reference = value
    reference._validate()
    return EvidenceIdentityReference(
        namespace=reference.namespace,
        identity_id=reference.identity_id,
        identity_version=reference.identity_version,
        identity_fingerprint=reference.identity_fingerprint,
    )


def _copy_source_reference(
    value: object,
    field_name: str,
) -> EvidenceSourceReference:
    if type(value) is not EvidenceSourceReference:
        raise TypeError(f"{field_name} must be an EvidenceSourceReference")
    reference = value
    reference._validate()
    return EvidenceSourceReference(
        namespace=reference.namespace,
        source_id=reference.source_id,
        source_version=reference.source_version,
        authority=reference.authority,
        source_fingerprint=reference.source_fingerprint,
    )


def _copy_subject_reference(value: object) -> EvidenceSubjectReference:
    if type(value) is not EvidenceSubjectReference:
        raise TypeError("subjects must contain EvidenceSubjectReference values")
    reference = value
    reference._validate()
    return EvidenceSubjectReference(
        namespace=reference.namespace,
        subject_id=reference.subject_id,
        subject_version=reference.subject_version,
        subject_fingerprint=reference.subject_fingerprint,
    )


def _copy_contract_reference(value: object) -> EvidenceContractReference:
    if type(value) is not EvidenceContractReference:
        raise TypeError("governing_contract must be an EvidenceContractReference")
    reference = value
    reference._validate()
    return EvidenceContractReference(
        namespace=reference.namespace,
        contract_id=reference.contract_id,
        contract_version=reference.contract_version,
        information_class=reference.information_class,
        contract_fingerprint=reference.contract_fingerprint,
    )


def _copy_artifact_reference(value: object) -> EvidenceArtifactReference:
    if type(value) is not EvidenceArtifactReference:
        raise TypeError("predecessors must contain EvidenceArtifactReference values")
    reference = value
    reference._validate()
    return EvidenceArtifactReference(
        artifact_id=reference.artifact_id,
        artifact_version=reference.artifact_version,
        artifact_fingerprint=reference.artifact_fingerprint,
        information_class=reference.information_class,
        authority=reference.authority,
    )


def _source_reference_tuple(
    value: object,
    field_name: str,
    *,
    minimum_count: int,
    canonical_order: bool,
    require_retained_tuple: bool = False,
) -> tuple[EvidenceSourceReference, ...]:
    if type(value) is not tuple:
        message = (
            "must be physically stored as a tuple"
            if require_retained_tuple
            else "must be an exact tuple"
        )
        raise TypeError(f"{field_name} {message}")
    references = tuple(
        _copy_source_reference(item, field_name)
        for item in cast(tuple[object, ...], value)
    )
    if len(references) < minimum_count:
        raise ValueError(f"{field_name} requires at least {minimum_count} reference")
    if len(set(references)) != len(references):
        raise ValueError(f"{field_name} must not contain duplicate references")
    if canonical_order:
        ordered = tuple(sorted(references, key=_source_reference_sort_key))
        if require_retained_tuple and references != ordered:
            raise ValueError(f"{field_name} retained ordering is not canonical")
        return ordered
    return references


def _identity_reference_tuple(
    value: object,
    field_name: str,
    *,
    minimum_count: int,
    canonical_order: bool,
    require_retained_tuple: bool = False,
) -> tuple[EvidenceIdentityReference, ...]:
    if type(value) is not tuple:
        message = (
            "must be physically stored as a tuple"
            if require_retained_tuple
            else "must be an exact tuple"
        )
        raise TypeError(f"{field_name} {message}")
    references = tuple(
        _copy_identity_reference(item, field_name)
        for item in cast(tuple[object, ...], value)
    )
    if len(references) < minimum_count:
        raise ValueError(f"{field_name} requires at least {minimum_count} reference")
    if len(set(references)) != len(references):
        raise ValueError(f"{field_name} must not contain duplicate references")
    if canonical_order:
        ordered = tuple(sorted(references, key=_identity_reference_sort_key))
        if require_retained_tuple and references != ordered:
            raise ValueError(f"{field_name} retained ordering is not canonical")
        return ordered
    return references


def _identity_reference_sort_key(
    value: EvidenceIdentityReference,
) -> tuple[str, str, str, str]:
    return (
        value.namespace,
        value.identity_id,
        value.identity_version,
        "" if value.identity_fingerprint is None else value.identity_fingerprint,
    )


def _source_reference_sort_key(
    value: EvidenceSourceReference,
) -> tuple[str, str, str, str]:
    return (
        value.namespace,
        value.source_id,
        value.source_version,
        "" if value.source_fingerprint is None else value.source_fingerprint,
    )


def _subject_reference_tuple(
    value: object,
    field_name: str,
    *,
    minimum_count: int,
    canonical_order: bool,
    require_retained_tuple: bool = False,
) -> tuple[EvidenceSubjectReference, ...]:
    if type(value) is not tuple:
        message = (
            "must be physically stored as a tuple"
            if require_retained_tuple
            else "must be an exact tuple"
        )
        raise TypeError(f"{field_name} {message}")
    references = tuple(
        _copy_subject_reference(item) for item in cast(tuple[object, ...], value)
    )
    if len(references) < minimum_count:
        raise ValueError(f"{field_name} requires at least {minimum_count} reference")
    if len(set(references)) != len(references):
        raise ValueError(f"{field_name} must not contain duplicate references")
    if canonical_order:
        ordered = tuple(sorted(references, key=_subject_reference_sort_key))
        if require_retained_tuple and references != ordered:
            raise ValueError(f"{field_name} retained ordering is not canonical")
        return ordered
    return references


def _subject_reference_sort_key(
    value: EvidenceSubjectReference,
) -> tuple[str, str, str, str]:
    return (
        value.namespace,
        value.subject_id,
        value.subject_version,
        "" if value.subject_fingerprint is None else value.subject_fingerprint,
    )


def _artifact_reference_tuple(
    value: object,
    *,
    require_retained_tuple: bool = False,
) -> tuple[EvidenceArtifactReference, ...]:
    if type(value) is not tuple:
        message = (
            "must be physically stored as a tuple"
            if require_retained_tuple
            else "must be an exact tuple"
        )
        raise TypeError(f"predecessors {message}")
    references = tuple(
        _copy_artifact_reference(item) for item in cast(tuple[object, ...], value)
    )
    if len(set(references)) != len(references):
        raise ValueError("predecessors must not contain duplicate references")
    ordered = tuple(
        sorted(
            references,
            key=lambda item: (
                item.artifact_id,
                item.artifact_version,
                item.artifact_fingerprint,
            ),
        )
    )
    if require_retained_tuple and references != ordered:
        raise ValueError("predecessors retained ordering is not canonical")
    return ordered


def _copy_temporal_identity(value: object) -> EvidenceTemporalIdentity:
    if type(value) is not EvidenceTemporalIdentity:
        raise TypeError("temporal_identity must be an EvidenceTemporalIdentity")
    temporal = value
    temporal._validate()
    return EvidenceTemporalIdentity(
        platform_received_at=temporal.platform_received_at,
        artifact_created_at=temporal.artifact_created_at,
        observed_at=temporal.observed_at,
        observation_period_start=temporal.observation_period_start,
        observation_period_end=temporal.observation_period_end,
        effective_from=temporal.effective_from,
        effective_until=temporal.effective_until,
        published_at=temporal.published_at,
        source_revision=temporal.source_revision,
    )


def _copy_provenance(value: object) -> EvidenceProvenance:
    if type(value) is not EvidenceProvenance:
        raise TypeError("provenance must be an EvidenceProvenance")
    provenance = value
    provenance._validate()
    return EvidenceProvenance(
        origin=provenance.origin,
        producer=provenance.producer,
        source_references=provenance.source_references,
        transformations=provenance.transformations,
        predecessors=provenance.predecessors,
    )


__all__ = [
    "EVIDENCE_ARTIFACT_SCHEMA_VERSION",
    "EVIDENCE_PROVENANCE_SCHEMA_VERSION",
    "EVIDENCE_TEMPORAL_IDENTITY_SCHEMA_VERSION",
    "EvidenceArtifact",
    "EvidenceArtifactReference",
    "EvidenceAuthority",
    "EvidenceInformationClass",
    "EvidenceIdentityReference",
    "EvidenceProvenance",
    "EvidenceTemporalIdentity",
]
