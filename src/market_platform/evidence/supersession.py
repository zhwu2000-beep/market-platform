"""Immutable artifact-supersession links and deterministic as-of resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)

EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION = (
    "evidence_artifact_supersession_link/v1"
)
EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION = (
    "evidence_artifact_supersession_link_reference/v1"
)
EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION = (
    "evidence_artifact_supersession_resolution/v1"
)

_SUPERSESSION_LINK_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)


class EvidenceArtifactSupersessionResolutionError(ValueError):
    """Raised when applicable artifact supersession lineage cannot resolve safely."""


@dataclass(frozen=True, slots=True)
class EvidenceArtifactSupersessionLinkReference:
    """Exact immutable reference to one artifact supersession lifecycle link."""

    supersession_link_id: str
    predecessor_artifact_reference: EvidenceArtifactReference
    successor_artifact_reference: EvidenceArtifactReference
    scope: str
    recorded_at: datetime
    effective_at: datetime
    supersession_link_fingerprint: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        predecessor = _copy_artifact_reference(
            self.predecessor_artifact_reference,
            "predecessor_artifact_reference",
        )
        successor = _copy_artifact_reference(
            self.successor_artifact_reference,
            "successor_artifact_reference",
        )
        _require_distinct_artifact_versions(predecessor, successor)
        _require_semantic_continuity(predecessor, successor)
        values: dict[str, object] = {
            "supersession_link_id": _visible_ascii(
                self.supersession_link_id,
                "supersession_link_id",
                256,
            ),
            "predecessor_artifact_reference": predecessor,
            "successor_artifact_reference": successor,
            "scope": _visible_ascii(self.scope, "scope", 256),
            "recorded_at": _timestamp(self.recorded_at, "recorded_at"),
            "effective_at": _timestamp(self.effective_at, "effective_at"),
            "supersession_link_fingerprint": _fingerprint(
                self.supersession_link_fingerprint,
                "supersession_link_fingerprint",
            ),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "supersession_link_id": self.supersession_link_id,
            "predecessor_artifact_reference": (
                self.predecessor_artifact_reference.to_dict()
            ),
            "successor_artifact_reference": (
                self.successor_artifact_reference.to_dict()
            ),
            "scope": self.scope,
            "recorded_at": self.recorded_at.isoformat(),
            "effective_at": self.effective_at.isoformat(),
            "supersession_link_fingerprint": self.supersession_link_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceArtifactSupersessionLinkReference(
            supersession_link_id=self.supersession_link_id,
            predecessor_artifact_reference=self.predecessor_artifact_reference,
            successor_artifact_reference=self.successor_artifact_reference,
            scope=self.scope,
            recorded_at=_require_canonical_timestamp(
                self.recorded_at,
                "recorded_at",
            ),
            effective_at=_require_canonical_timestamp(
                self.effective_at,
                "effective_at",
            ),
            supersession_link_fingerprint=self.supersession_link_fingerprint,
        )
        if (
            self.schema_version
            != EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "artifact supersession link reference schema_version is invalid"
            )
        if _fingerprint(self.fingerprint, "fingerprint") != reconstructed.fingerprint:
            raise ValueError(
                "artifact supersession link reference fingerprint does not "
                "match identity"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact supersession-link-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class EvidenceArtifactSupersessionLink:
    """One append-only replacement declaration for exact artifact versions."""

    supersession_link_id: str
    predecessor_artifact_reference: EvidenceArtifactReference
    successor_artifact_reference: EvidenceArtifactReference
    scope: str
    reason: str
    recorded_at: datetime
    effective_at: datetime
    responsible_actor_identity: EvidenceIdentityReference
    responsible_capability_identity: EvidenceIdentityReference | None
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceArtifactSupersessionLink must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        supersession_link_id: str,
        predecessor_artifact_reference: EvidenceArtifactReference,
        successor_artifact_reference: EvidenceArtifactReference,
        scope: str,
        reason: str,
        recorded_at: datetime,
        effective_at: datetime,
        responsible_actor_identity: EvidenceIdentityReference,
        responsible_capability_identity: EvidenceIdentityReference | None,
        seal: object,
    ) -> EvidenceArtifactSupersessionLink:
        if seal is not _SUPERSESSION_LINK_SEAL:
            raise TypeError("EvidenceArtifactSupersessionLink construction is private")
        predecessor = _copy_artifact_reference(
            predecessor_artifact_reference,
            "predecessor_artifact_reference",
        )
        successor = _copy_artifact_reference(
            successor_artifact_reference,
            "successor_artifact_reference",
        )
        _require_distinct_artifact_versions(predecessor, successor)
        _require_semantic_continuity(predecessor, successor)
        result = object.__new__(cls)
        values: dict[str, object] = {
            "supersession_link_id": _visible_ascii(
                supersession_link_id,
                "supersession_link_id",
                256,
            ),
            "predecessor_artifact_reference": predecessor,
            "successor_artifact_reference": successor,
            "scope": _visible_ascii(scope, "scope", 256),
            "reason": _reason(reason),
            "recorded_at": _timestamp(recorded_at, "recorded_at"),
            "effective_at": _timestamp(effective_at, "effective_at"),
            "responsible_actor_identity": _copy_identity_reference(
                responsible_actor_identity,
                "responsible_actor_identity",
            ),
            "responsible_capability_identity": _copy_optional_identity_reference(
                responsible_capability_identity,
                "responsible_capability_identity",
            ),
            "schema_version": EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION,
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
            "supersession_link_id": self.supersession_link_id,
            "predecessor_artifact_reference": (
                self.predecessor_artifact_reference.to_dict()
            ),
            "successor_artifact_reference": (
                self.successor_artifact_reference.to_dict()
            ),
            "scope": self.scope,
            "reason": self.reason,
            "recorded_at": self.recorded_at.isoformat(),
            "effective_at": self.effective_at.isoformat(),
            "responsible_actor_identity": (self.responsible_actor_identity.to_dict()),
            "responsible_capability_identity": (
                None
                if self.responsible_capability_identity is None
                else self.responsible_capability_identity.to_dict()
            ),
        }

    def _validate(self) -> None:
        try:
            supersession_link_id = self.supersession_link_id
            predecessor = self.predecessor_artifact_reference
            successor = self.successor_artifact_reference
            scope = self.scope
            reason = self.reason
            recorded_at = self.recorded_at
            effective_at = self.effective_at
            actor = self.responsible_actor_identity
            capability = self.responsible_capability_identity
            schema_version = self.schema_version
            fingerprint = self.fingerprint
        except AttributeError as error:
            raise ValueError(
                "artifact supersession link retained state is incomplete"
            ) from error
        _visible_ascii(supersession_link_id, "supersession_link_id", 256)
        copied_predecessor = _copy_artifact_reference(
            predecessor,
            "predecessor_artifact_reference",
        )
        copied_successor = _copy_artifact_reference(
            successor,
            "successor_artifact_reference",
        )
        _require_distinct_artifact_versions(copied_predecessor, copied_successor)
        _require_semantic_continuity(copied_predecessor, copied_successor)
        _visible_ascii(scope, "scope", 256)
        _reason(reason)
        _require_canonical_timestamp(recorded_at, "recorded_at")
        _require_canonical_timestamp(effective_at, "effective_at")
        _copy_identity_reference(actor, "responsible_actor_identity")
        _copy_optional_identity_reference(
            capability,
            "responsible_capability_identity",
        )
        if schema_version != EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION:
            raise ValueError("artifact supersession link schema_version is invalid")
        if _fingerprint(fingerprint, "fingerprint") != canonical_fingerprint(
            self._fingerprint_payload()
        ):
            raise ValueError(
                "artifact supersession link fingerprint does not match content"
            )

    def reference(self) -> EvidenceArtifactSupersessionLinkReference:
        """Return an exact immutable reference to this lifecycle link."""

        self._validate()
        return EvidenceArtifactSupersessionLinkReference(
            supersession_link_id=self.supersession_link_id,
            predecessor_artifact_reference=self.predecessor_artifact_reference,
            successor_artifact_reference=self.successor_artifact_reference,
            scope=self.scope,
            recorded_at=self.recorded_at,
            effective_at=self.effective_at,
            supersession_link_fingerprint=self.fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical immutable supersession-link projection."""

        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class EvidenceArtifactSupersessionResolution:
    """Exact scoped artifact and link lineage selected under explicit cutoffs."""

    requested_artifact_reference: EvidenceArtifactReference
    resolved_artifact_reference: EvidenceArtifactReference
    scope: str
    knowledge_as_of: datetime
    effective_as_of: datetime
    applied_supersession_link_references: tuple[
        EvidenceArtifactSupersessionLinkReference,
        ...,
    ]
    schema_version: str = field(
        init=False,
        default=EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION,
    )

    def __post_init__(self) -> None:
        values: dict[str, object] = {
            "requested_artifact_reference": _copy_artifact_reference(
                self.requested_artifact_reference,
                "requested_artifact_reference",
            ),
            "resolved_artifact_reference": _copy_artifact_reference(
                self.resolved_artifact_reference,
                "resolved_artifact_reference",
            ),
            "scope": _visible_ascii(self.scope, "scope", 256),
            "knowledge_as_of": _timestamp(
                self.knowledge_as_of,
                "knowledge_as_of",
            ),
            "effective_as_of": _timestamp(
                self.effective_as_of,
                "effective_as_of",
            ),
            "applied_supersession_link_references": (
                _supersession_link_reference_tuple(
                    self.applied_supersession_link_references
                )
            ),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)
        _require_resolution_correspondence(self)

    def _validate(self) -> None:
        reconstructed = EvidenceArtifactSupersessionResolution(
            requested_artifact_reference=self.requested_artifact_reference,
            resolved_artifact_reference=self.resolved_artifact_reference,
            scope=self.scope,
            knowledge_as_of=_require_canonical_timestamp(
                self.knowledge_as_of,
                "knowledge_as_of",
            ),
            effective_as_of=_require_canonical_timestamp(
                self.effective_as_of,
                "effective_as_of",
            ),
            applied_supersession_link_references=(
                self.applied_supersession_link_references
            ),
        )
        if (
            self.schema_version
            != EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION
            or self != reconstructed
        ):
            raise ValueError(
                "artifact supersession resolution retained state is invalid"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic resolution without an aggregate fingerprint."""

        self._validate()
        return {
            "schema_version": self.schema_version,
            "requested_artifact_reference": (
                self.requested_artifact_reference.to_dict()
            ),
            "resolved_artifact_reference": self.resolved_artifact_reference.to_dict(),
            "scope": self.scope,
            "knowledge_as_of": self.knowledge_as_of.isoformat(),
            "effective_as_of": self.effective_as_of.isoformat(),
            "applied_supersession_link_references": [
                reference.to_dict()
                for reference in self.applied_supersession_link_references
            ],
        }


def create_evidence_artifact_supersession_link(
    *,
    supersession_link_id: str,
    predecessor_artifact_reference: EvidenceArtifactReference,
    successor_artifact_reference: EvidenceArtifactReference,
    scope: str,
    reason: str,
    recorded_at: datetime,
    effective_at: datetime,
    responsible_actor_identity: EvidenceIdentityReference,
    responsible_capability_identity: EvidenceIdentityReference | None = None,
) -> EvidenceArtifactSupersessionLink:
    """Create one append-only link without modifying either artifact."""

    return EvidenceArtifactSupersessionLink._create(
        supersession_link_id=supersession_link_id,
        predecessor_artifact_reference=predecessor_artifact_reference,
        successor_artifact_reference=successor_artifact_reference,
        scope=scope,
        reason=reason,
        recorded_at=recorded_at,
        effective_at=effective_at,
        responsible_actor_identity=responsible_actor_identity,
        responsible_capability_identity=responsible_capability_identity,
        seal=_SUPERSESSION_LINK_SEAL,
    )


def resolve_evidence_artifact_supersession_as_of(
    *,
    artifact_reference: EvidenceArtifactReference,
    scope: str,
    artifact_references: tuple[EvidenceArtifactReference, ...],
    supersession_links: tuple[EvidenceArtifactSupersessionLink, ...],
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> EvidenceArtifactSupersessionResolution:
    """Resolve one exact artifact through applicable scoped supersession links."""

    requested = _copy_artifact_reference(
        artifact_reference,
        "artifact_reference",
    )
    exact_scope = _visible_ascii(scope, "scope", 256)
    artifacts = _artifact_reference_tuple(artifact_references)
    links = _supersession_link_tuple(supersession_links)
    knowledge_cutoff = _timestamp(knowledge_as_of, "knowledge_as_of")
    effective_cutoff = _timestamp(effective_as_of, "effective_as_of")
    available = {_artifact_identity(reference): reference for reference in artifacts}
    if _artifact_identity(requested) not in available:
        raise EvidenceArtifactSupersessionResolutionError(
            "requested artifact reference is missing from available lineage"
        )
    applicable = tuple(
        link
        for link in links
        if link.scope == exact_scope
        and link.recorded_at <= knowledge_cutoff
        and link.effective_at <= effective_cutoff
    )
    candidates_by_predecessor: dict[
        tuple[str, str, str],
        list[EvidenceArtifactSupersessionLink],
    ] = {}
    for link in applicable:
        predecessor_identity = _artifact_identity(link.predecessor_artifact_reference)
        candidates_by_predecessor.setdefault(predecessor_identity, []).append(link)

    current = requested
    seen = {_artifact_identity(current)}
    applied: list[EvidenceArtifactSupersessionLinkReference] = []
    while candidates := candidates_by_predecessor.get(_artifact_identity(current)):
        successor_identities = {
            _artifact_identity(link.successor_artifact_reference) for link in candidates
        }
        if len(successor_identities) != 1:
            raise EvidenceArtifactSupersessionResolutionError(
                "forked artifact supersession lineage has no unique successor"
            )
        precedence = max((link.effective_at, link.recorded_at) for link in candidates)
        co_precedent = tuple(
            link
            for link in candidates
            if (link.effective_at, link.recorded_at) == precedence
        )
        if len(co_precedent) != 1:
            raise EvidenceArtifactSupersessionResolutionError(
                "co-precedent artifact supersession links are ambiguous"
            )
        selected = co_precedent[0]
        predecessor_identity = _artifact_identity(
            selected.predecessor_artifact_reference
        )
        successor_identity = _artifact_identity(selected.successor_artifact_reference)
        if predecessor_identity not in available or successor_identity not in available:
            raise EvidenceArtifactSupersessionResolutionError(
                "applicable artifact supersession link has missing referenced lineage"
            )
        if successor_identity in seen:
            raise EvidenceArtifactSupersessionResolutionError(
                "applicable artifact supersession lineage contains a cycle"
            )
        seen.add(successor_identity)
        applied.append(selected.reference())
        current = available[successor_identity]

    return EvidenceArtifactSupersessionResolution(
        requested_artifact_reference=requested,
        resolved_artifact_reference=current,
        scope=exact_scope,
        knowledge_as_of=knowledge_cutoff,
        effective_as_of=effective_cutoff,
        applied_supersession_link_references=tuple(applied),
    )


def _require_resolution_correspondence(
    resolution: EvidenceArtifactSupersessionResolution,
) -> None:
    current = resolution.requested_artifact_reference
    for reference in resolution.applied_supersession_link_references:
        if reference.scope != resolution.scope:
            raise ValueError("resolved supersession link must bind the requested scope")
        if reference.recorded_at > resolution.knowledge_as_of:
            raise ValueError("resolved supersession link exceeds knowledge_as_of")
        if reference.effective_at > resolution.effective_as_of:
            raise ValueError("resolved supersession link exceeds effective_as_of")
        if reference.predecessor_artifact_reference != current:
            raise ValueError("resolved supersession links must form an exact chain")
        current = reference.successor_artifact_reference
    if current != resolution.resolved_artifact_reference:
        raise ValueError("resolved artifact does not correspond to link lineage")


def _artifact_reference_tuple(
    value: object,
) -> tuple[EvidenceArtifactReference, ...]:
    if type(value) is not tuple:
        raise TypeError("artifact_references must be an exact tuple")
    references = tuple(
        _copy_artifact_reference(item, "artifact_references")
        for item in cast(tuple[object, ...], value)
    )
    identities = tuple(_artifact_identity(reference) for reference in references)
    if len(set(identities)) != len(identities):
        raise ValueError("artifact_references must not contain duplicates")
    version_identities = tuple(
        (reference.artifact_id, reference.artifact_version) for reference in references
    )
    if len(set(version_identities)) != len(version_identities):
        raise ValueError(
            "artifact_references contain conflicting exact artifact versions"
        )
    return tuple(sorted(references, key=_artifact_identity))


def _supersession_link_tuple(
    value: object,
) -> tuple[EvidenceArtifactSupersessionLink, ...]:
    if type(value) is not tuple:
        raise TypeError("supersession_links must be an exact tuple")
    links: list[EvidenceArtifactSupersessionLink] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceArtifactSupersessionLink:
            raise TypeError(
                "supersession_links must contain "
                "EvidenceArtifactSupersessionLink values"
            )
        item._validate()
        links.append(item)
    link_ids = tuple(link.supersession_link_id for link in links)
    if len(set(link_ids)) != len(link_ids):
        raise ValueError("supersession_links must not duplicate link identities")
    fingerprints = tuple(link.fingerprint for link in links)
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("supersession_links must not contain duplicates")
    return tuple(
        sorted(
            links,
            key=lambda link: (
                link.scope,
                link.effective_at,
                link.recorded_at,
                link.supersession_link_id,
            ),
        )
    )


def _supersession_link_reference_tuple(
    value: object,
) -> tuple[EvidenceArtifactSupersessionLinkReference, ...]:
    if type(value) is not tuple:
        raise TypeError("applied_supersession_link_references must be an exact tuple")
    references: list[EvidenceArtifactSupersessionLinkReference] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceArtifactSupersessionLinkReference:
            raise TypeError(
                "applied_supersession_link_references must contain "
                "EvidenceArtifactSupersessionLinkReference values"
            )
        item._validate()
        references.append(
            EvidenceArtifactSupersessionLinkReference(
                supersession_link_id=item.supersession_link_id,
                predecessor_artifact_reference=(item.predecessor_artifact_reference),
                successor_artifact_reference=item.successor_artifact_reference,
                scope=item.scope,
                recorded_at=item.recorded_at,
                effective_at=item.effective_at,
                supersession_link_fingerprint=item.supersession_link_fingerprint,
            )
        )
    link_ids = tuple(reference.supersession_link_id for reference in references)
    if len(set(link_ids)) != len(link_ids):
        raise ValueError(
            "applied_supersession_link_references must not duplicate identities"
        )
    return tuple(references)


def _copy_artifact_reference(
    value: object,
    field_name: str,
) -> EvidenceArtifactReference:
    if type(value) is not EvidenceArtifactReference:
        raise TypeError(f"{field_name} must be an EvidenceArtifactReference")
    reference = value
    reference._validate()
    return EvidenceArtifactReference(
        artifact_id=reference.artifact_id,
        artifact_version=reference.artifact_version,
        artifact_fingerprint=reference.artifact_fingerprint,
        information_class=reference.information_class,
        authority=reference.authority,
    )


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


def _copy_optional_identity_reference(
    value: object,
    field_name: str,
) -> EvidenceIdentityReference | None:
    if value is None:
        return None
    return _copy_identity_reference(value, field_name)


def _require_distinct_artifact_versions(
    predecessor: EvidenceArtifactReference,
    successor: EvidenceArtifactReference,
) -> None:
    if (
        predecessor.artifact_id,
        predecessor.artifact_version,
    ) == (
        successor.artifact_id,
        successor.artifact_version,
    ):
        raise ValueError(
            "artifact supersession must link distinct exact artifact versions"
        )


def _require_semantic_continuity(
    predecessor: EvidenceArtifactReference,
    successor: EvidenceArtifactReference,
) -> None:
    if predecessor.authority is not successor.authority:
        raise ValueError("artifact supersession cannot change Evidence authority")
    if predecessor.information_class is not successor.information_class:
        raise ValueError(
            "artifact supersession cannot change Evidence information class"
        )


def _artifact_identity(
    reference: EvidenceArtifactReference,
) -> tuple[str, str, str]:
    return (
        reference.artifact_id,
        reference.artifact_version,
        reference.artifact_fingerprint,
    )


def _reason(value: object) -> str:
    if type(value) is not str:
        raise TypeError("reason must be a string")
    if not value or value != value.strip():
        raise ValueError("reason must be nonempty without edge whitespace")
    if len(value) > 2048:
        raise ValueError("reason exceeds maximum length 2048")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("reason must not contain control characters")
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
    "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION",
    "EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION",
    "EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION",
    "EvidenceArtifactSupersessionLink",
    "EvidenceArtifactSupersessionLinkReference",
    "EvidenceArtifactSupersessionResolution",
    "EvidenceArtifactSupersessionResolutionError",
    "create_evidence_artifact_supersession_link",
    "resolve_evidence_artifact_supersession_as_of",
]
