from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event

import pytest
from test_polygon_completed_daily_production_admission_validity import (
    _activate,
    _refuse,
    _setup,
)
from test_polygon_completed_daily_production_validation import _Clock

import market_platform.evidence as evidence
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import (
    polygon_completed_daily_production_freshness as f,
)
from market_platform.application import polygon_completed_daily_production_validity as v
from market_platform.evidence.evaluation import _resolve_validation_concern


@pytest.mark.parametrize(
    "field",
    [
        "freshness_rule",
        "production_profile_fingerprint",
        "construction_receipt_fingerprint",
        "executor",
    ],
)
def test_lookalike_freshness_context_refuses(field):
    issuer, request, _, _, _, result, _ = _setup()
    if field == "freshness_rule":
        value = evidence.EvidenceFreshnessRule(
            "lookalike", "1.0.0", "observation_period_end", a._SCOPE
        )
    elif field == "executor":
        value = evidence.EvidenceIdentityReference("caller", "caller", "1")
    else:
        value = "sha256:" + "0" * 64
    object.__setattr__(result.companion, field, value)
    _refuse(issuer, request)


@pytest.mark.parametrize(
    "field", ["artifact_fingerprint", "artifact_version", "artifact_id"]
)
def test_active_artifact_mismatch_refuses(field):
    issuer, request, *_, instant = _setup()
    issuer.issue_admission(request)
    service, intent = _activate(issuer, request, instant + timedelta(minutes=1))
    altered = replace(intent.artifact_reference, **{field: "sha256:" + "0" * 64})
    with pytest.raises(v.PolygonCompletedDailyValidityIssuanceRefused):
        service.issue_initial_active(
            v.PolygonCompletedDailyInitialActiveRequest(
                altered, intent.construction_execution_id
            )
        )
    assert service.get_validity_history(intent.artifact_reference) == ()


@pytest.mark.parametrize("field", ["admission_scope", "deciding_actor_identity"])
def test_active_rejects_corrupt_admission_scope_and_actor(field):
    issuer, request, *_, instant = _setup()
    admitted = issuer.issue_admission(request)
    value = (
        "wrong.scope"
        if field == "admission_scope"
        else evidence.EvidenceIdentityReference("caller", "caller", "1")
    )
    object.__setattr__(admitted.admission_record, field, value)
    service, intent = _activate(issuer, request, instant + timedelta(minutes=1))
    with pytest.raises(v.PolygonCompletedDailyValidityIssuanceRefused):
        service.issue_initial_active(intent)


@pytest.mark.parametrize("stage", ["admission", "active"])
@pytest.mark.parametrize("phase", ["completion", "availability"])
def test_regressing_clocks_never_publish(stage, phase):
    issuer, request, *_, instant = _setup()
    if stage == "active":
        issuer.issue_admission(request)
        instant += timedelta(minutes=1)
        service, intent = _activate(issuer, request, instant)
        error = v.PolygonCompletedDailyValidityIssuanceRefused
        issue = service.issue_initial_active
    else:
        service, intent = issuer, request
        error = a.PolygonCompletedDailyAdmissionIssuanceRefused
        issue = service.issue_admission
    backwards = instant - timedelta(seconds=1)
    service._execution_clock = _Clock(
        instant, backwards if phase == "completion" else instant, backwards
    )
    with pytest.raises(error):
        issue(intent)
    assert service._history._state == (1, ())


def test_prerequisite_locks_are_held_through_final_availability():
    issuer, request, validator, fresh, *_, instant = _setup()
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 3:
            for store in (
                issuer._construction_service._history,
                validator._history,
                fresh._history,
                issuer._history,
            ):
                assert store._lock.locked()
            assert issuer._history._pending is not None
            assert issuer._history._state == (1, ())
        return instant

    issuer._execution_clock = clock
    result = issuer.issue_admission(request)
    assert result.companion.available_at == instant
    assert calls == 3


def test_concurrent_initial_activation_issues_only_once():
    issuer, request, *_, instant = _setup()
    issuer.issue_admission(request)
    service, intent = _activate(issuer, request, instant + timedelta(minutes=1))
    go = Event()

    def issue():
        assert go.wait(10)
        try:
            return service.issue_initial_active(intent)
        except v.PolygonCompletedDailyValidityIssuanceRefused:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(issue) for _ in range(2)]
        go.set()
        results = [future.result(timeout=30) for future in futures]
    assert sum(item is not None for item in results) == 1
    assert len(service.get_validity_history(request.artifact_reference)) == 1


def test_intervening_prerequisite_corruption_at_publication_refuses():
    issuer, request, validator, *_, instant = _setup()
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 3:
            sequence, entries = validator._history._state
            validator._history._state = (sequence, entries[:-1])
        return instant

    issuer._execution_clock = clock
    _refuse(issuer, request)


def test_admission_history_prefix_deletion_is_corruption():
    issuer, request, *_, instant = _setup()
    issuer.issue_admission(request)
    issuer._history._state = (2, ())
    with pytest.raises(a.PolygonCompletedDailyAdmissionHistoryError):
        issuer.get_admission_history(request.artifact_reference)


@pytest.mark.parametrize("target", ["admission", "active", "construction"])
def test_final_publication_refuses_changed_retained_history(target):
    issuer, request, *_, instant = _setup()
    if target == "admission":
        service, intent = issuer, request
        issue = service.issue_admission
        error = a.PolygonCompletedDailyAdmissionIssuanceRefused
        store = issuer._history
    else:
        issuer.issue_admission(request)
        instant += timedelta(minutes=1)
        service, intent = _activate(issuer, request, instant)
        issue = service.issue_initial_active
        error = v.PolygonCompletedDailyValidityIssuanceRefused
        store = (
            service._history
            if target == "active"
            else issuer._construction_service._history
        )
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 3:
            sequence, entries = store._state
            store._state = (sequence + 1, entries)
        return instant

    service._execution_clock = clock
    with pytest.raises(error):
        issue(intent)
    assert service._history._state[1] == ()
    assert service._history._pending is None


def test_task_staleness_and_supersession_do_not_issue_terminal_events():
    issuer, request, _, fresh, *_, instant = _setup()
    admitted = issuer.issue_admission(request)
    service, intent = _activate(issuer, request, instant + timedelta(minutes=1))
    activated = service.issue_initial_active(intent)
    later = instant + timedelta(days=10)
    fresh._execution_clock = lambda: later
    stale = fresh.execute_task(
        f.PolygonCompletedDailyTaskFreshnessRequest(
            request.artifact_reference, request.construction_execution_id, later
        )
    )
    assert not stale.freshness_record.result
    assert service.get_validity_history(request.artifact_reference) == (activated,)
    assert activated.validity_event.status is evidence.EvidenceValidityStatus.ACTIVE
    assert (
        admitted.admission_record.disposition
        is evidence.EvidenceAdmissionDisposition.ADMITTED
    )
    # Artifact supersession is an independent generic history, absent from this issuer.
    assert (
        "supersession"
        not in v.PolygonCompletedDailyProductionValidityApplicationService.__slots__
    )


@pytest.mark.parametrize(
    "case", ["successor", "fork", "missing", "adverse", "duplicate"]
)
def test_reused_validation_selector_preserves_released_lineage_semantics(case):
    issuer, _, _, _, results, _, instant = _setup()
    prior = results[0].validation_record

    def record(name, disposition=evidence.EvidenceValidationDisposition.PASSED):
        return evidence.create_evidence_validation_record(
            validation_record_id=name,
            artifact_reference=prior.artifact_reference,
            concern=prior.concern,
            scope=prior.scope,
            disposition=disposition,
            validator_identity=prior.validator_identity,
            ruleset_id=prior.ruleset_id,
            ruleset_version=prior.ruleset_version,
            recorded_at=instant,
            effective_at=instant,
            findings=("Fixture lifecycle conclusion.",),
            predecessor=prior,
        )

    successor = record(
        "successor",
        evidence.EvidenceValidationDisposition.REJECTED
        if case == "adverse"
        else evidence.EvidenceValidationDisposition.PASSED,
    )
    histories = {
        "successor": (prior, successor),
        "fork": (prior, successor, record("fork")),
        "missing": (successor,),
        "adverse": (prior, successor),
        "duplicate": (prior, prior),
    }
    assert a._resolve_validation_concern is _resolve_validation_concern
    selected, lineage, failure = a._resolve_validation_concern(
        histories[case], prior.concern
    )
    if case in ("fork", "missing"):
        assert selected is None and failure is not None
    elif case == "adverse":
        assert selected is successor and failure is not None
    elif case == "duplicate":
        assert selected is prior and failure is None
    else:
        assert (
            selected is successor
            and lineage == (prior.reference(),)
            and failure is None
        )


def test_released_evaluator_still_requires_task_freshness_after_activation():
    issuer, request, _, _, validations, freshness, instant = _setup()
    admitted = issuer.issue_admission(request)
    service, intent = _activate(issuer, request, instant + timedelta(minutes=1))
    activated = service.issue_initial_active(intent)
    state = evidence.evaluate_evidence_admission_as_of(
        artifact=admitted.construction_result.artifact,
        admission_scope=a._SCOPE,
        validation_records=tuple(item.validation_record for item in validations),
        freshness_evaluations=(freshness.freshness_record,),
        admission_records=(admitted.admission_record,),
        validity_events=(activated.validity_event,),
        admission_ruleset=a._RULESET,
        knowledge_as_of=activated.companion.available_at,
        effective_as_of=activated.validity_event.effective_at,
    )
    assert (
        state.selected_admission_record_reference
        == admitted.admission_record.reference()
    )
    assert state.selected_validity_reference == activated.validity_event.reference()
    assert not state.is_consumable
