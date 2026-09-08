from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields, replace
from datetime import timedelta

import pytest
from test_polygon_completed_daily_production_validation import (
    _Clock,
    _construction,
    _request,
    _validation_service,
)

import market_platform.evidence as evidence
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import (
    polygon_completed_daily_production_freshness as f,
)
from market_platform.application import (
    polygon_completed_daily_production_validation as v,
)
from market_platform.application import (
    polygon_completed_daily_production_validity as active,
)
from market_platform.evidence import evaluation


def _setup(*, validation=True, freshness=True, constant=False):
    construction_service, constructed = _construction()
    validator = _validation_service(
        construction_service, constructed, constant=constant
    )
    results = validator.execute_profile(_request(constructed)) if validation else ()
    instant = constructed.receipt.available_at + timedelta(minutes=3)
    fresh = f.PolygonCompletedDailyProductionFreshnessApplicationService(
        construction_service, execution_clock=lambda: instant
    )
    fresh_request = f.PolygonCompletedDailyAdmissionFreshnessRequest(
        constructed.artifact.reference(), constructed.receipt.execution_id
    )
    fresh_result = fresh.execute_admission(fresh_request) if freshness else None
    issued = instant + timedelta(minutes=1)
    issuer = a.PolygonCompletedDailyProductionAdmissionApplicationService(
        construction_service,
        validator,
        fresh,
        execution_clock=_Clock(
            issued, issued + timedelta(seconds=1), issued + timedelta(seconds=2)
        ),
    )
    request = a.PolygonCompletedDailyAdmissionRequest(
        constructed.artifact.reference(), constructed.receipt.execution_id
    )
    return issuer, request, validator, fresh, results, fresh_result, issued


def _activate(issuer, request, instant):
    service = active.PolygonCompletedDailyProductionValidityApplicationService(
        issuer, execution_clock=lambda: instant
    )
    intent = active.PolygonCompletedDailyInitialActiveRequest(
        request.artifact_reference, request.construction_execution_id
    )
    return service, intent


def _refuse(issuer, request, reason=None):
    with pytest.raises(a.PolygonCompletedDailyAdmissionIssuanceRefused) as caught:
        issuer.issue_admission(request)
    if reason is not None:
        assert caught.value.reason is reason
    assert issuer._history._state == (1, ())
    assert issuer._history._pending is None


def test_authentic_admission_and_separate_initial_active_without_task_freshness(
    monkeypatch,
):
    def forbidden(**kwargs):
        raise AssertionError("full evaluator must never authorize issuance")

    monkeypatch.setattr(evaluation, "evaluate_evidence_admission_as_of", forbidden)
    issuer, request, _, fresh, validations, freshness, issued = _setup()
    validity, intent = _activate(issuer, request, issued + timedelta(minutes=1))
    assert issuer.get_admission_history(request.artifact_reference) == ()
    assert validity.get_validity_history(request.artifact_reference) == ()
    admitted = issuer.issue_admission(request)
    assert (
        admitted.admission_record.disposition
        is evidence.EvidenceAdmissionDisposition.ADMITTED
    )
    assert admitted.admission_record.selected_validation_record_references == tuple(
        item.validation_record.reference() for item in validations
    )
    assert (
        admitted.admission_record.admission_freshness_evaluation_reference
        == freshness.freshness_record.reference()
    )
    assert validity.get_validity_history(request.artifact_reference) == ()
    assert (
        fresh.get_task_freshness_history(
            request.artifact_reference,
            construction_execution_id=request.construction_execution_id,
        )
        == ()
    )
    result = validity.issue_initial_active(intent)
    assert result.validity_event.status is evidence.EvidenceValidityStatus.ACTIVE
    assert (
        result.companion.admission_execution_reference
        == admitted.companion.execution_reference()
    )
    assert (
        admitted.companion.available_at
        <= result.validity_event.effective_at
        <= result.companion.available_at
    )
    for obj in (admitted, admitted.companion, result, result.companion):
        for name in ("consumable", "is_consumable", "research_permitted"):
            assert not hasattr(obj, name)


@pytest.mark.parametrize(
    "validation,freshness", [(False, True), (True, False), (False, False)]
)
def test_missing_prerequisites_refuse(validation, freshness):
    issuer, request, *_ = _setup(validation=validation, freshness=freshness)
    _refuse(issuer, request)


@pytest.mark.parametrize("concern", tuple(evidence.EvidenceValidationConcern))
def test_missing_any_one_concern_refuses(concern):
    issuer, request, validator, *_ = _setup()
    # Simulate interrupted profile execution by retaining only the authentic prefix.
    entries = validator._history._state[1]
    cut = next(
        index
        for index, item in enumerate(entries)
        if item.validation_record.concern is concern
    )
    validator._history._state = (cut + 1, entries[:cut])
    _refuse(issuer, request)


@pytest.mark.parametrize(
    "disposition",
    [
        evidence.EvidenceValidationDisposition.REJECTED,
        evidence.EvidenceValidationDisposition.UNABLE_TO_VALIDATE,
    ],
)
def test_later_adverse_cannot_be_ignored(disposition, monkeypatch):
    issuer, request, validator, _, _, _, issued = _setup()
    original = v._evaluate_definition

    def adverse(definition, support):
        if definition.requirement.concern is evidence.EvidenceValidationConcern.SCHEMA:
            return v._RuleConclusion(disposition, ("Controlled adverse execution.",))
        return original(definition, support)

    # Trusted executor seam supplies adverse lifecycle history, never caller tuples.
    _historical_rule_fixture(monkeypatch, validator._history._state[1], adverse)
    validator._execution_clock = lambda: issued - timedelta(seconds=1)
    validator.execute_profile(
        v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    _refuse(
        issuer,
        request,
        a.PolygonCompletedDailyAdmissionRefusalReason.VALIDATION_REJECTED
        if disposition is evidence.EvidenceValidationDisposition.REJECTED
        else (
            a.PolygonCompletedDailyAdmissionRefusalReason.VALIDATION_UNABLE_TO_VALIDATE
        ),
    )
    assert (
        len(
            validator.get_validation_history(
                request.artifact_reference,
                construction_execution_id=request.construction_execution_id,
                concern=evidence.EvidenceValidationConcern.SCHEMA,
            )
        )
        == 2
    )


def test_duplicate_execution_occurrences_are_one_lifecycle_record():
    issuer, request, validator, fresh, _, initial_freshness, _ = _setup(constant=True)
    validator.execute_profile(
        v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    duplicate_freshness = fresh.execute_admission(
        f.PolygonCompletedDailyAdmissionFreshnessRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    assert duplicate_freshness.freshness_record == initial_freshness.freshness_record
    result = issuer.issue_admission(request)
    assert len(result.companion.selected_validation_record_references) == 8
    assert len(result.companion.selected_validation_execution_references) == 16
    assert len(result.companion.admission_freshness_execution_references) == 2


def test_genuine_co_precedent_validation_conflict_refuses(monkeypatch):
    issuer, request, validator, *_ = _setup(constant=True)
    original = v._evaluate_definition

    def different(definition, support):
        conclusion = original(definition, support)
        return replace(
            conclusion, findings=(*conclusion.findings, "Distinct conclusion.")
        )

    _historical_rule_fixture(monkeypatch, validator._history._state[1], different)
    validator.execute_profile(
        v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    _refuse(issuer, request)


@pytest.mark.parametrize("days", [1, 5])
def test_previous_new_york_date_and_stale_freshness_refuse(days):
    issuer, request, _, fresh, _, _, issued = _setup()
    later = issued + timedelta(days=days)
    if days == 5:
        fresh._execution_clock = lambda: later - timedelta(seconds=1)
        result = fresh.execute_admission(
            f.PolygonCompletedDailyAdmissionFreshnessRequest(
                request.artifact_reference, request.construction_execution_id
            )
        )
        assert result.freshness_record.result is False
    issuer._execution_clock = lambda: later
    _refuse(issuer, request)


def test_task_freshness_cannot_substitute():
    issuer, request, _, fresh, _, _, issued = _setup(freshness=False)
    task = fresh.execute_task(
        f.PolygonCompletedDailyTaskFreshnessRequest(
            request.artifact_reference, request.construction_execution_id, issued
        )
    )
    assert task.freshness_record.result is True
    _refuse(issuer, request)


@pytest.mark.parametrize("kind", ["validation", "freshness"])
def test_prerequisite_actual_availability_required(kind):
    issuer, request, validator, fresh, _, _, issued = _setup(
        validation=False, freshness=False
    )
    validator._execution_clock = lambda: issued - timedelta(seconds=2)
    if kind == "validation":
        validator._execution_clock = _Clock(
            *sum(
                (
                    [
                        issued - timedelta(seconds=2),
                        issued - timedelta(seconds=1),
                        issued + timedelta(seconds=1),
                    ]
                    for _ in range(8)
                ),
                [],
            )
        )
    validator.execute_profile(
        v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    fresh._execution_clock = _Clock(
        issued - timedelta(seconds=2),
        issued - timedelta(seconds=2),
        issued - timedelta(seconds=1),
        issued + timedelta(seconds=1) if kind == "freshness" else issued,
    )
    fresh.execute_admission(
        f.PolygonCompletedDailyAdmissionFreshnessRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    issuer._execution_clock = lambda: issued
    _refuse(issuer, request)


def test_admission_and_active_availability_cutoffs_are_inclusive():
    issuer, request, *_, issued = _setup()
    result = issuer.issue_admission(request)
    available = result.companion.available_at
    assert (
        issuer.get_admission_history_as_of(
            request.artifact_reference,
            knowledge_as_of=available - timedelta(microseconds=1),
        )
        == ()
    )
    assert issuer.get_admission_history_as_of(
        request.artifact_reference, knowledge_as_of=available
    ) == (result,)
    service, intent = _activate(issuer, request, available)
    activated = service.issue_initial_active(intent)
    assert (
        service.get_validity_history_as_of(
            request.artifact_reference,
            knowledge_as_of=available - timedelta(microseconds=1),
        )
        == ()
    )
    assert service.get_validity_history_as_of(
        request.artifact_reference, knowledge_as_of=available
    ) == (activated,)


@pytest.mark.parametrize("stage", ["admission", "active"])
def test_failed_publication_exposes_no_result(stage, monkeypatch):
    issuer, request, *_, issued = _setup()

    def fail(self, staged):
        assert self._state == (1, ())
        raise RuntimeError("publication failed")

    if stage == "admission":
        monkeypatch.setattr(
            a._InMemoryPolygonCompletedDailyAdmissionHistory, "_stage_publication", fail
        )
        _refuse(issuer, request)
    else:
        issuer.issue_admission(request)
        service, intent = _activate(issuer, request, issued + timedelta(minutes=1))
        monkeypatch.setattr(
            active._InMemoryPolygonCompletedDailyValidityHistory,
            "_stage_publication",
            fail,
        )
        with pytest.raises(active.PolygonCompletedDailyValidityIssuanceRefused):
            service.issue_initial_active(intent)
        assert service._history._state == (1, ())
        assert service._history._pending is None


def test_no_admission_and_not_yet_available_admission_refuse_active():
    issuer, request, *_, issued = _setup()
    service, intent = _activate(issuer, request, issued)
    with pytest.raises(active.PolygonCompletedDailyValidityIssuanceRefused):
        service.issue_initial_active(intent)
    admitted = issuer.issue_admission(request)
    service._execution_clock = lambda: (
        admitted.companion.available_at - timedelta(microseconds=1)
    )
    with pytest.raises(active.PolygonCompletedDailyValidityIssuanceRefused):
        service.issue_initial_active(intent)
    assert service._history._state == (1, ())


def test_second_initial_active_refuses():
    issuer, request, *_, issued = _setup()
    issuer.issue_admission(request)
    service, intent = _activate(issuer, request, issued + timedelta(minutes=1))
    first = service.issue_initial_active(intent)
    with pytest.raises(active.PolygonCompletedDailyValidityIssuanceRefused) as caught:
        service.issue_initial_active(intent)
    assert (
        caught.value.reason
        is active.PolygonCompletedDailyValidityRefusalReason.PRIOR_VALIDITY
    )
    assert service.get_validity_history(request.artifact_reference) == (first,)


@pytest.mark.parametrize(
    "status",
    [
        evidence.EvidenceValidityStatus.EXPIRED,
        evidence.EvidenceValidityStatus.WITHDRAWN,
        evidence.EvidenceValidityStatus.REVOKED,
    ],
)
def test_terminal_events_cannot_be_reopened_or_imported(status):
    issuer, request, *_, issued = _setup()
    issuer.issue_admission(request)
    service, intent = _activate(issuer, request, issued + timedelta(minutes=1))
    first = service.issue_initial_active(intent)
    terminal = evidence.create_evidence_validity_event(
        validity_event_id="terminal.fixture",
        artifact_reference=request.artifact_reference,
        status=status,
        recorded_at=issued + timedelta(minutes=2),
        effective_at=issued + timedelta(minutes=2),
        actor_identity=active._ACTOR,
        reason="Terminal fixture",
        scope=a._SCOPE,
        predecessor=first.validity_event,
    )
    with pytest.raises(ValueError, match="terminal validity"):
        evidence.create_evidence_validity_event(
            validity_event_id="reopen.fixture",
            artifact_reference=request.artifact_reference,
            status=evidence.EvidenceValidityStatus.ACTIVE,
            recorded_at=issued + timedelta(minutes=3),
            effective_at=issued + timedelta(minutes=3),
            actor_identity=active._ACTOR,
            reason="Reopen",
            scope=a._SCOPE,
            predecessor=terminal,
        )
    # Unsupported imported terminal data is corruption, never empty history.
    object.__setattr__(first, "validity_event", terminal)
    with pytest.raises(active.PolygonCompletedDailyValidityIssuanceRefused):
        service.issue_initial_active(intent)
    assert terminal.status is status


@pytest.mark.parametrize(
    "name",
    [
        "disposition",
        "selected_validation_record_references",
        "admission_record",
        "companion",
        "effective_at",
        "scope",
    ],
)
def test_callers_cannot_supply_admission_authority(name):
    assert (
        name
        not in inspect.signature(a.PolygonCompletedDailyAdmissionRequest).parameters
    )
    assert (
        name
        not in inspect.signature(
            a.PolygonCompletedDailyProductionAdmissionApplicationService.issue_admission
        ).parameters
    )


def test_source_result_and_companion_construction_is_private():
    for cls in (
        a.PolygonCompletedDailyAdmissionExecutionCompanion,
        a.PolygonCompletedDailyProductionAdmissionResult,
        active.PolygonCompletedDailyValidityExecutionCompanion,
        active.PolygonCompletedDailyProductionValidityResult,
    ):
        with pytest.raises(TypeError):
            cls()
    for cls in (
        a.PolygonCompletedDailyProductionAdmissionApplicationService,
        active.PolygonCompletedDailyProductionValidityApplicationService,
    ):
        for method in ("append", "import_record", "import_history", "retain"):
            assert not hasattr(cls, method)
    assert {
        item.name for item in fields(active.PolygonCompletedDailyInitialActiveRequest)
    } == {"artifact_reference", "construction_execution_id"}


def test_repeated_admission_uses_predecessor_and_history_is_complete():
    issuer, request, *_, issued = _setup()
    first = issuer.issue_admission(request)
    issuer._execution_clock = lambda: issued + timedelta(minutes=1)
    second = issuer.issue_admission(request)
    assert (
        second.admission_record.predecessor_admission_record_reference
        == first.admission_record.reference()
    )
    assert issuer.get_admission_history(request.artifact_reference) == (first, second)


@pytest.mark.parametrize("kind", ["admission", "active", "validation", "freshness"])
def test_duplicate_corrupt_history_fails_closed(kind):
    issuer, request, validator, fresh, *_, issued = _setup()
    if kind in ("validation", "freshness"):
        history = validator._history if kind == "validation" else fresh._history
        sequence, entries = history._state
        history._state = (sequence + 1, (*entries, entries[0]))
        _refuse(issuer, request)
    elif kind == "admission":
        result = issuer.issue_admission(request)
        issuer._history._state = (3, (result, result))
        with pytest.raises(a.PolygonCompletedDailyAdmissionHistoryError):
            issuer.get_admission_history(request.artifact_reference)
    else:
        issuer.issue_admission(request)
        service, intent = _activate(issuer, request, issued + timedelta(minutes=1))
        result = service.issue_initial_active(intent)
        service._history._state = (3, (result, result))
        with pytest.raises(active.PolygonCompletedDailyValidityHistoryError):
            service.get_validity_history(request.artifact_reference)


def test_companions_are_immutable_and_exact_frozen_identities_remain():
    issuer, request, *_ = _setup()
    result = issuer.issue_admission(request)
    with pytest.raises(FrozenInstanceError):
        result.companion.available_at = result.companion.execution_started_at
    assert len(evidence.__all__) == len(set(evidence.__all__)) == 69
    assert (
        a._PROFILE.fingerprint
        == "sha256:341279ccfd6839287e5e5c9af46f9eb834577a07e9ffd1a16c0e27ccc35cfd49"
    )
    assert (
        a._PROFILE.construction_authorization.fingerprint
        == "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
    )


def test_new_york_boundary_during_issuance_refuses():
    issuer, request, *_, issued = _setup()
    next_day = (issued + timedelta(days=1)).replace(hour=4, minute=0, second=0)
    issuer._execution_clock = _Clock(next_day - timedelta(seconds=1), next_day)
    _refuse(issuer, request)


def _historical_rule_fixture(monkeypatch, originals, replacement):
    """Model distinct historical conclusions without changing released Slice 4.

    Its deterministic immutable-support engine cannot naturally change a past
    conclusion. Keep native authentication of those original records, and use a
    controlled executor seam for new records to exercise lifecycle selection.
    """
    original_evaluate = v._evaluate_definition
    original_validate = v._validate_result_correspondence
    records = tuple(item.validation_record for item in originals)

    def validate(construction, record, companion):
        if record in records:
            with monkeypatch.context() as context:
                context.setattr(v, "_evaluate_definition", original_evaluate)
                original_validate(construction, record, companion)
        else:
            original_validate(construction, record, companion)

    monkeypatch.setattr(v, "_evaluate_definition", replacement)
    monkeypatch.setattr(v, "_validate_result_correspondence", validate)
