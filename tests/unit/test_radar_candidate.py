"""Passive correspondence tests; coherent fixtures do not authenticate execution."""

import ast
import importlib
import inspect
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta
from itertools import permutations
from unittest.mock import Mock

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import radar_candidate as subject
from market_platform.application.radar_candidate import (
    RADAR_CANDIDATE_ELIGIBILITY_POLICY_ID,
    RADAR_CANDIDATE_ELIGIBILITY_POLICY_REVISION,
    RADAR_CANDIDATE_ELIGIBILITY_POLICY_SCHEMA,
    RADAR_CANDIDATE_SCHEMA,
    RadarCandidate,
    RadarCandidateDecision,
    evaluate_radar_candidate,
)
from market_platform.application.radar_candidate import (
    RadarCandidateDecisionReason as Reason,
)
from market_platform.application.radar_candidate import (
    RadarCandidateEligibilityPolicyIdentity as Policy,
)
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.application import (
    RadarApplicationResult,
    RadarApplicationService,
    RadarCheckpointAdvancementError,
    RadarObservationPreparationError,
)
from market_platform.radar.application import (
    RadarCheckpointAdvancement as Advancement,
)
from market_platform.radar.calendar import ExchangeSessionCalendar
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.context import RadarEvaluationContext
from market_platform.radar.core import (
    RadarGateDisposition as Disposition,
)
from market_platform.radar.core import (
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
    RadarProfile,
)
from market_platform.radar.core import (
    RadarPipelineOutcome as Outcome,
)
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_CALCULATION_REVISION,
    EMA8_EMA20_OBSERVATION_DEFINITION_ID,
    EMA8_EMA20_OBSERVATION_LOOKUP,
    EMA8_EMA20_OBSERVATION_SCHEMA,
    RadarLightweightObservation,
    RadarLightweightObservationLookupResult,
    RadarLightweightObservationLookupStatus,
)
from market_platform.radar.lightweight_observation import (
    RadarEmaRelation as Relation,
)
from market_platform.radar.meaningful_change import evaluate_meaningful_change
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
)
from market_platform.radar.observation_state import (
    RadarObservationState,
    RadarObservationStateLookupResult,
    RadarObservationStateLookupStatus,
)
from market_platform.radar.pipeline import (
    RadarPipeline,
    RadarPipelineFailure,
    RadarPipelineFailureCategory,
    RadarPipelineResult,
)
from market_platform.radar.resolver import RadarGateFactoryBinding, RadarGateResolver
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP,
    SESSION_CONTENT_TRIGGER_KEY,
    RadarCurrentMarketContent,
    RadarCurrentMarketContentLookupResult,
    RadarCurrentMarketContentLookupStatus,
    RadarSessionContentTriggerGate,
)


def trigger(name="arbitrary-name", **identity_changes):
    key = SESSION_CONTENT_TRIGGER_KEY
    identity = RadarGateIdentity(
        key.gate_id, key.behavioral_revision, key.configuration_schema
    )
    return RadarGateOccurrence(name, replace(identity, **identity_changes))


def other():
    return RadarGateOccurrence(
        "session_content_trigger", RadarGateIdentity("other", "1", "other/v1")
    )


def observation(relation=Relation.ABOVE, *, earlier=False, **changes):
    session = date(2026, 9, 22 if earlier else 23)
    return replace(
        RadarLightweightObservation(
            CanonicalInstrumentId("us-msft"),
            EMA8_EMA20_OBSERVATION_DEFINITION_ID,
            EMA8_EMA20_CALCULATION_REVISION,
            EMA8_EMA20_OBSERVATION_SCHEMA,
            session,
            "sha256:" + ("a" if earlier else "b") * 64,
            RadarMarketContentScope(date(2025, 10, 1), session),
            relation,
            datetime(2026, 9, 24, tzinfo=UTC),
        ),
        **changes,
    )


def pipeline(*, occurrences=None, results=None, profile_id="test", current=None):
    occurrences = (trigger(),) if occurrences is None else occurrences
    current = observation() if current is None else current
    if results is None:
        results = tuple(
            RadarGateResult(g, Disposition.PASS, "NEW_COMPLETED_SESSION")
            for g in occurrences
        )
    return RadarPipelineResult(
        RadarProfile(profile_id, "1", "test/v1", occurrences),
        current.instrument,
        current.as_of,
        results,
    )


def saved(*, current=None, prior=None, baseline=False, result=None, observed_at=None):
    current = observation() if current is None else current
    if prior is None and not baseline:
        prior = observation(Relation.BELOW, earlier=True)
    if result is None:
        reason = "BASELINE_REQUIRED" if baseline else "NEW_COMPLETED_SESSION"
        if prior is not None and prior.completed_session == current.completed_session:
            reason = "MARKET_CONTENT_CHANGED"
        result = pipeline(
            current=current,
            results=(RadarGateResult(trigger(), Disposition.PASS, reason),),
        )
    checkpoint = RadarObservationCheckpoint(
        current.instrument,
        current.completed_session,
        current.normalized_market_content_identity,
        observed_at or current.as_of,
        current.content_scope,
    )
    decision = evaluate_meaningful_change(prior, current)
    state = RadarObservationState(
        checkpoint, current, decision, result.profile.fingerprint, result.outcome
    )
    return RadarApplicationResult(
        result, Advancement.SAVED, checkpoint, decision, state
    )


def evaluate(value):
    return evaluate_radar_candidate(value, policy=Policy())


def assert_reason(value, reason):
    decision = evaluate(value)
    assert decision.reason is reason
    assert decision.eligible is (reason is Reason.ELIGIBLE)
    assert (decision.candidate is not None) is decision.eligible
    return decision


def test_closed_policy_constants_and_projection():
    assert RADAR_CANDIDATE_SCHEMA == "radar_candidate/v1"
    assert RADAR_CANDIDATE_ELIGIBILITY_POLICY_ID == "selected_meaningful_transition"
    assert RADAR_CANDIDATE_ELIGIBILITY_POLICY_REVISION == "1"
    assert (
        RADAR_CANDIDATE_ELIGIBILITY_POLICY_SCHEMA
        == "radar_candidate_eligibility_policy/v1"
    )
    policy = Policy()
    assert policy.to_dict() == {
        "policy_id": RADAR_CANDIDATE_ELIGIBILITY_POLICY_ID,
        "behavioral_revision": RADAR_CANDIDATE_ELIGIBILITY_POLICY_REVISION,
        "policy_schema": RADAR_CANDIDATE_ELIGIBILITY_POLICY_SCHEMA,
    }
    projected = policy.to_dict()
    projected.clear()
    assert len(policy.to_dict()) == 3
    assert {r.name: r.value for r in Reason} == {
        name: name
        for name in (
            "NOT_SELECTED",
            "NOT_ADVANCED",
            "NO_MEANINGFUL_TRANSITION",
            "ELIGIBLE",
        )
    }


@pytest.mark.parametrize("name", [f.name for f in fields(Policy)])
@pytest.mark.parametrize("bad", ["unknown", "2", None, 1, True])
def test_unknown_or_nonexact_policy_rejected(name, bad):
    with pytest.raises((TypeError, ValueError)):
        Policy(**{name: bad})


def test_frozen_slotted_contracts_and_derived_fields():
    candidate = evaluate(saved()).candidate
    decision = RadarCandidateDecision(Policy(), Reason.ELIGIBLE, candidate)
    for value in (Policy(), candidate, decision):
        assert not hasattr(value, "__dict__")
        name = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, name, getattr(value, name))
    assert {f.name for f in fields(candidate)} == {
        "schema_version",
        "source_observation_state",
        "eligibility_policy",
        "fingerprint",
    }
    assert {f.name for f in fields(decision)} == {"policy", "reason", "candidate"}
    assert not next(f for f in fields(candidate) if f.name == "fingerprint").init
    with pytest.raises(TypeError):
        RadarCandidate(candidate.source_observation_state, Policy(), fingerprint="fake")
    with pytest.raises(TypeError):
        RadarCandidateDecision(Policy(), Reason.ELIGIBLE, candidate, eligible=True)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        decision.eligible = False


@pytest.mark.parametrize("reason", list(Reason))
def test_decision_presence_invariant(reason):
    candidate = evaluate(saved()).candidate
    bad = None if reason is Reason.ELIGIBLE else candidate
    with pytest.raises(ValueError):
        RadarCandidateDecision(Policy(), reason, bad)


def test_decision_rejects_corrupted_candidate_policy():
    candidate = evaluate(saved()).candidate
    # v1 has no second supported policy. Deliberate corruption is rejected.
    object.__setattr__(candidate.eligibility_policy, "behavioral_revision", "2")
    with pytest.raises(ValueError):
        RadarCandidateDecision(Policy(), Reason.ELIGIBLE, candidate)


@pytest.mark.parametrize(
    "field", ["source_observation_state", "eligibility_policy", "schema_version"]
)
@pytest.mark.parametrize("bad", [None, {}, 1, True, "unknown"])
def test_candidate_rejects_invalid_fields(field, bad):
    candidate = evaluate(saved()).candidate
    with pytest.raises((TypeError, ValueError)):
        replace(candidate, **{field: bad})


def test_exact_types_reject_subclasses_and_duck_types():
    value = saved()
    for original in (value, Policy(), value.saved_state):
        child = type("Child", (type(original),), {})
        derived = child(
            **{f.name: getattr(original, f.name) for f in fields(original) if f.init}
        )
        with pytest.raises(TypeError):
            if type(original) is RadarApplicationResult:
                evaluate(derived)
            elif type(original) is Policy:
                evaluate_radar_candidate(value, policy=derived)
            else:
                RadarCandidate(derived, Policy())
    for bad in (None, {}, value.saved_state, Mock()):
        with pytest.raises(TypeError):
            evaluate(bad)
    with pytest.raises(TypeError):
        RadarCandidateDecision(Policy(), "ELIGIBLE", evaluate(value).candidate)


def test_deep_detachment_and_canonical_fingerprint():
    value = saved()
    policy = Policy()
    candidate = RadarCandidate(value.saved_state, policy)
    retained = candidate.source_observation_state
    assert retained == value.saved_state and retained is not value.saved_state
    assert retained.market_observation is not value.saved_checkpoint
    assert (
        retained.lightweight_observation
        is not value.saved_state.lightweight_observation
    )
    assert retained.committed_decision is not value.meaningful_change_decision
    assert (
        retained.committed_decision.prior is not value.meaningful_change_decision.prior
    )
    assert (
        retained.lightweight_observation.content_scope
        is not value.saved_checkpoint.content_scope
    )
    assert (
        retained.market_observation.instrument is not value.saved_checkpoint.instrument
    )
    assert candidate.eligibility_policy is not policy
    payload = {
        "schema_version": RADAR_CANDIDATE_SCHEMA,
        "source_observation_state": value.saved_state.to_dict(),
        "eligibility_policy": policy.to_dict(),
    }
    assert candidate.fingerprint == canonical_fingerprint(payload)
    assert (
        candidate.fingerprint == RadarCandidate(value.saved_state, Policy()).fingerprint
    )
    expected = candidate.to_dict()
    projection = candidate.to_dict()
    projection["source_observation_state"]["committed_decision"]["prior"].clear()
    projection["eligibility_policy"].clear()
    assert candidate.to_dict() == expected
    object.__setattr__(
        value.saved_checkpoint, "observed_at", datetime(2030, 1, 1, tzinfo=UTC)
    )
    assert candidate.to_dict() == expected


@pytest.mark.parametrize(
    "prior_relation,current_relation", list(permutations(Relation, 2))
)
@pytest.mark.parametrize("corrected", [False, True])
def test_all_six_transitions_without_directional_preference(
    prior_relation, current_relation, corrected
):
    current = observation(current_relation)
    prior = observation(prior_relation, earlier=not corrected)
    if corrected:
        prior = replace(prior, normalized_market_content_identity="sha256:" + "a" * 64)
    value = saved(current=current, prior=prior)
    decision = assert_reason(value, Reason.ELIGIBLE)
    assert decision.candidate.source_observation_state == value.saved_state
    assert value.meaningful_change_decision.reason.value == (
        "CORRECTED_CONTENT_STATE_TRANSITION"
        if corrected
        else "NEW_SESSION_STATE_TRANSITION"
    )


@pytest.mark.parametrize("kind", ["baseline", "incomparable", "unchanged"])
def test_selected_saved_nontransitions(kind):
    prior = observation(Relation.ABOVE, earlier=True)
    if kind == "incomparable":
        prior = replace(prior, definition_id="old_observation")
    value = saved(
        baseline=kind == "baseline", prior=None if kind == "baseline" else prior
    )
    assert_reason(value, Reason.NO_MEANINGFUL_TRANSITION)
    with pytest.raises(ValueError, match="SELECTED meaningful STATE_TRANSITION"):
        RadarCandidate(value.saved_state, Policy())


@pytest.mark.parametrize(
    "field", ["definition_id", "calculation_revision", "observation_schema"]
)
def test_incompatible_prior_is_valid_provenance(field):
    prior = replace(observation(Relation.BELOW, earlier=True), **{field: "old"})
    assert_reason(saved(prior=prior), Reason.NO_MEANINGFUL_TRANSITION)


def test_filtered_saved_transition_stays_not_selected():
    occurrences = (trigger(), other())
    result = pipeline(
        occurrences=occurrences,
        results=(
            RadarGateResult(occurrences[0], Disposition.PASS, "NEW_COMPLETED_SESSION"),
            RadarGateResult(occurrences[1], Disposition.DROP, "FILTER"),
        ),
    )
    value = saved(result=result)
    assert value.meaningful_change_decision.meaningful_change
    assert_reason(value, Reason.NOT_SELECTED)
    with pytest.raises(ValueError, match="SELECTED meaningful STATE_TRANSITION"):
        RadarCandidate(value.saved_state, Policy())
    # A later selected observation with unchanged relation cannot backfill it.
    current = observation(earlier=False)
    current = replace(current, normalized_market_content_identity="sha256:" + "c" * 64)
    assert_reason(
        saved(current=current, prior=value.saved_state.lightweight_observation),
        Reason.NO_MEANINGFUL_TRANSITION,
    )


@pytest.mark.parametrize("outcome", list(Outcome))
def test_not_advanced_matrix(outcome):
    if outcome is Outcome.FAILED:
        result = RadarPipelineResult(
            pipeline().profile,
            observation().instrument,
            observation().as_of,
            (),
            RadarPipelineFailure(
                trigger(), RadarPipelineFailureCategory.GATE_EXCEPTION
            ),
        )
    else:
        disposition = {
            Outcome.SELECTED: Disposition.PASS,
            Outcome.FILTERED: Disposition.DROP,
            Outcome.ATTENTION: Disposition.ATTENTION,
        }[outcome]
        result = pipeline(
            results=(RadarGateResult(trigger(), disposition, "UNCHANGED"),)
        )
    assert result.outcome is outcome
    assert_reason(
        RadarApplicationResult(result, Advancement.NOT_ADVANCED),
        Reason.NOT_ADVANCED if outcome is Outcome.SELECTED else Reason.NOT_SELECTED,
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_actual_application_unchanged_retry_and_legacy_bootstrap(legacy):
    current = observation()
    complete = saved().saved_state
    lookup = RadarObservationStateLookupResult(
        RadarObservationStateLookupStatus.LEGACY_CONTENT_ONLY
        if legacy
        else RadarObservationStateLookupStatus.PRESENT_COMPLETE_STATE,
        legacy_checkpoint=complete.market_observation if legacy else None,
        state=None if legacy else complete,
    )
    store = Mock(spec=RadarCheckpointFileStore)
    store.lookup_state.return_value = lookup
    calendar = Mock(spec=ExchangeSessionCalendar)
    calendar.latest_completed_session.return_value = current.completed_session
    calendar.is_session.return_value = True
    resolver = RadarGateResolver(
        [
            RadarGateFactoryBinding(
                SESSION_CONTENT_TRIGGER_KEY,
                lambda occurrence: RadarSessionContentTriggerGate(occurrence, calendar),
            )
        ]
    )
    clock = Mock(return_value=current.as_of)
    service = RadarApplicationService(resolver, store, clock)
    content = RadarCurrentMarketContent(
        current.instrument,
        current.completed_session,
        current.normalized_market_content_identity,
        current.content_scope,
    )
    loaders = {
        CURRENT_MARKET_CONTENT_LOOKUP: lambda: RadarCurrentMarketContentLookupResult(
            RadarCurrentMarketContentLookupStatus.PRESENT, content
        ),
        EMA8_EMA20_OBSERVATION_LOOKUP: lambda: RadarLightweightObservationLookupResult(
            RadarLightweightObservationLookupStatus.PRESENT, current
        ),
    }
    value = service.evaluate(
        pipeline().profile, current.instrument, current.as_of, loaders
    )
    assert value.pipeline_result.outcome is Outcome.FILTERED
    actual = value.pipeline_result.executed_results[0]
    assert actual.disposition is Disposition.DROP and actual.reason_code == "UNCHANGED"
    assert value.advancement is (
        Advancement.SAVED if legacy else Advancement.NOT_ADVANCED
    )
    if legacy:
        assert value.meaningful_change_decision.reason.value == "BASELINE_INITIALIZED"
        assert not value.meaningful_change_decision.meaningful_change
        store.save_state.assert_called_once()
    else:
        store.save_state.assert_not_called()
        clock.assert_not_called()
    assert_reason(value, Reason.NOT_SELECTED)


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "skipped",
        "impostor",
        "multiple",
        "reason",
        "drop",
        "baseline_transition",
        "configuration",
        "wrong_revision",
        "wrong_schema",
    ],
)
def test_saved_trigger_contradictions_raise_before_precedence(case):
    occurrences = (trigger(),)
    results = (
        RadarGateResult(occurrences[0], Disposition.PASS, "NEW_COMPLETED_SESSION"),
    )
    if case in {"missing", "impostor"}:
        occurrences = (other(),)
        results = (
            RadarGateResult(
                other(),
                Disposition.PASS,
                "NEW_COMPLETED_SESSION" if case == "impostor" else "OK",
            ),
        )
    elif case == "skipped":
        occurrences = (other(), trigger())
        results = (RadarGateResult(other(), Disposition.DROP, "FILTER"),)
    elif case == "multiple":
        occurrences = (trigger(), trigger("second"))
        results = tuple(
            RadarGateResult(g, Disposition.PASS, "NEW_COMPLETED_SESSION")
            for g in occurrences
        )
    elif case in {"configuration", "wrong_revision", "wrong_schema"}:
        changes = (
            {"configuration": {"extra": True}}
            if case == "configuration"
            else {
                "behavioral_revision"
                if case == "wrong_revision"
                else "configuration_schema": "other"
            }
        )
        occurrences = (trigger(**changes),)
        results = (
            RadarGateResult(occurrences[0], Disposition.PASS, "NEW_COMPLETED_SESSION"),
        )
    else:
        reason = (
            "BASELINE_REQUIRED"
            if case == "baseline_transition"
            else "NEW_COMPLETED_SESSION"
            if case == "drop"
            else "UNCHANGED"
        )
        results = (
            RadarGateResult(
                trigger(),
                Disposition.DROP if case == "drop" else Disposition.PASS,
                reason,
            ),
        )
    value = saved(result=pipeline(occurrences=occurrences, results=results))
    with pytest.raises(ValueError):
        evaluate(value)


@pytest.mark.parametrize(
    "reason", ["NEW_COMPLETED_SESSION", "MARKET_CONTENT_CHANGED", "BASELINE_REQUIRED"]
)
def test_trigger_reason_must_match_available_comparison_provenance(reason):
    corrected = reason == "NEW_COMPLETED_SESSION"
    prior = observation(Relation.BELOW, earlier=not corrected)
    if corrected:
        prior = replace(prior, normalized_market_content_identity="sha256:" + "a" * 64)
    value = saved(
        prior=prior,
        result=pipeline(
            results=(RadarGateResult(trigger(), Disposition.PASS, reason),)
        ),
    )
    with pytest.raises(ValueError):
        evaluate(value)


@pytest.mark.parametrize(
    "reason", ["NEW_COMPLETED_SESSION", "MARKET_CONTENT_CHANGED", "BASELINE_REQUIRED"]
)
def test_ordinary_saved_without_technical_prior_allows_qualifying_pass(reason):
    value = saved(
        baseline=True,
        result=pipeline(
            results=(RadarGateResult(trigger(), Disposition.PASS, reason),)
        ),
    )
    assert value.meaningful_change_decision.prior is None
    assert value.meaningful_change_decision.reason.value == "BASELINE_INITIALIZED"
    assert not value.meaningful_change_decision.meaningful_change
    assert_reason(value, Reason.NO_MEANINGFUL_TRANSITION)
    with pytest.raises(ValueError, match="SELECTED meaningful STATE_TRANSITION"):
        RadarCandidate(value.saved_state, Policy())


@pytest.mark.parametrize("reason", ["NEW_COMPLETED_SESSION", "MARKET_CONTENT_CHANGED"])
def test_actual_application_legacy_qualifying_pass_initializes_baseline(
    tmp_path, reason
):
    current = observation()
    prior_session = (
        current.completed_session - timedelta(days=1)
        if reason == "NEW_COMPLETED_SESSION"
        else current.completed_session
    )
    predecessor = RadarObservationCheckpoint(
        current.instrument,
        prior_session,
        "sha256:" + "a" * 64,
        current.as_of - timedelta(days=1),
        replace(current.content_scope, history_end=prior_session),
    )
    store = RadarCheckpointFileStore(tmp_path)
    store.save(predecessor)
    retained = store.lookup_state(current.instrument)
    assert retained.status is RadarObservationStateLookupStatus.LEGACY_CONTENT_ONLY
    assert retained.legacy_checkpoint == predecessor
    assert retained.state is None
    calendar = Mock(spec=ExchangeSessionCalendar)
    calendar.latest_completed_session.return_value = current.completed_session
    calendar.is_session.return_value = True
    resolver = RadarGateResolver(
        [
            RadarGateFactoryBinding(
                SESSION_CONTENT_TRIGGER_KEY,
                lambda occurrence: RadarSessionContentTriggerGate(occurrence, calendar),
            )
        ]
    )
    service = RadarApplicationService(resolver, store, lambda: current.as_of)
    content = RadarCurrentMarketContent(
        current.instrument,
        current.completed_session,
        current.normalized_market_content_identity,
        current.content_scope,
    )
    value = service.evaluate(
        pipeline().profile,
        current.instrument,
        current.as_of,
        {
            CURRENT_MARKET_CONTENT_LOOKUP: lambda: (
                RadarCurrentMarketContentLookupResult(
                    RadarCurrentMarketContentLookupStatus.PRESENT, content
                )
            ),
            EMA8_EMA20_OBSERVATION_LOOKUP: lambda: (
                RadarLightweightObservationLookupResult(
                    RadarLightweightObservationLookupStatus.PRESENT, current
                )
            ),
        },
    )
    assert value.advancement is Advancement.SAVED
    assert value.pipeline_result.outcome is Outcome.SELECTED
    actual = value.pipeline_result.executed_results[0]
    assert actual.occurrence == trigger()
    assert actual.disposition is Disposition.PASS
    assert actual.reason_code == reason
    assert (
        value.meaningful_change_decision.classification.value == "BASELINE_INITIALIZED"
    )
    assert value.meaningful_change_decision.prior is None
    assert not value.meaningful_change_decision.meaningful_change
    assert (
        RadarCheckpointFileStore(tmp_path).lookup_state(current.instrument).state
        == value.saved_state
    )
    assert_reason(value, Reason.NO_MEANINGFUL_TRANSITION)
    with pytest.raises(ValueError, match="SELECTED meaningful STATE_TRANSITION"):
        RadarCandidate(value.saved_state, Policy())


@pytest.mark.parametrize(
    "field", ["definition_id", "calculation_revision", "observation_schema"]
)
def test_direct_candidate_rejects_unsupported_current_transition_semantics(field):
    # Matching unsupported identities remain a structurally valid transition.
    current = replace(observation(), **{field: "unsupported"})
    prior = replace(observation(Relation.BELOW, earlier=True), **{field: "unsupported"})
    state = saved(current=current, prior=prior).saved_state
    assert state.pipeline_outcome is Outcome.SELECTED
    assert state.committed_decision.meaningful_change
    with pytest.raises(ValueError, match="Unsupported current observation semantics"):
        RadarCandidate(state, Policy())


def test_direct_candidate_validates_state_without_authenticating_application():
    # A coherent state alone cannot establish Trigger execution or a disk commit.
    value = saved(result=pipeline(occurrences=(other(),)))
    state = RadarObservationState.from_dict(value.saved_state.to_dict())
    candidate = RadarCandidate(state, Policy())
    decision = RadarCandidateDecision(Policy(), Reason.ELIGIBLE, candidate)
    assert decision.eligible
    assert candidate.source_observation_state == state
    assert set(candidate.to_dict()) == {
        "schema_version",
        "source_observation_state",
        "eligibility_policy",
        "fingerprint",
    }
    # Application-level provenance remains the evaluator's responsibility.
    with pytest.raises(ValueError, match="Session/Content Trigger"):
        evaluate(value)


def test_drop_unchanged_cannot_disguise_transition_as_legacy_bootstrap():
    result = pipeline(
        results=(RadarGateResult(trigger(), Disposition.DROP, "UNCHANGED"),)
    )
    with pytest.raises(ValueError):
        evaluate(saved(result=result))


@pytest.mark.parametrize(
    "field", ["definition_id", "calculation_revision", "observation_schema"]
)
@pytest.mark.parametrize("filtered", [False, True])
def test_unsupported_current_semantics_fail_closed(field, filtered):
    current = replace(observation(), **{field: "unsupported"})
    occurrences = (trigger(), other())
    results = (
        RadarGateResult(trigger(), Disposition.PASS, "NEW_COMPLETED_SESSION"),
        RadarGateResult(
            other(), Disposition.DROP if filtered else Disposition.PASS, "OK"
        ),
    )
    value = saved(
        current=current, result=pipeline(occurrences=occurrences, results=results)
    )
    with pytest.raises(ValueError, match="Unsupported current"):
        evaluate(value)


@pytest.mark.parametrize(
    "corruption",
    [
        "checkpoint",
        "decision",
        "state_instrument",
        "profile",
        "as_of",
        "outcome",
        "executed_occurrence",
        "profile_fingerprint",
        "gate_fingerprint",
        "result_disposition",
        "policy_id",
        "policy_revision",
        "policy_schema",
        "scope_schema",
    ],
)
def test_revalidates_corrupted_nested_contracts(corruption):
    value = saved()
    state = value.saved_state
    if corruption == "checkpoint":
        object.__setattr__(
            value,
            "saved_checkpoint",
            replace(
                value.saved_checkpoint,
                observed_at=value.saved_checkpoint.observed_at + timedelta(seconds=1),
            ),
        )
    elif corruption == "decision":
        object.__setattr__(
            value,
            "meaningful_change_decision",
            evaluate_meaningful_change(None, state.lightweight_observation),
        )
    elif corruption == "state_instrument":
        object.__setattr__(
            value.pipeline_result, "instrument", CanonicalInstrumentId("other")
        )
    elif corruption == "profile":
        object.__setattr__(state, "profile_fingerprint", "sha256:" + "f" * 64)
    elif corruption == "as_of":
        object.__setattr__(
            value.pipeline_result,
            "as_of",
            value.pipeline_result.as_of + timedelta(seconds=1),
        )
    elif corruption == "outcome":
        object.__setattr__(state, "pipeline_outcome", Outcome.FILTERED)
    elif corruption == "executed_occurrence":
        object.__setattr__(
            value.pipeline_result.executed_results[0], "occurrence", other()
        )
    elif corruption in {"profile_fingerprint", "gate_fingerprint"}:
        target = (
            value.pipeline_result.profile
            if corruption == "profile_fingerprint"
            else value.pipeline_result.profile.gates[0].gate_identity
        )
        object.__setattr__(target, "fingerprint", "sha256:" + "f" * 64)
        if corruption == "profile_fingerprint":
            object.__setattr__(state, "profile_fingerprint", target.fingerprint)
    elif corruption == "result_disposition":
        object.__setattr__(
            value.pipeline_result.executed_results[0], "disposition", "PASS"
        )
    elif corruption == "scope_schema":
        object.__setattr__(
            state.lightweight_observation.content_scope, "schema_version", "unknown"
        )
    else:
        field = {
            "policy_id": "policy_id",
            "policy_revision": "behavioral_revision",
            "policy_schema": "decision_schema",
        }[corruption]
        object.__setattr__(state.committed_decision.policy, field, "unknown")
    with pytest.raises((TypeError, ValueError)):
        evaluate(value)


def test_not_selected_does_not_hide_invalid_result_or_saved_claim():
    result = pipeline(
        results=(RadarGateResult(trigger(), Disposition.DROP, "UNCHANGED"),)
    )
    value = RadarApplicationResult(result, Advancement.NOT_ADVANCED)
    object.__setattr__(value, "saved_state", saved().saved_state)
    with pytest.raises(ValueError):
        evaluate(value)
    value = RadarApplicationResult(result, Advancement.NOT_ADVANCED)
    object.__setattr__(result.executed_results[0], "reason_code", "invalid reason")
    with pytest.raises(ValueError):
        evaluate(value)


def test_preparation_and_save_errors_are_not_application_results():
    value = saved()
    for prepared in (
        value.saved_state,
        RadarObservationPreparationError(value.pipeline_result),
        RadarCheckpointAdvancementError(value.pipeline_result, value.saved_state),
    ):
        with pytest.raises(TypeError):
            evaluate(prepared)


@pytest.mark.parametrize(
    "change", ["instrument", "profile", "prior", "current", "observed_at", "as_of"]
)
def test_complete_source_participates_in_fingerprint(change):
    original = saved()
    current = observation()
    prior = observation(Relation.BELOW, earlier=True)
    observed_at = current.as_of
    profile_id = "test"
    if change == "instrument":
        current = replace(current, instrument=CanonicalInstrumentId("us-aapl"))
        prior = replace(prior, instrument=current.instrument)
    elif change == "profile":
        profile_id = "different-profile"
    elif change == "prior":
        prior = replace(prior, relation=Relation.EQUAL)
    elif change == "current":
        current = replace(current, relation=Relation.EQUAL)
    elif change == "observed_at":
        observed_at += timedelta(seconds=1)
    else:
        current = replace(current, as_of=current.as_of + timedelta(seconds=1))
    changed = saved(
        current=current,
        prior=prior,
        observed_at=observed_at,
        result=pipeline(current=current, profile_id=profile_id),
    )
    assert (
        evaluate(original).candidate.fingerprint
        != evaluate(changed).candidate.fingerprint
    )


def test_projection_field_graph_is_json_safe_detached_and_without_authority():
    value = evaluate(saved())
    projection = value.to_dict()
    assert set(projection) == {"policy", "reason", "candidate"}
    assert set(projection["candidate"]) == {
        "schema_version",
        "source_observation_state",
        "eligibility_policy",
        "fingerprint",
    }
    forbidden = {
        "BUY",
        "SELL",
        "HOLD",
        "target",
        "stop",
        "position_size",
        "recommendation",
        "order",
        "broker",
        "EvidenceArtifact",
        "admitted",
        "consumable",
        "research_result",
        "strategy",
        "ranking",
        "score",
        "priority",
        "delivery_status",
        "retry_count",
        "created_at",
        "accepted_at",
        "uuid",
    }

    def check(node):
        if type(node) is dict:
            assert not (node.keys() & forbidden)
            for item in node.values():
                check(item)
        elif type(node) is list:
            for item in node:
                check(item)

    check(projection)
    assert json.loads(json.dumps(projection)) == projection
    assert json.dumps(projection) == json.dumps(value.to_dict())
    projection["candidate"]["source_observation_state"].clear()
    projection["policy"].clear()
    assert value.to_dict() != projection


def test_evaluation_is_pure_and_does_not_mutate_input(monkeypatch):
    value = saved()
    before = (
        value.pipeline_result.profile.to_dict(),
        value.saved_state.to_dict(),
        repr(value),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Candidate must not call runtime services")

    for cls, method in (
        (RadarEvaluationContext, "get_fact"),
        (RadarCheckpointFileStore, "lookup_state"),
        (RadarCheckpointFileStore, "save_state"),
        (ExchangeSessionCalendar, "latest_completed_session"),
        (RadarPipeline, "evaluate"),
        (RadarApplicationService, "evaluate"),
    ):
        monkeypatch.setattr(cls, method, forbidden)
    # Inspect the narrow dependency graph: no clock, provider, filesystem,
    # calendar, Context, or governed research capability is bound in this module.
    allowed_imports = {
        "dataclasses",
        "enum",
        "market_platform._fingerprint",
        "market_platform.radar.application",
        "market_platform.radar.core",
        "market_platform.radar.lightweight_observation",
        "market_platform.radar.meaningful_change",
        "market_platform.radar.observation_state",
        "market_platform.radar.pipeline",
        "market_platform.radar.resolver",
        "market_platform.radar.trigger",
    }
    tree = ast.parse(inspect.getsource(subject))
    assert {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } <= allowed_imports
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    assert not {"open", "eval", "exec", "__import__"} & {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert_reason(value, Reason.ELIGIBLE)
    assert before == (
        value.pipeline_result.profile.to_dict(),
        value.saved_state.to_dict(),
        repr(value),
    )


def test_import_does_not_activate_or_reexport_candidate():
    modules = [
        importlib.import_module(name)
        for name in (
            "market_platform.application",
            "market_platform.radar.application",
            "market_platform.application.radar_single_symbol",
            "market_platform.application.radar_batch",
            "market_platform.radar.pipeline",
            "market_platform.radar.core",
            "market_platform.radar.trigger",
            "market_platform.radar.checkpoint_store",
        )
    ]
    before = [dict(vars(module)) for module in modules]
    # Execute a fresh copy without disturbing the classes used by other tests.
    namespace = {"__name__": subject.__name__}
    exec(compile(inspect.getsource(subject), subject.__file__, "exec"), namespace)
    for module, original in zip(modules, before, strict=True):
        assert dict(vars(module)) == original
        assert "RadarCandidate" not in vars(module)
        assert "evaluate_radar_candidate" not in vars(module)
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "radar_candidate" not in (node.module or "").split(".")
                assert all(alias.name != "radar_candidate" for alias in node.names)
            elif isinstance(node, ast.Import):
                assert all(
                    "radar_candidate" not in alias.name.split(".")
                    for alias in node.names
                )
