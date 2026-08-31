from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
from inspect import signature

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)
from market_platform.evidence.validity import (
    EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION,
    EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION,
    EvidenceValidityEvent,
    EvidenceValidityReference,
    EvidenceValidityStatus,
    create_evidence_validity_event,
    evaluate_evidence_validity_as_of,
)

_SCOPE = "specialist.market_quote"
_BASE_TIME = datetime(2026, 8, 25, 20, tzinfo=UTC)


def _artifact_reference() -> EvidenceArtifactReference:
    return EvidenceArtifactReference(
        artifact_id="market.quote.spy.2026-08-25",
        artifact_version="1",
        artifact_fingerprint=canonical_fingerprint(
            {"schema_version": "evidence_artifact/v1", "artifact": "SPY"}
        ),
        information_class=EvidenceInformationClass.SOURCE_MEASUREMENT,
        authority=EvidenceAuthority.EXTERNAL_ORIGIN,
    )


def _actor() -> EvidenceIdentityReference:
    return EvidenceIdentityReference(
        namespace="actor",
        identity_id="evidence_validity_service",
        identity_version="1",
    )


def _capability(
    identity_id: str = "record_evidence_validity",
) -> EvidenceIdentityReference:
    return EvidenceIdentityReference(
        namespace="capability",
        identity_id=identity_id,
        identity_version="1",
    )


def _event(
    status: EvidenceValidityStatus,
    *,
    suffix: str,
    effective_at: datetime,
    recorded_at: datetime,
    artifact_reference: EvidenceArtifactReference | None = None,
    actor_identity: EvidenceIdentityReference | None = None,
    capability_identity: EvidenceIdentityReference | None = None,
    predecessor: EvidenceValidityEvent | None = None,
) -> EvidenceValidityEvent:
    return create_evidence_validity_event(
        validity_event_id=f"validity.market.quote.spy.{suffix}",
        artifact_reference=artifact_reference or _artifact_reference(),
        status=status,
        recorded_at=recorded_at,
        effective_at=effective_at,
        actor_identity=actor_identity or _actor(),
        capability_identity=capability_identity,
        reason=f"Validity became {status.value.lower()}.",
        scope=_SCOPE,
        predecessor=predecessor,
    )


def _evaluate(
    events: tuple[EvidenceValidityEvent, ...],
    *,
    knowledge_as_of: datetime = _BASE_TIME + timedelta(hours=4),
    effective_as_of: datetime = _BASE_TIME + timedelta(hours=4),
) -> EvidenceValidityReference | None:
    return evaluate_evidence_validity_as_of(
        artifact_reference=_artifact_reference(),
        scope=_SCOPE,
        validity_events=events,
        knowledge_as_of=knowledge_as_of,
        effective_as_of=effective_as_of,
    )


def test_validity_status_has_exact_adr_0035_states() -> None:
    assert tuple(EvidenceValidityStatus) == (
        EvidenceValidityStatus.ACTIVE,
        EvidenceValidityStatus.EXPIRED,
        EvidenceValidityStatus.WITHDRAWN,
        EvidenceValidityStatus.REVOKED,
    )
    assert tuple(status.value for status in EvidenceValidityStatus) == (
        "ACTIVE",
        "EXPIRED",
        "WITHDRAWN",
        "REVOKED",
    )
    with pytest.raises(ValueError):
        EvidenceValidityStatus("active")


def test_validity_event_and_reference_are_exact_frozen_slotted_contracts() -> None:
    with pytest.raises(TypeError, match="factory-created"):
        EvidenceValidityEvent()
    event = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    reference = event.reference()

    assert tuple(item.name for item in fields(EvidenceValidityEvent)) == (
        "validity_event_id",
        "artifact_reference",
        "status",
        "recorded_at",
        "effective_at",
        "actor_identity",
        "capability_identity",
        "predecessor_validity_event_reference",
        "reason",
        "scope",
        "schema_version",
        "fingerprint",
    )
    assert tuple(item.name for item in fields(EvidenceValidityReference)) == (
        "validity_event_id",
        "artifact_reference",
        "status",
        "scope",
        "recorded_at",
        "effective_at",
        "validity_event_fingerprint",
        "schema_version",
        "fingerprint",
    )
    assert event.schema_version == EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION
    assert EVIDENCE_VALIDITY_EVENT_SCHEMA_VERSION == "evidence_validity_event/v3"
    assert reference.schema_version == EVIDENCE_VALIDITY_REFERENCE_SCHEMA_VERSION
    assert reference.validity_event_fingerprint == event.fingerprint
    assert event.capability_identity is None
    assert not hasattr(event, "__dict__")
    assert not hasattr(reference, "__dict__")
    with pytest.raises(FrozenInstanceError):
        event.status = EvidenceValidityStatus.REVOKED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        reference.status = EvidenceValidityStatus.REVOKED  # type: ignore[misc]


def test_validity_fingerprints_are_canonical_stable_and_timezone_normalized() -> None:
    offset = timezone(timedelta(hours=8))
    baseline = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    equivalent = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME.astimezone(offset),
        recorded_at=(_BASE_TIME + timedelta(minutes=1)).astimezone(offset),
    )
    projection = baseline.to_dict()
    retained_fingerprint = projection.pop("fingerprint")

    assert retained_fingerprint == canonical_fingerprint(projection)
    assert baseline.fingerprint == equivalent.fingerprint
    assert baseline.reference().fingerprint == equivalent.reference().fingerprint


def test_validity_retains_separate_actor_and_optional_capability_provenance() -> None:
    actor = _actor()
    capability = _capability()
    event = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active-with-capability",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
        actor_identity=actor,
        capability_identity=capability,
    )
    object.__setattr__(actor, "identity_id", "tampered-actor")
    object.__setattr__(capability, "identity_id", "tampered-capability")

    assert event.actor_identity.identity_id == "evidence_validity_service"
    assert event.capability_identity is not None
    assert event.capability_identity.identity_id == "record_evidence_validity"
    assert event.actor_identity.namespace == "actor"
    assert event.capability_identity.namespace == "capability"


def test_validity_fingerprint_changes_with_capability_provenance() -> None:
    without_capability = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    with_capability = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
        capability_identity=_capability(),
    )
    changed_capability = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
        capability_identity=_capability("record_evidence_validity_v2"),
    )

    assert (
        len(
            {
                without_capability.fingerprint,
                with_capability.fingerprint,
                changed_capability.fingerprint,
            }
        )
        == 3
    )


def test_validity_defensively_revalidates_retained_capability_identity() -> None:
    event = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active-with-capability",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
        capability_identity=_capability(),
    )
    assert event.capability_identity is not None
    object.__setattr__(
        event.capability_identity,
        "identity_id",
        "tampered-capability",
    )

    with pytest.raises(ValueError, match="fingerprint does not match identity"):
        event.to_dict()


@pytest.mark.parametrize(
    "terminal_status",
    [
        EvidenceValidityStatus.EXPIRED,
        EvidenceValidityStatus.WITHDRAWN,
        EvidenceValidityStatus.REVOKED,
    ],
)
def test_lifecycle_transitions_are_append_only_and_do_not_mutate_artifact(
    terminal_status: EvidenceValidityStatus,
) -> None:
    artifact_reference = _artifact_reference()
    artifact_before = artifact_reference.to_dict()
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
        artifact_reference=artifact_reference,
    )
    terminal = _event(
        terminal_status,
        suffix=terminal_status.value.lower(),
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=1),
        artifact_reference=artifact_reference,
        predecessor=active,
    )
    active_before = active.to_dict()

    selected = _evaluate((active, terminal))

    assert selected is not None
    assert selected.status is terminal_status
    assert selected.validity_event_fingerprint == terminal.fingerprint
    assert artifact_reference.to_dict() == artifact_before
    assert active.to_dict() == active_before


def test_validity_precedence_is_effective_time_then_recorded_time() -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    expired = _event(
        EvidenceValidityStatus.EXPIRED,
        suffix="expired",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=1),
    )
    revoked = _event(
        EvidenceValidityStatus.REVOKED,
        suffix="revoked",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=2),
    )

    selected = _evaluate((revoked, active, expired))

    assert selected is not None
    assert selected.validity_event_id == revoked.validity_event_id
    assert selected.status is EvidenceValidityStatus.REVOKED


def test_conflicting_co_precedent_validity_events_fail_closed() -> None:
    expired = _event(
        EvidenceValidityStatus.EXPIRED,
        suffix="expired",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=1),
    )
    revoked = _event(
        EvidenceValidityStatus.REVOKED,
        suffix="revoked",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=1),
    )

    assert _evaluate((expired, revoked)) is None


def test_historical_replay_separates_knowledge_and_effective_cutoffs() -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    revoked = _event(
        EvidenceValidityStatus.REVOKED,
        suffix="revoked",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=2),
    )
    before_knowledge = _evaluate(
        (revoked, active),
        knowledge_as_of=_BASE_TIME + timedelta(hours=1, minutes=30),
        effective_as_of=_BASE_TIME + timedelta(hours=3),
    )
    before_effective = _evaluate(
        (revoked, active),
        knowledge_as_of=_BASE_TIME + timedelta(hours=3),
        effective_as_of=_BASE_TIME + timedelta(minutes=30),
    )
    after_both = _evaluate((active, revoked))
    replay = _evaluate(
        (revoked, active),
        knowledge_as_of=_BASE_TIME + timedelta(hours=1, minutes=30),
        effective_as_of=_BASE_TIME + timedelta(hours=3),
    )

    assert before_knowledge is not None
    assert before_effective is not None
    assert after_both is not None
    assert before_knowledge.status is EvidenceValidityStatus.ACTIVE
    assert before_effective.status is EvidenceValidityStatus.ACTIVE
    assert after_both.status is EvidenceValidityStatus.REVOKED
    assert replay is not None
    assert replay.fingerprint == before_knowledge.fingerprint


def test_reactivation_of_a_terminal_artifact_version_fails_closed() -> None:
    expired = _event(
        EvidenceValidityStatus.EXPIRED,
        suffix="expired",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=1),
    )
    reactivated = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="reactivated",
        effective_at=_BASE_TIME + timedelta(hours=2),
        recorded_at=_BASE_TIME + timedelta(hours=2, minutes=1),
    )

    assert _evaluate((expired, reactivated)) is None


def test_validity_rejects_mutable_inputs_and_copies_nested_identity() -> None:
    actor = _actor()
    event = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
        actor_identity=actor,
    )
    object.__setattr__(actor, "identity_id", "tampered")

    assert event.actor_identity.identity_id == "evidence_validity_service"
    with pytest.raises(TypeError, match="validity_events must be an exact tuple"):
        evaluate_evidence_validity_as_of(
            artifact_reference=_artifact_reference(),
            scope=_SCOPE,
            validity_events=[event],  # type: ignore[arg-type]
            knowledge_as_of=_BASE_TIME + timedelta(hours=1),
            effective_as_of=_BASE_TIME + timedelta(hours=1),
        )


def test_validity_has_no_hidden_clock_or_forbidden_semantics() -> None:
    parameters = signature(evaluate_evidence_validity_as_of).parameters
    forbidden = {
        "interpretation",
        "confidence",
        "recommendation",
        "ranking",
        "trading_action",
        "market_meaning",
    }

    assert parameters["knowledge_as_of"].default is parameters["knowledge_as_of"].empty
    assert parameters["effective_as_of"].default is parameters["effective_as_of"].empty
    assert forbidden.isdisjoint(EvidenceValidityEvent.__dataclass_fields__)
    assert forbidden.isdisjoint(EvidenceValidityReference.__dataclass_fields__)
    assert _evaluate(()) is None


def test_validity_predecessor_lineage_is_exact_and_preserves_capability() -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    terminal = _event(
        EvidenceValidityStatus.REVOKED,
        suffix="revoked",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=1),
        capability_identity=_capability(),
        predecessor=active,
    )

    selected = _evaluate((terminal, active))

    assert selected == terminal.reference()
    assert terminal.predecessor_validity_event_reference == active.reference()
    assert terminal.capability_identity == _capability()


def test_missing_or_forked_validity_predecessor_lineage_fails_closed() -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    terminal_events = tuple(
        _event(
            status,
            suffix=status.value.lower(),
            effective_at=_BASE_TIME + timedelta(hours=index),
            recorded_at=_BASE_TIME + timedelta(hours=index, minutes=1),
            predecessor=active,
        )
        for index, status in enumerate(
            (
                EvidenceValidityStatus.EXPIRED,
                EvidenceValidityStatus.REVOKED,
            ),
            start=1,
        )
    )

    assert _evaluate((terminal_events[0],)) is None
    assert _evaluate((active, *terminal_events)) is None


def test_tampered_cyclic_validity_lineage_fails_closed_before_resolution() -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="active",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    revoked = _event(
        EvidenceValidityStatus.REVOKED,
        suffix="revoked",
        effective_at=_BASE_TIME + timedelta(hours=1),
        recorded_at=_BASE_TIME + timedelta(hours=1, minutes=1),
        predecessor=active,
    )
    object.__setattr__(
        active,
        "predecessor_validity_event_reference",
        revoked.reference(),
    )

    with pytest.raises(ValueError, match="must remain earlier"):
        _evaluate((active, revoked))


@pytest.mark.parametrize(
    "terminal_status",
    (EvidenceValidityStatus.REVOKED, EvidenceValidityStatus.WITHDRAWN),
)
def test_terminal_state_cannot_be_reactivated_by_backdated_successor(
    terminal_status: EvidenceValidityStatus,
) -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="initial",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    terminal = _event(
        terminal_status,
        suffix=terminal_status.value.lower(),
        effective_at=_BASE_TIME + timedelta(minutes=30),
        recorded_at=_BASE_TIME + timedelta(minutes=31),
        predecessor=active,
    )

    with pytest.raises(ValueError, match="must not precede its predecessor"):
        _event(
            EvidenceValidityStatus.ACTIVE,
            suffix="backdated-reactivation",
            effective_at=_BASE_TIME + timedelta(minutes=6),
            recorded_at=_BASE_TIME + timedelta(minutes=40),
            predecessor=terminal,
        )


def test_terminal_state_cannot_be_reactivated_even_at_later_effective_time() -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="initial",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    terminal = _event(
        EvidenceValidityStatus.REVOKED,
        suffix="revoked",
        effective_at=_BASE_TIME + timedelta(minutes=30),
        recorded_at=_BASE_TIME + timedelta(minutes=31),
        predecessor=active,
    )

    with pytest.raises(ValueError, match="cannot be reactivated"):
        _event(
            EvidenceValidityStatus.ACTIVE,
            suffix="later-reactivation",
            effective_at=_BASE_TIME + timedelta(minutes=40),
            recorded_at=_BASE_TIME + timedelta(minutes=41),
            predecessor=terminal,
        )


def test_non_monotonic_non_terminal_predecessor_time_fails_closed() -> None:
    active = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="initial",
        effective_at=_BASE_TIME + timedelta(minutes=10),
        recorded_at=_BASE_TIME + timedelta(minutes=11),
    )

    with pytest.raises(ValueError, match="must not precede its predecessor"):
        _event(
            EvidenceValidityStatus.ACTIVE,
            suffix="backdated-active",
            effective_at=_BASE_TIME + timedelta(minutes=9),
            recorded_at=_BASE_TIME + timedelta(minutes=12),
            predecessor=active,
        )


def test_monotonic_non_terminal_validity_lineage_still_resolves() -> None:
    first = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="first",
        effective_at=_BASE_TIME,
        recorded_at=_BASE_TIME + timedelta(minutes=1),
    )
    second = _event(
        EvidenceValidityStatus.ACTIVE,
        suffix="second",
        effective_at=_BASE_TIME + timedelta(minutes=10),
        recorded_at=_BASE_TIME + timedelta(minutes=11),
        predecessor=first,
    )

    assert _evaluate((first, second)) == second.reference()
