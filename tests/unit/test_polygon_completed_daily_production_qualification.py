from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta

import pytest
from test_polygon_completed_daily_production_admission_validity import _activate, _setup
from test_polygon_completed_daily_production_validation import (
    _Clock,
    _construction,
    _mapping,
)

import market_platform.evidence as evidence
from market_platform.application import (
    polygon_completed_daily_production_qualification as q,
)

R = q.PolygonCompletedDailyQualificationRefusalReason


def _ready(*, validation=True, admission=True, active=True, constant=False):
    issuer, request, validator, fresh, validations, initial, issued = _setup(
        validation=validation, constant=constant
    )
    if admission:
        issuer.issue_admission(request)
    validity, intent = _activate(issuer, request, issued + timedelta(minutes=1))
    if active:
        validity.issue_initial_active(intent)
    analysis = issued + timedelta(minutes=2)
    fresh._execution_clock = _Clock(
        analysis, analysis + timedelta(seconds=1), analysis + timedelta(seconds=2)
    )
    service = q.PolygonCompletedDailyProductionQualificationApplicationService(
        validity,
        execution_clock=_Clock(
            analysis,
            analysis + timedelta(seconds=3),
            analysis + timedelta(seconds=4),
            analysis + timedelta(seconds=5),
        ),
    )
    intent = q.PolygonCompletedDailyQualificationRequest(
        request.artifact_reference, request.construction_execution_id, analysis
    )
    return service, intent


def _refuse(service, request, reason=None):
    with pytest.raises(q.PolygonCompletedDailyQualificationRefused) as caught:
        service.qualify(request)
    if reason is not None:
        assert caught.value.reason is reason
    assert service._history._state == (1, ())
    assert service._history._pending is None
    return caught.value


def test_complete_authentic_canonical_chain_and_envelope(monkeypatch):
    service, request = _ready()
    original = q.evaluation.evaluate_evidence_admission_as_of
    calls = []

    def observe(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(q.evaluation, "evaluate_evidence_admission_as_of", observe)
    result = service.qualify(request)
    assert len(calls) == 1
    assert result.canonical_state.is_consumable is True
    assert (
        result.analysis_as_of
        == result.effective_as_of
        == result.task_freshness_result.freshness_record.evaluation_as_of
    )
    assert (
        result.task_freshness_result.companion.available_at
        < result.knowledge_as_of
        < result.execution_completed_at
        < result.available_at
    )
    assert result.original_ordered_dates == ("2026-08-27", "2026-08-28")
    assert result.original_row_count == 2
    row_projection = {
        "schema_version": "polygon_completed_daily_row_dates/v1",
        "ordered_session_dates": list(result.original_ordered_dates),
        "row_count": result.original_row_count,
    }
    expected = q.canonical_fingerprint(row_projection)
    assert result.original_row_date_fingerprint == expected
    assert q.canonical_fingerprint(dict(row_projection)) == expected
    for change in (
        {"ordered_session_dates": list(reversed(result.original_ordered_dates))},
        {"ordered_session_dates": ["2026-08-26", "2026-08-28"]},
        {"row_count": 1},
        {"schema_version": "polygon_completed_daily_row_dates/v2"},
    ):
        assert q.canonical_fingerprint({**row_projection, **change}) != expected
    assert (
        result.original_row_date_fingerprint
        != result.construction_result.material.fingerprint
    )
    assert not hasattr(result, "research_dataset_fingerprint")
    assert result.all_row_mapping_covered and result.whole_material_completed
    assert result.production_profile.fingerprint == q._PROFILE_FINGERPRINT
    assert (
        result.production_profile.analysis_profile.get("profile_fingerprint")
        == q._ANALYSIS_FINGERPRINT
    )
    assert (
        result.canonical_state.task_freshness_evaluation_reference
        == result.task_freshness_result.freshness_record.reference()
    )
    assert len(calls[0]["validation_records"]) == 8
    assert len(calls[0]["freshness_evaluations"]) == 2
    assert calls[0]["admission_ruleset"] == q._PROFILE.admission_ruleset
    assert result.to_dict()["fingerprint"] == result.fingerprint
    with pytest.raises(FrozenInstanceError):
        result.available_at = request.analysis_as_of
    with pytest.raises(TypeError):
        q.PolygonCompletedDailyQualifiedUse()


@pytest.mark.parametrize(
    "validation,admission,active",
    [(False, False, False), (True, False, False), (True, True, False)],
)
def test_missing_lifecycle_is_canonically_refused(validation, admission, active):
    service, request = _ready(validation=validation, admission=admission, active=active)
    refusal = _refuse(service, request, R.LIFECYCLE_REFUSED)
    assert refusal.canonical_state.is_consumable is False


def test_canonical_false_cannot_be_overridden(monkeypatch):
    service, request = _ready()
    original = q.evaluation.evaluate_evidence_admission_as_of

    def refuse(**kwargs):
        return original(**{**kwargs, "validity_events": ()})

    def forbidden(*args):
        raise AssertionError("consumer cannot override canonical refusal")

    monkeypatch.setattr(q.evaluation, "evaluate_evidence_admission_as_of", refuse)
    monkeypatch.setattr(q, "_qualify_material", forbidden)
    _refuse(service, request, R.LIFECYCLE_REFUSED)


@pytest.mark.parametrize(
    "attribute",
    ["execute_profile", "execute_admission", "issue_admission", "issue_initial_active"],
)
def test_no_automatic_prerequisite_repair(attribute, monkeypatch):
    service, request = _ready()
    source = service._validity_service._admission_service
    owner = {
        "execute_profile": type(source._validation_service),
        "execute_admission": type(source._freshness_service),
        "issue_admission": type(source),
        "issue_initial_active": type(service._validity_service),
    }[attribute]

    def forbidden(*args, **kwargs):
        raise AssertionError("unrequested lifecycle repair")

    monkeypatch.setattr(owner, attribute, forbidden)
    service.qualify(request)


def test_task_failure_has_no_retry(monkeypatch):
    service, request = _ready()
    calls = []

    def fail(*args):
        calls.append(args)
        raise q.f.PolygonCompletedDailyFreshnessExecutionRefused(
            q.f.PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE,
            "failed",
        )

    monkeypatch.setattr(
        q.f.PolygonCompletedDailyProductionFreshnessApplicationService,
        "execute_task",
        fail,
    )
    _refuse(service, request, R.TASK_UNAVAILABLE)
    assert len(calls) == 1


def test_stale_task_is_decisive_despite_admission_freshness():
    service, request = _ready()
    later = request.analysis_as_of + timedelta(days=10)
    service._clock = lambda: later
    service._validity_service._admission_service._freshness_service._execution_clock = (
        lambda: later
    )
    refusal = _refuse(
        service, replace(request, analysis_as_of=later), R.LIFECYCLE_REFUSED
    )
    assert refusal.canonical_state.task_freshness_evaluation_reference.result is False


def test_historical_new_task_is_later_knowledge():
    service, request = _ready()
    cutoff = request.analysis_as_of
    service._clock = lambda: cutoff + timedelta(days=1)
    fresh = service._validity_service._admission_service._freshness_service
    fresh._execution_clock = lambda: cutoff + timedelta(days=1)
    _refuse(service, replace(request, knowledge_as_of=cutoff), R.TASK_UNAVAILABLE)
    assert (
        len(
            fresh.get_task_freshness_history(
                request.artifact_reference,
                construction_execution_id=request.construction_execution_id,
            )
        )
        == 1
    )


def test_replay_uses_retained_task_and_never_backdates_qualification(monkeypatch):
    service, request = _ready()
    first = service.qualify(request)
    later = first.available_at + timedelta(days=1)
    service._clock = lambda: later

    def forbidden(*args):
        raise AssertionError("replay already has exact authentic task")

    monkeypatch.setattr(
        q.f.PolygonCompletedDailyProductionFreshnessApplicationService,
        "execute_task",
        forbidden,
    )
    replay = service.qualify(replace(request, knowledge_as_of=first.knowledge_as_of))
    assert replay.available_at == later > replay.knowledge_as_of
    assert replay.execution_id != first.execution_id
    assert replay.history_sequence == 2
    assert replay.task_freshness_result == first.task_freshness_result
    assert replay.history_context.fingerprint == first.history_context.fingerprint
    assert service.get_qualification_history_as_of(
        request.artifact_reference, knowledge_as_of=first.available_at
    ) == (first,)
    assert (
        service.get_qualification_history_as_of(
            request.artifact_reference,
            knowledge_as_of=first.available_at - timedelta(microseconds=1),
        )
        == ()
    )


def test_effective_after_knowledge_refuses():
    service, request = _ready()
    with pytest.raises(q.PolygonCompletedDailyQualificationRefused):
        replace(request, knowledge_as_of=request.analysis_as_of - timedelta(seconds=1))


@pytest.mark.parametrize("phase", ["capture", "complete", "publish"])
def test_backward_clock_fails_closed(phase):
    service, request = _ready()
    t = request.analysis_as_of
    values = {
        "capture": [t, t - timedelta(seconds=1)],
        "complete": [t, t + timedelta(seconds=3), t],
        "publish": [t, t + timedelta(seconds=3), t + timedelta(seconds=4), t],
    }
    service._clock = _Clock(*values[phase])
    _refuse(service, request)


def test_failed_publication_has_no_visible_success(monkeypatch):
    service, request = _ready()

    def fail(store, result):
        store._pending = result
        assert store._state == (1, ())
        raise RuntimeError("publication failed")

    monkeypatch.setattr(q._QualificationHistory, "_stage_publication", fail)
    _refuse(service, request, R.PUBLICATION_FAILED)


def test_duplicate_execution_records_do_not_conflict():
    service, request = _ready(constant=True)
    source = service._validity_service._admission_service
    retained = source._validation_service._history._state[1]
    source._validation_service._execution_clock = lambda: (
        retained[-1].companion.execution_completed_at
    )
    source._validation_service.execute_profile(
        q.v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    result = service.qualify(request)
    assert len(result.history_context.validations) == 16
    assert len(result.canonical_state.selected_validation_record_references) == 8


@pytest.mark.parametrize(
    "kind", ["consumer", "use", "analysis_profile", "transformation"]
)
def test_lookalike_profile_refuses(kind, monkeypatch):
    service, request = _ready()
    changed = replace(getattr(q._PROFILE, kind), configuration=(("lookalike", True),))
    monkeypatch.setattr(q, "_PROFILE", replace(q._PROFILE, **{kind: changed}))
    _refuse(service, request, R.PROFILE_MISMATCH)


def test_request_has_only_intent_and_references():
    assert {
        item.name for item in fields(q.PolygonCompletedDailyQualificationRequest)
    } == {
        "artifact_reference",
        "construction_execution_id",
        "analysis_as_of",
        "knowledge_as_of",
    }
    assert not hasattr(q.PolygonCompletedDailyQualifiedUse, "from_dict")
    assert (
        "history"
        not in inspect.signature(
            q.PolygonCompletedDailyProductionQualificationApplicationService
        ).parameters
    )
    assert len(evidence.__all__) == len(set(evidence.__all__)) == 69


@pytest.mark.parametrize(
    "valid_from,passes",
    [
        (datetime(2020, 1, 1, tzinfo=UTC), True),
        (datetime(2026, 8, 28, tzinfo=UTC), False),
        (datetime(2020, 1, 1, 1, tzinfo=UTC), False),
    ],
)
def test_whole_mapping_coverage_and_partial_day(valid_from, passes):
    _, target = _construction(mapping=_mapping(valid_from=valid_from))
    analysis = target.receipt.available_at
    if passes:
        _, dates = q._qualify_material(target, analysis, analysis)
        assert dates == tuple(row.session_date for row in target.material.rows)
    else:
        with pytest.raises(q.PolygonCompletedDailyQualificationRefused) as caught:
            q._qualify_material(target, analysis, analysis)
        assert caught.value.reason is R.MAPPING_FAILURE
        assert len(target.material.rows) == 2


def test_whole_material_completion_no_drop():
    _, target = _construction()
    cutoff = target.receipt.available_at
    with pytest.raises(q.PolygonCompletedDailyQualificationRefused) as caught:
        q._qualify_material(target, datetime(2026, 8, 28, 16, tzinfo=UTC), cutoff)
    assert caught.value.reason is R.INCOMPLETE_MATERIAL
    assert len(target.material.rows) == 2


def test_mapping_context_must_be_available():
    _, target = _construction()
    with pytest.raises(q.PolygonCompletedDailyQualificationRefused) as caught:
        q._qualify_material(
            target,
            target.receipt.available_at,
            target.receipt.available_at - timedelta(microseconds=1),
        )
    assert caught.value.reason is R.INPUT_UNAVAILABLE


@pytest.mark.parametrize(
    "disposition",
    [
        evidence.EvidenceValidationDisposition.REJECTED,
        evidence.EvidenceValidationDisposition.UNABLE_TO_VALIDATE,
    ],
)
def test_authentic_adverse_validation_reaches_canonical(disposition, monkeypatch):
    from test_polygon_completed_daily_production_admission_validity import (
        _historical_rule_fixture,
    )

    service, request = _ready()
    validator = service._validity_service._admission_service._validation_service
    original = q.v._evaluate_definition

    def adverse(definition, support):
        if definition.requirement.concern is evidence.EvidenceValidationConcern.SCHEMA:
            return q.v._RuleConclusion(disposition, ("Controlled adverse execution.",))
        return original(definition, support)

    _historical_rule_fixture(monkeypatch, validator._history._state[1], adverse)
    validator._execution_clock = lambda: request.analysis_as_of - timedelta(seconds=1)
    validator.execute_profile(
        q.v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    refused = _refuse(service, request, R.LIFECYCLE_REFUSED)
    assert any(
        item.disposition is disposition
        for item in refused.canonical_state.selected_validation_record_references
    )


def test_genuine_lifecycle_conflict_remains_conflict(monkeypatch):
    from test_polygon_completed_daily_production_admission_validity import (
        _historical_rule_fixture,
    )

    service, request = _ready(constant=True)
    validator = service._validity_service._admission_service._validation_service
    original = q.v._evaluate_definition

    def different(definition, support):
        conclusion = original(definition, support)
        return replace(
            conclusion, findings=(*conclusion.findings, "Distinct authentic record.")
        )

    entries = validator._history._state[1]
    _historical_rule_fixture(monkeypatch, entries, different)
    validator._execution_clock = lambda: entries[-1].companion.execution_completed_at
    validator.execute_profile(
        q.v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    _refuse(service, request, R.LIFECYCLE_REFUSED)


def test_carried_time_before_k_with_publication_after_k_is_excluded():
    service, request = _ready()
    first = service.qualify(request)
    validator = service._validity_service._admission_service._validation_service
    before = request.analysis_as_of - timedelta(seconds=1)
    after = first.available_at + timedelta(seconds=10)
    validator._execution_clock = _Clock(*([before, before, after] * 8))
    later = validator.execute_profile(
        q.v.PolygonCompletedDailyValidationRequest(
            request.artifact_reference, request.construction_execution_id
        )
    )
    assert all(
        item.validation_record.recorded_at
        < first.knowledge_as_of
        < item.companion.available_at
        for item in later
    )
    service._clock = lambda: after + timedelta(seconds=1)
    replay = service.qualify(replace(request, knowledge_as_of=first.knowledge_as_of))
    assert replay.history_context.validations == first.history_context.validations


def _custom_construction(*, mappings=None, rows=None):
    import asyncio

    from test_polygon_completed_daily_production_validation import _row

    service, original = _construction(
        rows=(_row(date(2026, 8, 27)),) if rows is None else rows
    )
    request = (
        original.request
        if mappings is None
        else replace(original.request, mappings=mappings)
    )
    candidate = service._candidate_service
    new = q.c.PolygonCompletedDailyProductionConstructionApplicationService(
        candidate._acquirer,
        creation_clock=candidate._creation_clock,
        execution_clock=_Clock(
            original.receipt.execution_started_at,
            original.receipt.execution_completed_at,
            original.receipt.available_at,
        ),
    )
    return new, asyncio.run(new.execute(request))


def _from_construction(constructor, target):
    instant = target.receipt.available_at + timedelta(minutes=1)
    validator = q.v.PolygonCompletedDailyProductionValidationApplicationService(
        constructor, execution_clock=lambda: instant
    )
    validator.execute_profile(
        q.v.PolygonCompletedDailyValidationRequest(
            target.artifact.reference(), target.receipt.execution_id
        )
    )
    fresh = q.f.PolygonCompletedDailyProductionFreshnessApplicationService(
        constructor, execution_clock=lambda: instant
    )
    fresh.execute_admission(
        q.f.PolygonCompletedDailyAdmissionFreshnessRequest(
            target.artifact.reference(), target.receipt.execution_id
        )
    )
    issuer = q.a.PolygonCompletedDailyProductionAdmissionApplicationService(
        constructor,
        validator,
        fresh,
        execution_clock=lambda: instant + timedelta(seconds=1),
    )
    issuer.issue_admission(
        q.a.PolygonCompletedDailyAdmissionRequest(
            target.artifact.reference(), target.receipt.execution_id
        )
    )
    active, intent = _activate(
        issuer,
        q.a.PolygonCompletedDailyAdmissionRequest(
            target.artifact.reference(), target.receipt.execution_id
        ),
        instant + timedelta(seconds=2),
    )
    active.issue_initial_active(intent)
    analysis = instant + timedelta(seconds=3)
    fresh._execution_clock = lambda: analysis
    return q.PolygonCompletedDailyProductionQualificationApplicationService(
        active, execution_clock=lambda: analysis
    ), q.PolygonCompletedDailyQualificationRequest(
        target.artifact.reference(), target.receipt.execution_id, analysis
    )


def test_one_row_sparse_history_qualifies_without_bridge_or_provider(monkeypatch):
    constructor, target = _custom_construction()
    service, request = _from_construction(constructor, target)

    def forbidden(*args, **kwargs):
        raise AssertionError("bridge/research/provider is out of scope")

    import market_platform.research.daily_evidence as representation
    import market_platform.research.technical_analysis as research

    monkeypatch.setattr(research, "analyze_daily_technical_snapshot", forbidden)

    monkeypatch.setattr(
        representation, "prepare_completed_daily_price_series", forbidden
    )
    monkeypatch.setattr(
        type(constructor._candidate_service._acquirer),
        "get_completed_daily_acquisition",
        forbidden,
    )
    result = service.qualify(request)
    assert result.original_row_count == 1
    assert result.construction_result.material is target.material
    assert result.production_profile.transformation == q._PROFILE.transformation


@pytest.mark.parametrize(
    "kind", ["outside", "partial_day", "ambiguous", "conflicting", "different_subject"]
)
def test_historical_mapping_whole_use_refusal_after_canonical(kind):
    from test_polygon_completed_daily_production_validation import _row

    current = _mapping()
    if kind == "outside":
        mappings = (replace(current, valid_from=datetime(2026, 8, 28, tzinfo=UTC)),)
    elif kind == "partial_day":
        mappings = (replace(current, valid_from=datetime(2020, 1, 1, 1, tzinfo=UTC)),)
    else:
        historical = replace(current, expires_at=datetime(2026, 8, 28, tzinfo=UTC))
        if kind in ("conflicting", "different_subject"):
            from market_platform.instruments import CanonicalInstrumentId

            historical = replace(
                historical,
                canonical_instrument=replace(
                    current.canonical_instrument,
                    instrument_id=CanonicalInstrumentId("us_equity.OTHER"),
                ),
            )
        if kind == "different_subject":
            current = replace(current, valid_from=datetime(2026, 8, 28, tzinfo=UTC))
        mappings = (current, historical)
    constructor, target = _custom_construction(
        mappings=mappings, rows=(_row(date(2026, 8, 27)), _row(date(2026, 8, 28)))
    )
    service, request = _from_construction(constructor, target)
    _refuse(service, request, R.MAPPING_FAILURE)
    assert len(target.material.rows) == 2


def test_terminal_canonical_state_cannot_be_overridden(monkeypatch):
    # Slice 5 releases initial ACTIVE only; this seam tests canonical terminal
    # refusal without inventing a production terminal issuance service.
    service, request = _ready()
    original = q.evaluation.evaluate_evidence_admission_as_of

    def terminal(**kwargs):
        active = kwargs["validity_events"][0]
        event = evidence.create_evidence_validity_event(
            validity_event_id="terminal.test",
            artifact_reference=active.artifact_reference,
            status=evidence.EvidenceValidityStatus.REVOKED,
            recorded_at=kwargs["effective_as_of"],
            effective_at=kwargs["effective_as_of"],
            actor_identity=active.actor_identity,
            capability_identity=active.capability_identity,
            scope=active.scope,
            predecessor=active,
            reason="Controlled terminal lifecycle fixture.",
        )
        return original(**{**kwargs, "validity_events": (active, event)})

    monkeypatch.setattr(q.evaluation, "evaluate_evidence_admission_as_of", terminal)
    refusal = _refuse(service, request, R.LIFECYCLE_REFUSED)
    assert (
        refusal.canonical_state.selected_validity_reference.status
        is evidence.EvidenceValidityStatus.REVOKED
    )


@pytest.mark.parametrize(
    "kind", ["construction", "validation", "freshness", "admission", "validity"]
)
def test_incomplete_trusted_store_cannot_be_pruned(kind):
    service, request = _ready()
    source = service._validity_service._admission_service
    stores = {
        "construction": source._construction_service._history,
        "validation": source._validation_service._history,
        "freshness": source._freshness_service._history,
        "admission": source._history,
        "validity": service._validity_service._history,
    }
    store = stores[kind]
    next_sequence, entries = store._state
    store._state = (next_sequence, entries[:-1])
    _refuse(service, request, R.HISTORY_INCOMPLETE)
