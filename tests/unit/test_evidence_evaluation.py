from __future__ import annotations

from datetime import UTC, datetime

import pytest
from test_evidence_admission import (
    _CONCERNS,
    _SCOPE,
    _artifact,
    _freshness,
    _ruleset,
    _validation,
)

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.admission import (
    EvidenceAdmissionDisposition,
    _create_evidence_admission_state_from_resolution,
    create_evidence_admission_record,
)
from market_platform.evidence.evaluation import evaluate_evidence_admission_as_of
from market_platform.evidence.policy import EvidenceAdmissionRuleSet
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)
from market_platform.evidence.temporal import (
    EvidenceFreshnessEvaluationRecord,
    EvidenceFreshnessRule,
)
from market_platform.evidence.validation import (
    EvidenceValidationConcern,
    EvidenceValidationDisposition,
    create_evidence_validation_record,
)
from market_platform.evidence.validity import (
    EvidenceValidityStatus,
    create_evidence_validity_event,
)


def _actor(identity_id: str) -> EvidenceIdentityReference:
    return EvidenceIdentityReference(
        namespace="actor",
        identity_id=identity_id,
        identity_version="1",
    )


def _fabricate_freshness(
    record: EvidenceFreshnessEvaluationRecord,
    *,
    temporal_values: tuple[tuple[str, datetime], ...],
    freshness_rule: EvidenceFreshnessRule | None = None,
    artifact_reference: EvidenceArtifactReference | None = None,
) -> EvidenceFreshnessEvaluationRecord:
    if freshness_rule is not None:
        object.__setattr__(record, "freshness_rule", freshness_rule)
    if artifact_reference is not None:
        object.__setattr__(record, "artifact_reference", artifact_reference)
    object.__setattr__(record, "evaluated_temporal_values", temporal_values)
    object.__setattr__(
        record,
        "fingerprint",
        canonical_fingerprint(record._fingerprint_payload()),
    )
    record.to_dict()
    return record


def _admission(
    artifact,
    validations,
    admission_freshness,
    *,
    ruleset: EvidenceAdmissionRuleSet,
    suffix: str = "1",
    disposition: EvidenceAdmissionDisposition = EvidenceAdmissionDisposition.ADMITTED,
    recorded_at: datetime = datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
    effective_at: datetime = datetime(2026, 8, 25, 20, 5, 30, tzinfo=UTC),
    predecessor=None,
    capability_identity: EvidenceIdentityReference | None = None,
):
    return create_evidence_admission_record(
        admission_record_id=f"admission.quote.spy.{suffix}",
        artifact_reference=artifact.reference(),
        admission_ruleset=ruleset,
        selected_validation_record_references=tuple(
            record.reference() for record in validations
        ),
        admission_freshness_evaluation_reference=(
            None if admission_freshness is None else admission_freshness.reference()
        ),
        deciding_actor_identity=_actor("admission_reviewer"),
        deciding_capability_identity=capability_identity,
        disposition=disposition,
        recorded_at=recorded_at,
        effective_at=effective_at,
        findings=(f"Admission decision {suffix}.",),
        predecessor=predecessor,
    )


def _validity(
    artifact,
    status: EvidenceValidityStatus = EvidenceValidityStatus.ACTIVE,
    *,
    suffix: str = "1",
    recorded_at: datetime = datetime(2026, 8, 25, 20, 6, tzinfo=UTC),
    effective_at: datetime = datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
    predecessor=None,
    capability_identity: EvidenceIdentityReference | None = None,
):
    return create_evidence_validity_event(
        validity_event_id=f"validity.quote.spy.{suffix}",
        artifact_reference=artifact.reference(),
        status=status,
        recorded_at=recorded_at,
        effective_at=effective_at,
        actor_identity=_actor("validity_reviewer"),
        capability_identity=capability_identity,
        reason=f"Validity became {status.value}.",
        scope=_SCOPE,
        predecessor=predecessor,
    )


def _records(*, ruleset: EvidenceAdmissionRuleSet | None = None):
    artifact = _artifact()
    policy = _ruleset() if ruleset is None else ruleset
    validations = tuple(_validation(artifact, concern) for concern in _CONCERNS)
    admission_freshness = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
    )
    task_freshness = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
    )
    admission = _admission(
        artifact,
        validations,
        admission_freshness,
        ruleset=policy,
    )
    active = _validity(artifact)
    return (
        artifact,
        policy,
        validations,
        (admission_freshness, task_freshness),
        admission,
        active,
    )


def _evaluate(
    artifact,
    *,
    ruleset,
    validations,
    freshness,
    admissions,
    validity,
    knowledge_as_of: datetime = datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
    effective_as_of: datetime = datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
):
    return evaluate_evidence_admission_as_of(
        artifact=artifact,
        admission_scope=_SCOPE,
        validation_records=validations,
        freshness_evaluations=freshness,
        admission_records=admissions,
        validity_events=validity,
        admission_ruleset=ruleset,
        knowledge_as_of=knowledge_as_of,
        effective_as_of=effective_as_of,
    )


def test_full_evaluation_is_policy_bound_and_provenance_complete() -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()

    first = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=tuple(reversed(validations)),
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )
    second = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )

    assert first.is_consumable
    assert first.ruleset_reference == ruleset.reference()
    assert first.selected_admission_record_reference == admission.reference()
    assert first.admission_freshness_evaluation_reference == freshness[0].reference()
    assert first.task_freshness_evaluation_reference == freshness[1].reference()
    assert first.selected_validity_reference == active.reference()
    assert first.selected_validation_record_references == tuple(
        record.reference() for record in validations
    )
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize(
    "missing",
    (
        "all_validations",
        "one_validation",
        "admission_freshness",
        "task_freshness",
        "admission_record",
        "validity",
    ),
)
def test_package_state_factory_rejects_incomplete_admitted_state(
    missing: str,
) -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    values = {
        "artifact": artifact,
        "admission_scope": _SCOPE,
        "knowledge_as_of": datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        "effective_as_of": datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        "ruleset": ruleset,
        "disposition": EvidenceAdmissionDisposition.ADMITTED,
        "selected_validations": validations,
        "admission_freshness": freshness[0],
        "task_freshness": freshness[1],
        "selected_admission": admission,
        "selected_validity": active,
        "validation_supersession_references": (),
        "admission_predecessor_references": (),
        "validity_predecessor_references": (),
        "findings": ("Attempted fabricated state.",),
    }
    replacements = {
        "all_validations": ("selected_validations", ()),
        "one_validation": ("selected_validations", validations[:-1]),
        "admission_freshness": ("admission_freshness", None),
        "task_freshness": ("task_freshness", None),
        "admission_record": ("selected_admission", None),
        "validity": ("selected_validity", None),
    }
    field_name, replacement = replacements[missing]
    values[field_name] = replacement

    with pytest.raises(ValueError, match="ADMITTED state is incomplete"):
        _create_evidence_admission_state_from_resolution(**values)  # type: ignore[arg-type]


def test_package_state_factory_rejects_non_active_or_mismatched_constituents() -> None:
    artifact, ruleset, validations, freshness, admission, _ = _records()
    expired = _validity(artifact, EvidenceValidityStatus.EXPIRED)
    base = {
        "artifact": artifact,
        "admission_scope": _SCOPE,
        "knowledge_as_of": datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        "effective_as_of": datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        "ruleset": ruleset,
        "disposition": EvidenceAdmissionDisposition.ADMITTED,
        "selected_validations": validations,
        "admission_freshness": freshness[0],
        "task_freshness": freshness[1],
        "selected_admission": admission,
        "selected_validity": expired,
        "validation_supersession_references": (),
        "admission_predecessor_references": (),
        "validity_predecessor_references": (),
        "findings": ("Attempted fabricated state.",),
    }
    with pytest.raises(ValueError, match="ACTIVE validity"):
        _create_evidence_admission_state_from_resolution(**base)  # type: ignore[arg-type]

    mismatched_reference = EvidenceArtifactReference(
        artifact_id="other.artifact",
        artifact_version="1",
        artifact_fingerprint=canonical_fingerprint(
            {"schema_version": "other_artifact/v1", "value": "other"}
        ),
        information_class=artifact.information_class,
        authority=artifact.authority,
    )
    mismatched_validation = validations[0]
    object.__setattr__(
        mismatched_validation,
        "artifact_reference",
        mismatched_reference,
    )
    object.__setattr__(
        mismatched_validation,
        "fingerprint",
        canonical_fingerprint(mismatched_validation._fingerprint_payload()),
    )
    mismatched = dict(base)
    mismatched["selected_validations"] = (
        mismatched_validation,
        *validations[1:],
    )
    with pytest.raises(ValueError, match="correspondence"):
        _create_evidence_admission_state_from_resolution(  # type: ignore[arg-type]
            **mismatched
        )


def test_full_record_resolution_boolean_is_not_a_state_factory_input() -> None:
    artifact, ruleset, _, _, _, _ = _records()
    with pytest.raises(TypeError, match="full_record_resolution"):
        _create_evidence_admission_state_from_resolution(
            artifact=artifact,
            admission_scope=_SCOPE,
            knowledge_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
            effective_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
            ruleset=ruleset,
            disposition=EvidenceAdmissionDisposition.ADMITTED,
            full_record_resolution=True,  # type: ignore[call-arg]
            selected_validations=(),
            admission_freshness=None,
            task_freshness=None,
            selected_admission=None,
            selected_validity=None,
            validation_supersession_references=(),
            admission_predecessor_references=(),
            validity_predecessor_references=(),
            findings=("Manual proof flag.",),
        )


@pytest.mark.parametrize(
    "missing",
    ["validation", "freshness", "admission", "validity"],
)
def test_missing_underlying_records_fail_closed_with_resolved_provenance(
    missing: str,
) -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    validation_records = validations
    freshness_records = freshness
    admission_records = (admission,)
    validity_events = (active,)
    if missing == "validation":
        validation_records = tuple(
            record
            for record in validations
            if record.concern is not EvidenceValidationConcern.AUTHORITY
        )
    elif missing == "freshness":
        freshness_records = ()
    elif missing == "admission":
        admission_records = ()
    else:
        validity_events = ()

    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validation_records,
        freshness=freshness_records,
        admissions=admission_records,
        validity=validity_events,
    )

    assert not state.is_consumable
    assert state.disposition is EvidenceAdmissionDisposition.REJECTED
    assert state.ruleset_reference == ruleset.reference()
    assert state.selected_validation_record_references
    if missing == "validation":
        assert {
            reference.concern
            for reference in state.selected_validation_record_references
        } == set(_CONCERNS) - {EvidenceValidationConcern.AUTHORITY}
    assert any(
        token in " ".join(state.findings).lower()
        for token in ("missing", "no effective")
    )


def test_full_record_reference_and_fingerprint_correspondence_is_required() -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    replacement_schema = create_evidence_validation_record(
        validation_record_id="validation.schema.replacement",
        artifact_reference=artifact.reference(),
        concern=EvidenceValidationConcern.SCHEMA,
        scope=_SCOPE,
        disposition=EvidenceValidationDisposition.PASSED,
        validator_identity=_actor("replacement_validator"),
        ruleset_id="quote_validation",
        ruleset_version="1",
        recorded_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
        findings=("Replacement schema validation.",),
    )
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=tuple(
            record
            for record in validations
            if record.concern is not EvidenceValidationConcern.SCHEMA
        )
        + (replacement_schema,),
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )

    assert not state.is_consumable
    assert replacement_schema.reference() in (
        state.selected_validation_record_references
    )
    assert "does not reference" in " ".join(state.findings).lower()


@pytest.mark.parametrize(
    ("ruleset_id", "ruleset_version"),
    (
        ("unrelated_validation_policy", "999"),
        ("quote_validation", "999"),
    ),
)
def test_full_evaluator_rejects_wrong_validation_policy_identity(
    ruleset_id: str,
    ruleset_version: str,
) -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    wrong_schema = _validation(
        artifact,
        EvidenceValidationConcern.SCHEMA,
        ruleset_id=ruleset_id,
        ruleset_version=ruleset_version,
    )
    supplied = tuple(
        record
        for record in validations
        if record.concern is not EvidenceValidationConcern.SCHEMA
    ) + (wrong_schema,)

    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=supplied,
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )

    assert not state.is_consumable
    assert all(
        reference.concern is not EvidenceValidationConcern.SCHEMA
        for reference in state.selected_validation_record_references
    )
    assert (
        "required validation concern is missing: schema"
        in " ".join(state.findings).lower()
    )


def test_task_time_freshness_is_independent_from_historical_admission() -> None:
    policy = _ruleset(task_freshness_required=True)
    artifact, _, validations, freshness, admission, active = _records(ruleset=policy)
    admission_freshness, task_pass = freshness
    admission_before = admission.to_dict()
    passing = _evaluate(
        artifact,
        ruleset=policy,
        validations=validations,
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )
    task_stale = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 21, tzinfo=UTC),
        result=False,
    )
    stale = _evaluate(
        artifact,
        ruleset=policy,
        validations=validations,
        freshness=(*freshness, task_stale),
        admissions=(admission,),
        validity=(active,),
        knowledge_as_of=datetime(2026, 8, 25, 21, tzinfo=UTC),
        effective_as_of=datetime(2026, 8, 25, 21, tzinfo=UTC),
    )

    assert passing.is_consumable
    assert not stale.is_consumable
    assert stale.task_freshness_evaluation_reference == task_stale.reference()
    assert (
        stale.admission_freshness_evaluation_reference
        == admission_freshness.reference()
    )
    assert stale.selected_admission_record_reference == admission.reference()
    assert admission.to_dict() == admission_before
    assert "task-time freshness" in " ".join(stale.findings).lower()


@pytest.mark.parametrize(
    "status",
    [
        EvidenceValidityStatus.EXPIRED,
        EvidenceValidityStatus.WITHDRAWN,
        EvidenceValidityStatus.REVOKED,
    ],
)
def test_terminal_validity_blocks_consumability(
    status: EvidenceValidityStatus,
) -> None:
    artifact, ruleset, validations, freshness, admission, _ = _records()
    terminal = _validity(artifact, status)
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=freshness,
        admissions=(admission,),
        validity=(terminal,),
    )

    assert not state.is_consumable
    assert state.selected_validity_reference == terminal.reference()
    assert "not active" in " ".join(state.findings).lower()


def test_validation_supersession_is_append_only_and_deterministic() -> None:
    artifact, ruleset, validations, freshness, _, active = _records()
    predecessor = next(
        record
        for record in validations
        if record.concern is EvidenceValidationConcern.SCHEMA
    )
    other_validations = tuple(
        record
        for record in validations
        if record.concern is not EvidenceValidationConcern.SCHEMA
    )
    successor = create_evidence_validation_record(
        validation_record_id="validation.schema.2",
        artifact_reference=artifact.reference(),
        concern=EvidenceValidationConcern.SCHEMA,
        scope=_SCOPE,
        disposition=EvidenceValidationDisposition.PASSED,
        validator_identity=_actor("validator"),
        validator_capability_identity=EvidenceIdentityReference(
            namespace="capability",
            identity_id="schema_validation",
            identity_version="1",
        ),
        ruleset_id="quote_validation",
        ruleset_version="1",
        recorded_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
        findings=("Schema revalidated.",),
        predecessor=predecessor,
    )
    admission = _admission(
        artifact,
        tuple(
            record
            for record in validations
            if record.concern is not EvidenceValidationConcern.SCHEMA
        )
        + (successor,),
        freshness[0],
        ruleset=ruleset,
    )
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=(successor, *other_validations, predecessor),
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )

    assert state.is_consumable
    assert successor.predecessor_validation_record_reference == predecessor.reference()
    assert successor.validator_capability_identity is not None
    assert state.resolved_validation_supersession_references == (
        predecessor.reference(),
    )


def test_forked_validation_supersession_fails_closed() -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    predecessor = next(
        record
        for record in validations
        if record.concern is EvidenceValidationConcern.SCHEMA
    )
    other_validations = tuple(
        record
        for record in validations
        if record.concern is not EvidenceValidationConcern.SCHEMA
    )
    successors = tuple(
        create_evidence_validation_record(
            validation_record_id=f"validation.schema.{suffix}",
            artifact_reference=artifact.reference(),
            concern=EvidenceValidationConcern.SCHEMA,
            scope=_SCOPE,
            disposition=EvidenceValidationDisposition.PASSED,
            validator_identity=_actor("validator"),
            ruleset_id="quote_validation",
            ruleset_version="1",
            recorded_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
            effective_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
            findings=(f"Fork {suffix}.",),
            predecessor=predecessor,
        )
        for suffix in ("fork_a", "fork_b")
    )
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=(*other_validations, predecessor, *successors),
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )

    assert not state.is_consumable
    assert "forked validation" in " ".join(state.findings).lower()


def test_historical_as_of_replay_is_deterministic() -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    revoked = _validity(
        artifact,
        EvidenceValidityStatus.REVOKED,
        suffix="revoked",
        recorded_at=datetime(2026, 8, 25, 21, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 30, tzinfo=UTC),
        predecessor=active,
    )
    task_at_21 = _freshness(
        artifact,
        as_of=datetime(2026, 8, 25, 21, tzinfo=UTC),
    )
    before = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=freshness,
        admissions=(admission,),
        validity=(active, revoked),
        knowledge_as_of=datetime(2026, 8, 25, 20, 45, tzinfo=UTC),
        effective_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
    )
    replay = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=tuple(reversed(validations)),
        freshness=freshness,
        admissions=(admission,),
        validity=(revoked, active),
        knowledge_as_of=datetime(2026, 8, 25, 20, 45, tzinfo=UTC),
        effective_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
    )
    after = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=(*freshness, task_at_21),
        admissions=(admission,),
        validity=(active, revoked),
        knowledge_as_of=datetime(2026, 8, 25, 21, tzinfo=UTC),
        effective_as_of=datetime(2026, 8, 25, 21, tzinfo=UTC),
    )

    assert before.is_consumable
    assert before.to_dict() == replay.to_dict()
    assert not after.is_consumable
    assert after.selected_validity_reference == revoked.reference()
    assert after.resolved_validity_predecessor_references == (active.reference(),)


def test_admission_predecessor_resolution_is_retained() -> None:
    artifact, ruleset, validations, freshness, predecessor, active = _records()
    successor = _admission(
        artifact,
        validations,
        freshness[0],
        ruleset=ruleset,
        suffix="rejected",
        disposition=EvidenceAdmissionDisposition.REJECTED,
        recorded_at=datetime(2026, 8, 25, 20, 8, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 8, tzinfo=UTC),
        predecessor=predecessor,
        capability_identity=EvidenceIdentityReference(
            namespace="capability",
            identity_id="record_evidence_admission",
            identity_version="1",
        ),
    )
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=freshness,
        admissions=(predecessor, successor),
        validity=(active,),
    )

    assert not state.is_consumable
    assert state.selected_admission_record_reference == successor.reference()
    assert successor.predecessor_admission_record_reference == predecessor.reference()
    assert successor.deciding_capability_identity is not None
    assert state.resolved_admission_predecessor_references == (predecessor.reference(),)


def test_missing_or_forked_admission_predecessor_lineage_fails_closed() -> None:
    artifact, ruleset, validations, freshness, predecessor, active = _records()
    successors = tuple(
        _admission(
            artifact,
            validations,
            freshness[0],
            ruleset=ruleset,
            suffix=suffix,
            disposition=EvidenceAdmissionDisposition.REJECTED,
            recorded_at=datetime(2026, 8, 25, 20, minute, tzinfo=UTC),
            effective_at=datetime(2026, 8, 25, 20, minute, tzinfo=UTC),
            predecessor=predecessor,
        )
        for suffix, minute in (("fork_a", 7), ("fork_b", 8))
    )

    missing = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=freshness,
        admissions=(successors[0],),
        validity=(active,),
    )
    forked = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=freshness,
        admissions=(predecessor, *successors),
        validity=(active,),
    )

    assert not missing.is_consumable
    assert "unresolved predecessor" in " ".join(missing.findings)
    assert not forked.is_consumable
    assert "Forked admission predecessor" in " ".join(forked.findings)
    assert forked.resolved_admission_predecessor_references == (
        predecessor.reference(),
    )


def test_co_precedent_admission_records_fail_closed_with_other_provenance() -> None:
    artifact, ruleset, validations, freshness, first, active = _records()
    second = _admission(
        artifact,
        validations,
        freshness[0],
        ruleset=ruleset,
        suffix="co_precedent",
    )

    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=freshness,
        admissions=(first, second),
        validity=(active,),
    )

    assert not state.is_consumable
    assert state.selected_admission_record_reference is None
    assert state.selected_validation_record_references == tuple(
        record.reference() for record in validations
    )
    assert state.admission_freshness_evaluation_reference is None
    assert state.task_freshness_evaluation_reference == freshness[1].reference()
    assert state.selected_validity_reference == active.reference()
    assert "co-precedent admission" in " ".join(state.findings)


def test_tampered_cyclic_admission_lineage_fails_closed_before_resolution() -> None:
    artifact, ruleset, validations, freshness, predecessor, active = _records()
    successor = _admission(
        artifact,
        validations,
        freshness[0],
        ruleset=ruleset,
        suffix="successor",
        disposition=EvidenceAdmissionDisposition.REJECTED,
        recorded_at=datetime(2026, 8, 25, 20, 8, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 8, tzinfo=UTC),
        predecessor=predecessor,
    )
    object.__setattr__(
        predecessor,
        "predecessor_admission_record_reference",
        successor.reference(),
    )

    with pytest.raises(ValueError, match="fingerprint does not match content"):
        _evaluate(
            artifact,
            ruleset=ruleset,
            validations=validations,
            freshness=freshness,
            admissions=(predecessor, successor),
            validity=(active,),
        )


def test_full_evaluator_requires_the_actual_untampered_artifact() -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()

    with pytest.raises(TypeError, match="artifact must be an EvidenceArtifact"):
        evaluate_evidence_admission_as_of(
            artifact=None,  # type: ignore[arg-type]
            admission_scope=_SCOPE,
            validation_records=validations,
            freshness_evaluations=freshness,
            admission_records=(admission,),
            validity_events=(active,),
            admission_ruleset=ruleset,
            knowledge_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
            effective_as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        )

    object.__setattr__(artifact, "fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(ValueError, match="fingerprint does not match content"):
        _evaluate(
            artifact,
            ruleset=ruleset,
            validations=validations,
            freshness=freshness,
            admissions=(admission,),
            validity=(active,),
        )


def test_fake_or_mismatched_artifact_reference_fails_closed() -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    fake_reference = EvidenceArtifactReference(
        artifact_id=artifact.artifact_id,
        artifact_version=artifact.artifact_version,
        artifact_fingerprint=canonical_fingerprint(
            {
                "schema_version": "fabricated_artifact/v1",
                "fabricated": "artifact fingerprint",
            }
        ),
        information_class=artifact.information_class,
        authority=artifact.authority,
    )
    fake_validation = create_evidence_validation_record(
        validation_record_id="validation.fake.reference",
        artifact_reference=fake_reference,
        concern=EvidenceValidationConcern.SOURCE_QUALITY,
        scope=_SCOPE,
        disposition=EvidenceValidationDisposition.PASSED,
        validator_identity=_actor("fake_validator"),
        ruleset_id="quote_validation",
        ruleset_version="1",
        recorded_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
        effective_at=datetime(2026, 8, 25, 20, 2, tzinfo=UTC),
        findings=("Fabricated reference.",),
    )

    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=(*validations, fake_validation),
        freshness=freshness,
        admissions=(admission,),
        validity=(active,),
    )

    assert not state.is_consumable
    assert state.artifact_reference == artifact.reference()
    assert "do not all bind the exact artifact" in " ".join(state.findings)


def test_fabricated_admission_freshness_anchor_fails_closed() -> None:
    artifact, ruleset, validations, freshness, _, active = _records()
    fabricated = _fabricate_freshness(
        _freshness(
            artifact,
            as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
        ),
        temporal_values=(("published_at", datetime(2027, 8, 25, 20, tzinfo=UTC)),),
    )
    admission = _admission(
        artifact,
        validations,
        fabricated,
        ruleset=ruleset,
    )
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=(fabricated, freshness[1]),
        admissions=(admission,),
        validity=(active,),
    )

    assert not state.is_consumable
    assert state.admission_freshness_evaluation_reference == fabricated.reference()
    assert "does not exactly correspond" in " ".join(state.findings)


def test_shifted_task_freshness_anchor_fails_closed() -> None:
    artifact, ruleset, validations, freshness, admission, active = _records()
    shifted_task = _fabricate_freshness(
        _freshness(
            artifact,
            as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        ),
        temporal_values=(("published_at", datetime(2026, 8, 25, 20, 1, tzinfo=UTC)),),
    )
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=(freshness[0], shifted_task),
        admissions=(admission,),
        validity=(active,),
    )

    assert not state.is_consumable
    assert state.task_freshness_evaluation_reference == shifted_task.reference()
    assert "does not exactly correspond" in " ".join(state.findings)


def test_missing_artifact_anchor_fails_without_temporal_fallback() -> None:
    artifact = _artifact()
    missing_anchor_rule = EvidenceFreshnessRule(
        rule_id="effective_until_required",
        rule_version="1",
        declared_temporal_anchor="effective_until",
        evaluation_scope=_SCOPE,
    )
    ruleset = EvidenceAdmissionRuleSet(
        ruleset_id="missing_anchor_policy",
        ruleset_version="1",
        admission_scope=_SCOPE,
        mandatory_validation_requirements=(
            _ruleset().mandatory_validation_requirements
        ),
        admission_freshness_required=True,
        admission_freshness_rule=missing_anchor_rule,
        task_freshness_required=True,
        task_freshness_rule=missing_anchor_rule,
        active_validity_required=True,
    )
    validations = tuple(_validation(artifact, concern) for concern in _CONCERNS)
    fabricated_admission = _fabricate_freshness(
        _freshness(
            artifact,
            as_of=datetime(2026, 8, 25, 20, 5, tzinfo=UTC),
        ),
        freshness_rule=missing_anchor_rule,
        temporal_values=(
            ("effective_until", artifact.temporal_identity.artifact_created_at),
        ),
    )
    fabricated_task = _fabricate_freshness(
        _freshness(
            artifact,
            as_of=datetime(2026, 8, 25, 20, 10, tzinfo=UTC),
        ),
        freshness_rule=missing_anchor_rule,
        temporal_values=(
            ("effective_until", artifact.temporal_identity.artifact_created_at),
        ),
    )
    admission = _admission(
        artifact,
        validations,
        fabricated_admission,
        ruleset=ruleset,
    )
    active = _validity(artifact)
    state = _evaluate(
        artifact,
        ruleset=ruleset,
        validations=validations,
        freshness=(fabricated_admission, fabricated_task),
        admissions=(admission,),
        validity=(active,),
    )

    assert not state.is_consumable
    assert state.admission_freshness_evaluation_reference is not None
    assert state.task_freshness_evaluation_reference is not None
    assert "artifact anchor is unavailable" in " ".join(state.findings)
    assert "effective_until" in " ".join(state.findings)
