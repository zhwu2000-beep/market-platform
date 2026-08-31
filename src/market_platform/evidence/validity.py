"""Immutable validity lifecycle contracts and deterministic as-of selection."""

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

EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION = "evidence_validity_event/v3"
EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION = "evidence_validity_reference/v1"

_VALIDITY_EVENT_SEAL = object()
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_TERMINAL_VALIDITY_STATUSES = frozenset(
    {
        "EXPIRED",
        "WITHDRAWN",
        "REVOKED",
    }
)


class EvidenceValidityStatus(StrEnum):
    """The complete set of Evidence validity lifecycle conclusions."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class EvidenceValidityReference:
    """Exact immutable reference to one validity event."""

    validity_event_id: str
    artifact_reference: EvidenceArtifactReference
    status: EvidenceValidityStatus
    scope: str
    recorded_at: datetime
    effective_at: datetime
    validity_event_fingerprint: str
    schema_version: str = field(
        init=False,
        default=EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION,
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.status) is not EvidenceValidityStatus:
            raise TypeError("status must be an exact EvidenceValidityStatus")
        values: dict[str, object] = {
            "validity_event_id": _visible_ascii(
                self.validity_event_id,
                "validity_event_id",
                256,
            ),
            "artifact_reference": _copy_artifact_reference(self.artifact_reference),
            "scope": _visible_ascii(self.scope, "scope", 256),
            "recorded_at": _timestamp(self.recorded_at, "recorded_at"),
            "effective_at": _timestamp(self.effective_at, "effective_at"),
            "validity_event_fingerprint": _fingerprint(
                self.validity_event_fingerprint,
                "validity_event_fingerprint",
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
            "validity_event_id": self.validity_event_id,
            "artifact_reference": self.artifact_reference.to_dict(),
            "status": self.status.value,
            "scope": self.scope,
            "recorded_at": self.recorded_at.isoformat(),
            "effective_at": self.effective_at.isoformat(),
            "validity_event_fingerprint": self.validity_event_fingerprint,
        }

    def _validate(self) -> None:
        reconstructed = EvidenceValidityReference(
            validity_event_id=self.validity_event_id,
            artifact_reference=self.artifact_reference,
            status=self.status,
            scope=self.scope,
            recorded_at=_require_canonical_timestamp(
                self.recorded_at,
                "recorded_at",
            ),
            effective_at=_require_canonical_timestamp(
                self.effective_at,
                "effective_at",
            ),
            validity_event_fingerprint=self.validity_event_fingerprint,
        )
        if self.schema_version != EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION:
            raise ValueError("evidence validity reference schema_version is invalid")
        retained_fingerprint = _fingerprint(self.fingerprint, "fingerprint")
        if retained_fingerprint != reconstructed.fingerprint:
            raise ValueError(
                "evidence validity reference fingerprint does not match identity"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the exact validity-event-reference projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class EvidenceValidityEvent:
    """One append-only validity conclusion for an exact artifact and scope."""

    validity_event_id: str
    artifact_reference: EvidenceArtifactReference
    status: EvidenceValidityStatus
    recorded_at: datetime
    effective_at: datetime
    actor_identity: EvidenceIdentityReference
    capability_identity: EvidenceIdentityReference | None
    predecessor_validity_event_reference: EvidenceValidityReference | None
    reason: str
    scope: str
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError("EvidenceValidityEvent must be factory-created")

    @classmethod
    def _create(
        cls,
        *,
        validity_event_id: str,
        artifact_reference: EvidenceArtifactReference,
        status: EvidenceValidityStatus,
        recorded_at: datetime,
        effective_at: datetime,
        actor_identity: EvidenceIdentityReference,
        capability_identity: EvidenceIdentityReference | None,
        predecessor_validity_event_reference: EvidenceValidityReference | None,
        reason: str,
        scope: str,
        seal: object,
    ) -> EvidenceValidityEvent:
        if seal is not _VALIDITY_EVENT_SEAL:
            raise TypeError("EvidenceValidityEvent construction is private")
        if type(status) is not EvidenceValidityStatus:
            raise TypeError("status must be an exact EvidenceValidityStatus")
        artifact = _copy_artifact_reference(artifact_reference)
        exact_scope = _visible_ascii(scope, "scope", 256)
        exact_recorded_at = _timestamp(recorded_at, "recorded_at")
        exact_effective_at = _timestamp(effective_at, "effective_at")
        predecessor_reference = _copy_optional_validity_reference(
            predecessor_validity_event_reference
        )
        if predecessor_reference is not None:
            if predecessor_reference.artifact_reference != artifact:
                raise ValueError("validity predecessor must bind the same artifact")
            if predecessor_reference.scope != exact_scope:
                raise ValueError("validity predecessor must bind the same scope")
            if predecessor_reference.validity_event_id == validity_event_id:
                raise ValueError("validity predecessor must be a distinct event")
            if predecessor_reference.recorded_at > exact_recorded_at:
                raise ValueError("validity predecessor must already be recorded")
            if predecessor_reference.effective_at > exact_effective_at:
                raise ValueError(
                    "validity successor effective_at must not precede its predecessor"
                )
            if (
                predecessor_reference.status.value in _TERMINAL_VALIDITY_STATUSES
                and status is EvidenceValidityStatus.ACTIVE
            ):
                raise ValueError(
                    "terminal validity cannot be reactivated for an artifact version"
                )
        instance = object.__new__(cls)
        values: dict[str, object] = {
            "validity_event_id": _visible_ascii(
                validity_event_id,
                "validity_event_id",
                256,
            ),
            "artifact_reference": artifact,
            "status": status,
            "recorded_at": exact_recorded_at,
            "effective_at": exact_effective_at,
            "actor_identity": _copy_identity_reference(actor_identity),
            "capability_identity": _copy_optional_identity_reference(
                capability_identity,
                "capability_identity",
            ),
            "predecessor_validity_event_reference": predecessor_reference,
            "reason": _reason(reason),
            "scope": exact_scope,
            "schema_version": EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION,
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
            "validity_event_id": self.validity_event_id,
            "artifact_reference": self.artifact_reference.to_dict(),
            "status": self.status.value,
            "recorded_at": self.recorded_at.isoformat(),
            "effective_at": self.effective_at.isoformat(),
            "actor_identity": self.actor_identity.to_dict(),
            "capability_identity": (
                None
                if self.capability_identity is None
                else self.capability_identity.to_dict()
            ),
            "predecessor_validity_event_reference": (
                None
                if self.predecessor_validity_event_reference is None
                else self.predecessor_validity_event_reference.to_dict()
            ),
            "reason": self.reason,
            "scope": self.scope,
        }

    def _validate(self) -> None:
        try:
            validity_event_id = self.validity_event_id
            artifact_reference = self.artifact_reference
            status = self.status
            recorded_at = self.recorded_at
            effective_at = self.effective_at
            actor_identity = self.actor_identity
            capability_identity = self.capability_identity
            predecessor_reference = self.predecessor_validity_event_reference
            reason = self.reason
            scope = self.scope
            schema_version = self.schema_version
            fingerprint = self.fingerprint
        except AttributeError as error:
            raise ValueError(
                "evidence validity event retained state is incomplete"
            ) from error
        _visible_ascii(validity_event_id, "validity_event_id", 256)
        _copy_artifact_reference(artifact_reference)
        if type(status) is not EvidenceValidityStatus:
            raise ValueError("evidence validity status is invalid")
        _require_canonical_timestamp(recorded_at, "recorded_at")
        _require_canonical_timestamp(effective_at, "effective_at")
        _copy_identity_reference(actor_identity)
        _copy_optional_identity_reference(
            capability_identity,
            "capability_identity",
        )
        copied_predecessor = _copy_optional_validity_reference(predecessor_reference)
        if copied_predecessor is not None:
            if copied_predecessor.artifact_reference != artifact_reference:
                raise ValueError(
                    "validity predecessor must retain artifact correspondence"
                )
            if copied_predecessor.scope != scope:
                raise ValueError(
                    "validity predecessor must retain scope correspondence"
                )
            if copied_predecessor.validity_event_id == validity_event_id:
                raise ValueError("validity predecessor must remain distinct")
            if copied_predecessor.recorded_at > recorded_at:
                raise ValueError("validity predecessor must remain earlier")
            if copied_predecessor.effective_at > effective_at:
                raise ValueError(
                    "validity successor effective_at must not precede its predecessor"
                )
            if (
                copied_predecessor.status.value in _TERMINAL_VALIDITY_STATUSES
                and status is EvidenceValidityStatus.ACTIVE
            ):
                raise ValueError(
                    "terminal validity cannot be reactivated for an artifact version"
                )
        _reason(reason)
        _visible_ascii(scope, "scope", 256)
        if schema_version != EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION:
            raise ValueError("evidence validity event schema_version is invalid")
        retained_fingerprint = _fingerprint(fingerprint, "fingerprint")
        if retained_fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError(
                "evidence validity event fingerprint does not match content"
            )

    def reference(self) -> EvidenceValidityReference:
        """Return an exact immutable reference to this validity event."""

        self._validate()
        return EvidenceValidityReference(
            validity_event_id=self.validity_event_id,
            artifact_reference=self.artifact_reference,
            status=self.status,
            scope=self.scope,
            recorded_at=self.recorded_at,
            effective_at=self.effective_at,
            validity_event_fingerprint=self.fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical immutable validity-event projection."""

        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


def create_evidence_validity_event(
    *,
    validity_event_id: str,
    artifact_reference: EvidenceArtifactReference,
    status: EvidenceValidityStatus,
    recorded_at: datetime,
    effective_at: datetime,
    actor_identity: EvidenceIdentityReference,
    reason: str,
    scope: str,
    capability_identity: EvidenceIdentityReference | None = None,
    predecessor: EvidenceValidityEvent | None = None,
) -> EvidenceValidityEvent:
    """Create one append-only event without mutating its artifact."""

    predecessor_reference: EvidenceValidityReference | None = None
    if predecessor is not None:
        if type(predecessor) is not EvidenceValidityEvent:
            raise TypeError("predecessor must be an EvidenceValidityEvent")
        predecessor._validate()
        predecessor_reference = predecessor.reference()
    return EvidenceValidityEvent._create(
        validity_event_id=validity_event_id,
        artifact_reference=artifact_reference,
        status=status,
        recorded_at=recorded_at,
        effective_at=effective_at,
        actor_identity=actor_identity,
        capability_identity=capability_identity,
        predecessor_validity_event_reference=predecessor_reference,
        reason=reason,
        scope=scope,
        seal=_VALIDITY_EVENT_SEAL,
    )


def evaluate_evidence_validity_as_of(
    *,
    artifact_reference: EvidenceArtifactReference,
    scope: str,
    validity_events: tuple[EvidenceValidityEvent, ...],
    knowledge_as_of: datetime,
    effective_as_of: datetime,
) -> EvidenceValidityReference | None:
    """Select the effective validity event under explicit historical cutoffs."""

    artifact = _copy_artifact_reference(artifact_reference)
    exact_scope = _visible_ascii(scope, "scope", 256)
    events = _validity_event_tuple(validity_events)
    knowledge_cutoff = _timestamp(knowledge_as_of, "knowledge_as_of")
    effective_cutoff = _timestamp(effective_as_of, "effective_as_of")
    eligible = tuple(
        event
        for event in events
        if event.artifact_reference == artifact
        and event.scope == exact_scope
        and event.recorded_at <= knowledge_cutoff
        and event.effective_at <= effective_cutoff
    )
    selected, _, failure = _resolve_validity_lineage(eligible)
    if failure is not None or selected is None:
        return None
    return selected.reference()


def _resolve_validity_lineage(
    eligible: tuple[EvidenceValidityEvent, ...],
) -> tuple[
    EvidenceValidityEvent | None,
    tuple[EvidenceValidityReference, ...],
    str | None,
]:
    """Resolve exact predecessor lineage for already cutoff-filtered events."""

    if not eligible:
        return None, (), "Required ACTIVE validity event is missing."
    by_identity = {
        (event.validity_event_id, event.fingerprint): event for event in eligible
    }
    successors: dict[tuple[str, str], tuple[str, str]] = {}
    lineage: list[EvidenceValidityReference] = []
    for event in eligible:
        predecessor_reference = event.predecessor_validity_event_reference
        if predecessor_reference is None:
            continue
        predecessor_identity = (
            predecessor_reference.validity_event_id,
            predecessor_reference.validity_event_fingerprint,
        )
        successor_identity = (event.validity_event_id, event.fingerprint)
        predecessor = by_identity.get(predecessor_identity)
        if predecessor is None or predecessor.reference() != predecessor_reference:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Validity predecessor lineage has an unresolved predecessor.",
            )
        if event.effective_at < predecessor.effective_at:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Validity predecessor lineage moves effective_at backward.",
            )
        if (
            predecessor.status.value in _TERMINAL_VALIDITY_STATUSES
            and event.status is EvidenceValidityStatus.ACTIVE
        ):
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Terminal validity cannot be reactivated.",
            )
        retained = successors.get(predecessor_identity)
        if retained is not None and retained != successor_identity:
            return (
                None,
                tuple(sorted(lineage, key=lambda item: item.fingerprint)),
                "Forked validity predecessor lineage fails closed.",
            )
        successors[predecessor_identity] = successor_identity
        lineage.append(predecessor.reference())
    if _has_validity_cycle(successors):
        return (
            None,
            tuple(sorted(lineage, key=lambda item: item.fingerprint)),
            "Cyclic validity predecessor lineage fails closed.",
        )
    remaining = tuple(
        event for identity, event in by_identity.items() if identity not in successors
    )
    if not remaining:
        return (
            None,
            tuple(sorted(lineage, key=lambda item: item.fingerprint)),
            "No validity event remains after predecessor resolution.",
        )
    precedence = max((event.effective_at, event.recorded_at) for event in remaining)
    co_precedent = tuple(
        event
        for event in remaining
        if (event.effective_at, event.recorded_at) == precedence
    )
    if len(co_precedent) != 1:
        return (
            None,
            tuple(sorted(lineage, key=lambda item: item.fingerprint)),
            "Conflicting co-precedent validity events fail closed.",
        )
    selected = co_precedent[0]
    if selected.status is EvidenceValidityStatus.ACTIVE and any(
        event.status.value in _TERMINAL_VALIDITY_STATUSES
        and (event.effective_at, event.recorded_at) < precedence
        for event in eligible
    ):
        return (
            selected,
            tuple(sorted(lineage, key=lambda item: item.fingerprint)),
            "Terminal validity cannot be reactivated.",
        )
    return (
        selected,
        tuple(sorted(lineage, key=lambda item: item.fingerprint)),
        None,
    )


def _has_validity_cycle(
    successors: dict[tuple[str, str], tuple[str, str]],
) -> bool:
    for start in successors:
        seen: set[tuple[str, str]] = set()
        current = start
        while current in successors:
            if current in seen:
                return True
            seen.add(current)
            current = successors[current]
    return False


def _validity_event_tuple(value: object) -> tuple[EvidenceValidityEvent, ...]:
    if type(value) is not tuple:
        raise TypeError("validity_events must be an exact tuple")
    events: list[EvidenceValidityEvent] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not EvidenceValidityEvent:
            raise TypeError("validity_events must contain EvidenceValidityEvent values")
        item._validate()
        events.append(item)
    event_ids = tuple(event.validity_event_id for event in events)
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("validity_events must not duplicate event identities")
    return tuple(
        sorted(
            events,
            key=lambda event: (
                event.artifact_reference.artifact_id,
                event.artifact_reference.artifact_version,
                event.scope,
                event.effective_at,
                event.recorded_at,
                event.validity_event_id,
            ),
        )
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
        raise TypeError("actor_identity must be an EvidenceIdentityReference")
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


def _copy_optional_validity_reference(
    value: object,
) -> EvidenceValidityReference | None:
    if value is None:
        return None
    if type(value) is not EvidenceValidityReference:
        raise TypeError(
            "predecessor_validity_event_reference must be an EvidenceValidityReference"
        )
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
    "EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION",
    "EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION",
    "EvidenceValidityEvent",
    "EvidenceValidityReference",
    "EvidenceValidityStatus",
    "create_evidence_validity_event",
    "evaluate_evidence_validity_as_of",
]
