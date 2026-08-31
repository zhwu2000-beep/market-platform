from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
from inspect import signature

import pytest
from evidence_test_support import (
    create_governed_test_artifact as _create_evidence_artifact,
)

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence.models import (
    EvidenceArtifact,
    EvidenceProvenance,
    EvidenceTemporalIdentity,
)
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceContractReference,
    EvidenceIdentityReference,
    EvidenceSourceReference,
    EvidenceSubjectReference,
)
from market_platform.evidence.supersession import (
    EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION,
    EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION,
    EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION,
    EvidenceArtifactSupersessionLink,
    EvidenceArtifactSupersessionLinkReference,
    EvidenceArtifactSupersessionResolution,
    EvidenceArtifactSupersessionResolutionError,
    create_evidence_artifact_supersession_link,
    resolve_evidence_artifact_supersession_as_of,
)

_SCOPE = "specialist.market_quote"
_OTHER_SCOPE = "specialist.market_news"
_BASE_TIME = datetime(2026, 8, 25, 20, tzinfo=UTC)


def _identity(
    namespace: str,
    identity_id: str,
) -> EvidenceIdentityReference:
    return EvidenceIdentityReference(
        namespace=namespace,
        identity_id=identity_id,
        identity_version="1",
    )


def _artifact(
    version: str,
    *,
    predecessors: tuple[EvidenceArtifactReference, ...] = (),
) -> EvidenceArtifact:
    source = EvidenceSourceReference(
        namespace="provider",
        source_id="market_feed",
        source_version="1",
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )
    return _create_evidence_artifact(
        artifact_id="market.quote.spy",
        artifact_version=version,
        evidence_type="market.quote",
        subjects=(
            EvidenceSubjectReference(
                namespace="instrument",
                subject_id="SPY",
                subject_version="1",
            ),
        ),
        temporal_identity=EvidenceTemporalIdentity(
            platform_received_at=_BASE_TIME,
            artifact_created_at=_BASE_TIME + timedelta(minutes=1),
            observed_at=_BASE_TIME - timedelta(minutes=1),
        ),
        provenance=EvidenceProvenance(
            origin=source,
            producer=_identity("producer", "market_feed_adapter"),
            source_references=(source,),
            predecessors=predecessors,
        ),
        governing_contract=EvidenceContractReference(
            namespace="evidence_contract",
            contract_id="market_quote",
            contract_version="1",
            information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        ),
        material_schema_version="market_quote/v1",
        material_fingerprint=canonical_fingerprint(
            {
                "schema_version": "market_quote/v1",
                "artifact": "SPY",
                "version": version,
            }
        ),
    )


def _link(
    predecessor: EvidenceArtifactReference,
    successor: EvidenceArtifactReference,
    *,
    suffix: str,
    scope: str = _SCOPE,
    effective_at: datetime = _BASE_TIME + timedelta(hours=1),
    recorded_at: datetime = _BASE_TIME + timedelta(hours=2),
    capability: EvidenceIdentityReference | None = None,
) -> EvidenceArtifactSupersessionLink:
    return create_evidence_artifact_supersession_link(
        supersession_link_id=f"supersession.market.quote.spy.{suffix}",
        predecessor_artifact_reference=predecessor,
        successor_artifact_reference=successor,
        scope=scope,
        reason="A source revision replaced the earlier artifact for this scope.",
        recorded_at=recorded_at,
        effective_at=effective_at,
        responsible_actor_identity=_identity("actor", "evidence_curator"),
        responsible_capability_identity=capability,
    )


def _resolve(
    requested: EvidenceArtifactReference,
    artifacts: tuple[EvidenceArtifactReference, ...],
    links: tuple[EvidenceArtifactSupersessionLink, ...],
    *,
    scope: str = _SCOPE,
    knowledge_as_of: datetime = _BASE_TIME + timedelta(hours=3),
    effective_as_of: datetime = _BASE_TIME + timedelta(hours=3),
) -> EvidenceArtifactSupersessionResolution:
    return resolve_evidence_artifact_supersession_as_of(
        artifact_reference=requested,
        scope=scope,
        artifact_references=artifacts,
        supersession_links=links,
        knowledge_as_of=knowledge_as_of,
        effective_as_of=effective_as_of,
    )


def test_supersession_contracts_are_exact_frozen_and_slotted() -> None:
    predecessor = _artifact("1")
    successor = _artifact("2")
    capability = _identity("capability", "record_artifact_supersession")
    link = _link(
        predecessor.reference(),
        successor.reference(),
        suffix="v1-v2",
        capability=capability,
    )
    reference = link.reference()
    resolution = _resolve(
        predecessor.reference(),
        (predecessor.reference(), successor.reference()),
        (link,),
    )

    with pytest.raises(TypeError, match="factory-created"):
        EvidenceArtifactSupersessionLink()
    assert tuple(item.name for item in fields(EvidenceArtifactSupersessionLink)) == (
        "supersession_link_id",
        "predecessor_artifact_reference",
        "successor_artifact_reference",
        "scope",
        "reason",
        "recorded_at",
        "effective_at",
        "responsible_actor_identity",
        "responsible_capability_identity",
        "schema_version",
        "fingerprint",
    )
    assert link.schema_version == EVIDENCE_ARTIFACT_SUPERSESSION_LINK_SCHEMA_VERSION
    assert (
        reference.schema_version
        == EVIDENCE_ARTIFACT_SUPERSESSION_LINK_REFERENCE_SCHEMA_VERSION
    )
    assert (
        resolution.schema_version
        == EVIDENCE_ARTIFACT_SUPERSESSION_RESOLUTION_SCHEMA_VERSION
    )
    assert link.responsible_actor_identity.namespace == "actor"
    assert link.responsible_capability_identity is not None
    assert link.responsible_capability_identity.namespace == "capability"
    assert not hasattr(link, "__dict__")
    assert not hasattr(reference, "__dict__")
    assert not hasattr(resolution, "__dict__")
    assert not hasattr(resolution, "fingerprint")
    with pytest.raises(FrozenInstanceError):
        link.scope = _OTHER_SCOPE  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        reference.scope = _OTHER_SCOPE  # type: ignore[misc]


def test_supersession_binds_exact_artifact_fingerprints_and_copies_identities() -> None:
    predecessor = _artifact("1").reference()
    successor = _artifact("2").reference()
    actor = _identity("actor", "evidence_curator")
    capability = _identity("capability", "record_artifact_supersession")
    link = create_evidence_artifact_supersession_link(
        supersession_link_id="supersession.market.quote.spy.v1-v2",
        predecessor_artifact_reference=predecessor,
        successor_artifact_reference=successor,
        scope=_SCOPE,
        reason="A source revision replaced the earlier artifact for this scope.",
        recorded_at=_BASE_TIME + timedelta(hours=2),
        effective_at=_BASE_TIME + timedelta(hours=1),
        responsible_actor_identity=actor,
        responsible_capability_identity=capability,
    )
    object.__setattr__(predecessor, "artifact_version", "tampered")
    object.__setattr__(successor, "artifact_version", "tampered")
    object.__setattr__(actor, "identity_id", "tampered")
    object.__setattr__(capability, "identity_id", "tampered")

    assert link.predecessor_artifact_reference.artifact_version == "1"
    assert link.successor_artifact_reference.artifact_version == "2"
    assert (
        link.reference().predecessor_artifact_reference.artifact_fingerprint
        == link.predecessor_artifact_reference.artifact_fingerprint
    )
    assert (
        link.reference().successor_artifact_reference.artifact_fingerprint
        == link.successor_artifact_reference.artifact_fingerprint
    )
    assert link.responsible_actor_identity.identity_id == "evidence_curator"
    assert link.responsible_capability_identity is not None
    assert (
        link.responsible_capability_identity.identity_id
        == "record_artifact_supersession"
    )


def test_supersession_fingerprint_is_deterministic_and_includes_capability() -> None:
    offset = timezone(timedelta(hours=8))
    predecessor = _artifact("1").reference()
    successor = _artifact("2").reference()
    baseline = _link(
        predecessor,
        successor,
        suffix="v1-v2",
        capability=_identity("capability", "record_artifact_supersession"),
    )
    equivalent = _link(
        predecessor,
        successor,
        suffix="v1-v2",
        effective_at=(_BASE_TIME + timedelta(hours=1)).astimezone(offset),
        recorded_at=(_BASE_TIME + timedelta(hours=2)).astimezone(offset),
        capability=_identity("capability", "record_artifact_supersession"),
    )
    changed_capability = _link(
        predecessor,
        successor,
        suffix="v1-v2",
        capability=_identity("capability", "record_artifact_supersession_v2"),
    )
    projection = baseline.to_dict()
    retained_fingerprint = projection.pop("fingerprint")

    assert retained_fingerprint == canonical_fingerprint(projection)
    assert baseline.fingerprint == equivalent.fingerprint
    assert baseline.reference().fingerprint == equivalent.reference().fingerprint
    assert baseline.fingerprint != changed_capability.fingerprint


def test_self_supersession_rejects_same_exact_artifact_version() -> None:
    predecessor = _artifact("1").reference()
    conflicting_fingerprint = EvidenceArtifactReference(
        artifact_id=predecessor.artifact_id,
        artifact_version=predecessor.artifact_version,
        artifact_fingerprint=canonical_fingerprint(
            {
                "schema_version": "market_quote/v1",
                "conflicting": "material",
            }
        ),
        information_class=predecessor.information_class,
        authority=predecessor.authority,
    )

    with pytest.raises(ValueError, match="distinct exact artifact versions"):
        _link(predecessor, predecessor, suffix="self")
    with pytest.raises(ValueError, match="distinct exact artifact versions"):
        _link(predecessor, conflicting_fingerprint, suffix="identity-collision")


def test_scoped_supersession_respects_recorded_and_effective_cutoffs() -> None:
    predecessor = _artifact("1")
    successor = _artifact("2")
    link = _link(
        predecessor.reference(),
        successor.reference(),
        suffix="v1-v2",
    )
    artifacts = (predecessor.reference(), successor.reference())

    before_knowledge = _resolve(
        predecessor.reference(),
        artifacts,
        (link,),
        knowledge_as_of=_BASE_TIME + timedelta(hours=1, minutes=30),
        effective_as_of=_BASE_TIME + timedelta(hours=3),
    )
    before_effective = _resolve(
        predecessor.reference(),
        artifacts,
        (link,),
        knowledge_as_of=_BASE_TIME + timedelta(hours=3),
        effective_as_of=_BASE_TIME + timedelta(minutes=30),
    )
    after_both = _resolve(predecessor.reference(), artifacts, (link,))
    outside_scope = _resolve(
        predecessor.reference(),
        artifacts,
        (link,),
        scope=_OTHER_SCOPE,
    )
    replay = _resolve(
        predecessor.reference(),
        artifacts,
        (link,),
        knowledge_as_of=_BASE_TIME + timedelta(hours=1, minutes=30),
        effective_as_of=_BASE_TIME + timedelta(hours=3),
    )

    assert before_knowledge.resolved_artifact_reference == predecessor.reference()
    assert before_effective.resolved_artifact_reference == predecessor.reference()
    assert outside_scope.resolved_artifact_reference == predecessor.reference()
    assert not before_knowledge.applied_supersession_link_references
    assert after_both.resolved_artifact_reference == successor.reference()
    assert after_both.applied_supersession_link_references == (link.reference(),)
    assert replay.to_dict() == before_knowledge.to_dict()


def test_resolution_preserves_exact_multi_link_chain() -> None:
    first = _artifact("1")
    second = _artifact("2")
    third = _artifact("3")
    first_link = _link(
        first.reference(),
        second.reference(),
        suffix="v1-v2",
    )
    second_link = _link(
        second.reference(),
        third.reference(),
        suffix="v2-v3",
        effective_at=_BASE_TIME + timedelta(hours=2),
        recorded_at=_BASE_TIME + timedelta(hours=2, minutes=30),
    )

    resolution = _resolve(
        first.reference(),
        (third.reference(), first.reference(), second.reference()),
        (second_link, first_link),
    )

    assert resolution.resolved_artifact_reference == third.reference()
    assert resolution.applied_supersession_link_references == (
        first_link.reference(),
        second_link.reference(),
    )


def test_resolution_fails_closed_on_missing_referenced_lineage() -> None:
    predecessor = _artifact("1")
    successor = _artifact("2")
    link = _link(
        predecessor.reference(),
        successor.reference(),
        suffix="v1-v2",
    )

    with pytest.raises(
        EvidenceArtifactSupersessionResolutionError,
        match="missing referenced lineage",
    ):
        _resolve(predecessor.reference(), (predecessor.reference(),), (link,))


def test_resolution_rejects_forks_and_co_precedent_links() -> None:
    predecessor = _artifact("1")
    successor = _artifact("2")
    forked_successor = _artifact("3")
    first = _link(
        predecessor.reference(),
        successor.reference(),
        suffix="v1-v2",
    )
    fork = _link(
        predecessor.reference(),
        forked_successor.reference(),
        suffix="v1-v3",
        effective_at=_BASE_TIME + timedelta(hours=2),
        recorded_at=_BASE_TIME + timedelta(hours=3),
    )
    duplicate = _link(
        predecessor.reference(),
        successor.reference(),
        suffix="v1-v2-duplicate",
    )
    artifacts = (
        predecessor.reference(),
        successor.reference(),
        forked_successor.reference(),
    )

    with pytest.raises(
        EvidenceArtifactSupersessionResolutionError,
        match="no unique successor",
    ):
        _resolve(
            predecessor.reference(),
            artifacts,
            (
                first,
                fork,
            ),
        )
    with pytest.raises(
        EvidenceArtifactSupersessionResolutionError,
        match="co-precedent",
    ):
        _resolve(predecessor.reference(), artifacts, (first, duplicate))


def test_resolution_rejects_applicable_cycles() -> None:
    predecessor = _artifact("1")
    successor = _artifact("2")
    forward = _link(
        predecessor.reference(),
        successor.reference(),
        suffix="v1-v2",
    )
    backward = _link(
        successor.reference(),
        predecessor.reference(),
        suffix="v2-v1",
        effective_at=_BASE_TIME + timedelta(hours=2),
        recorded_at=_BASE_TIME + timedelta(hours=2, minutes=30),
    )

    with pytest.raises(
        EvidenceArtifactSupersessionResolutionError,
        match="cycle",
    ):
        _resolve(
            predecessor.reference(),
            (predecessor.reference(), successor.reference()),
            (forward, backward),
        )


def test_construction_predecessors_do_not_imply_supersession() -> None:
    predecessor = _artifact("1")
    constructed_successor = _artifact(
        "2",
        predecessors=(predecessor.reference(),),
    )

    resolution = _resolve(
        predecessor.reference(),
        (predecessor.reference(), constructed_successor.reference()),
        (),
    )

    assert constructed_successor.provenance.predecessors == (predecessor.reference(),)
    assert resolution.resolved_artifact_reference == predecessor.reference()
    assert not resolution.applied_supersession_link_references


def test_supersession_is_independent_of_construction_and_mutates_no_artifact() -> None:
    predecessor = _artifact("1")
    independently_constructed_successor = _artifact("2")
    predecessor_before = predecessor.to_dict()
    successor_before = independently_constructed_successor.to_dict()
    link = _link(
        predecessor.reference(),
        independently_constructed_successor.reference(),
        suffix="v1-v2",
    )

    resolution = _resolve(
        predecessor.reference(),
        (
            predecessor.reference(),
            independently_constructed_successor.reference(),
        ),
        (link,),
    )

    assert not independently_constructed_successor.provenance.predecessors
    assert (
        resolution.resolved_artifact_reference
        == independently_constructed_successor.reference()
    )
    assert predecessor.to_dict() == predecessor_before
    assert independently_constructed_successor.to_dict() == successor_before


def test_supersession_defensively_revalidates_nested_identity() -> None:
    predecessor = _artifact("1")
    successor = _artifact("2")
    link = _link(
        predecessor.reference(),
        successor.reference(),
        suffix="v1-v2",
        capability=_identity("capability", "record_artifact_supersession"),
    )
    assert link.responsible_capability_identity is not None
    object.__setattr__(
        link.responsible_capability_identity,
        "identity_id",
        "tampered",
    )

    with pytest.raises(ValueError, match="fingerprint does not match identity"):
        link.to_dict()


def test_supersession_has_explicit_as_of_and_no_derived_judgment_fields() -> None:
    parameters = signature(resolve_evidence_artifact_supersession_as_of).parameters
    forbidden = {
        "interpretation",
        "confidence",
        "recommendation",
        "ranking",
        "trading",
        "market_meaning",
    }

    assert parameters["knowledge_as_of"].default is parameters["knowledge_as_of"].empty
    assert parameters["effective_as_of"].default is parameters["effective_as_of"].empty
    assert forbidden.isdisjoint(EvidenceArtifactSupersessionLink.__dataclass_fields__)
    assert forbidden.isdisjoint(
        EvidenceArtifactSupersessionLinkReference.__dataclass_fields__
    )
    assert forbidden.isdisjoint(
        EvidenceArtifactSupersessionResolution.__dataclass_fields__
    )
