"""FAST PURE / LOCAL APPLICATION orchestration tests."""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar import application as subject
from market_platform.radar.application import (
    RadarApplicationConfigurationError,
    RadarApplicationResult,
    RadarApplicationService,
    RadarCheckpointAdvancement,
    RadarCheckpointAdvancementError,
    RadarObservationPreparationError,
)
from market_platform.radar.calendar import ExchangeSessionCalendar
from market_platform.radar.checkpoint_store import (
    RadarCheckpointFileStore,
    RadarCheckpointStoreError,
)
from market_platform.radar.context import RadarEvaluationContext, RadarFactKey
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
from market_platform.radar.ema_relation import (
    EMA8_EMA20_RELATION_KEY,
    RadarEma8Ema20RelationGate,
)
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_CALCULATION_REVISION,
    EMA8_EMA20_OBSERVATION_DEFINITION_ID,
    EMA8_EMA20_OBSERVATION_LOOKUP,
    EMA8_EMA20_OBSERVATION_SCHEMA,
    RadarEmaRelation,
    RadarLightweightObservation,
    RadarLightweightObservationLookupResult,
    RadarLightweightObservationLookupStatus,
)
from market_platform.radar.meaningful_change import evaluate_meaningful_change
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
    RadarObservationLookupStatus,
)
from market_platform.radar.observation_state import (
    RadarObservationState,
    RadarObservationStateLookupResult,
    RadarObservationStateLookupStatus,
)
from market_platform.radar.pipeline import RadarPipeline
from market_platform.radar.resolver import (
    RadarGateFactoryBinding,
    RadarGateImplementationKey,
    RadarGateResolver,
    RadarResolutionError,
)
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP,
    PRIOR_OBSERVATION_LOOKUP,
    SESSION_CONTENT_TRIGGER_KEY,
    RadarCurrentMarketContent,
    RadarCurrentMarketContentLookupResult,
    RadarCurrentMarketContentLookupStatus,
    RadarSessionContentTriggerGate,
)

INSTRUMENT = CanonicalInstrumentId("NASDAQ_NVDA")
SESSION = date(2026, 9, 23)
AS_OF = datetime(2026, 9, 24, tzinfo=UTC)
COMPLETION = datetime(2026, 9, 24, 9, tzinfo=timezone(timedelta(hours=8)))
SCOPE = RadarMarketContentScope(date(2026, 1, 2), SESSION)
CONTENT = RadarCurrentMarketContent(INSTRUMENT, SESSION, "sha256:" + "a" * 64, SCOPE)
CURRENT = RadarCurrentMarketContentLookupResult(
    RadarCurrentMarketContentLookupStatus.PRESENT, CONTENT
)
CHECKPOINT = RadarObservationCheckpoint(
    INSTRUMENT, SESSION, CONTENT.normalized_market_content_identity, AS_OF, SCOPE
)
LIGHT = RadarLightweightObservation(
    INSTRUMENT,
    EMA8_EMA20_OBSERVATION_DEFINITION_ID,
    EMA8_EMA20_CALCULATION_REVISION,
    EMA8_EMA20_OBSERVATION_SCHEMA,
    SESSION,
    CONTENT.normalized_market_content_identity,
    SCOPE,
    RadarEmaRelation.ABOVE,
    AS_OF,
)
LIGHT_LOOKUP = RadarLightweightObservationLookupResult(
    RadarLightweightObservationLookupStatus.PRESENT, LIGHT
)
TRIGGER = RadarGateOccurrence(
    "arbitrary-name",
    RadarGateIdentity(
        SESSION_CONTENT_TRIGGER_KEY.gate_id,
        SESSION_CONTENT_TRIGGER_KEY.behavioral_revision,
        SESSION_CONTENT_TRIGGER_KEY.configuration_schema,
    ),
)
OTHER_KEY = RadarGateImplementationKey("other", "1", "other/v1")
OTHER = RadarGateOccurrence(
    "session_content_trigger", RadarGateIdentity("other", "1", "other/v1")
)


def profile(*occurrences):
    return RadarProfile("test", "1", "test/v1", occurrences or (TRIGGER,))


def state_for(checkpoint=CHECKPOINT, light=LIGHT):
    return RadarObservationState(
        checkpoint,
        light,
        evaluate_meaningful_change(None, light),
        profile().fingerprint,
        Outcome.SELECTED,
    )


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    store = RadarCheckpointFileStore(tmp_path)
    lookup = Mock(wraps=store.lookup_state)
    save = Mock(wraps=store.save_state)
    monkeypatch.setattr(store, "lookup_state", lookup)
    monkeypatch.setattr(store, "save_state", save)
    monkeypatch.setattr(
        store, "save", Mock(side_effect=AssertionError("No legacy save"))
    )
    calendar = Mock(spec=ExchangeSessionCalendar)
    calendar.latest_completed_session.return_value = SESSION
    calendar.is_session.return_value = True
    factory = Mock(
        side_effect=lambda occurrence: RadarSessionContentTriggerGate(
            occurrence, calendar
        )
    )
    other = Mock()
    other.identity = OTHER.gate_identity
    other.evaluate.return_value = RadarGateResult(
        OTHER, Disposition.PASS, "BASELINE_REQUIRED"
    )
    resolver = RadarGateResolver(
        [
            RadarGateFactoryBinding(SESSION_CONTENT_TRIGGER_KEY, factory),
            RadarGateFactoryBinding(OTHER_KEY, lambda occurrence: other),
        ]
    )
    clock = Mock(return_value=COMPLETION)
    loader = Mock(return_value=CURRENT)
    loaders = {
        CURRENT_MARKET_CONTENT_LOOKUP: loader,
        EMA8_EMA20_OBSERVATION_LOOKUP: Mock(return_value=LIGHT_LOOKUP),
    }
    service = RadarApplicationService(resolver, store, clock)
    accesses = []
    get_fact = RadarEvaluationContext.get_fact

    def track(context, key):
        accesses.append(key)
        return get_fact(context, key)

    monkeypatch.setattr(RadarEvaluationContext, "get_fact", track)
    return (
        service,
        store,
        lookup,
        save,
        clock,
        loader,
        loaders,
        other,
        factory,
        accesses,
    )


def run(runtime, chosen=None):
    return runtime[0].evaluate(chosen or profile(), INSTRUMENT, AS_OF, runtime[6])


def assert_not_advanced(runtime, result, outcome):
    assert result.pipeline_result.outcome is outcome
    assert result.advancement is RadarCheckpointAdvancement.NOT_ADVANCED
    assert result.saved_checkpoint is None
    assert result.saved_state is None
    assert result.meaningful_change_decision is None
    runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP].assert_not_called()
    runtime[3].assert_not_called()
    runtime[4].assert_not_called()


@pytest.mark.parametrize("downstream", [False, True])
def test_baseline_and_downstream_drop(runtime, tmp_path, downstream):
    runtime[7].evaluate.return_value = RadarGateResult(
        OTHER, Disposition.DROP, "FILTER"
    )
    result = run(runtime, profile(TRIGGER, OTHER) if downstream else profile())
    assert result.pipeline_result.outcome is (
        Outcome.FILTERED if downstream else Outcome.SELECTED
    )
    assert result.pipeline_result.executed_results[0].reason_code == "BASELINE_REQUIRED"
    assert result.advancement is RadarCheckpointAdvancement.SAVED
    expected = replace(CHECKPOINT, observed_at=COMPLETION)
    assert result.saved_checkpoint == expected
    assert result.saved_checkpoint.observed_at == COMPLETION.astimezone(UTC)
    assert result.saved_checkpoint.observed_at != AS_OF
    loaded = RadarCheckpointFileStore(tmp_path).lookup(INSTRUMENT)
    assert loaded.status is RadarObservationLookupStatus.PRESENT
    assert loaded.checkpoint == expected
    runtime[2].assert_called_once_with(INSTRUMENT)
    runtime[3].assert_called_once_with(result.saved_state)
    assert result.meaningful_change_decision.reason == "BASELINE_INITIALIZED"
    assert result.saved_state.committed_decision == result.meaningful_change_decision
    runtime[4].assert_called_once_with()
    runtime[5].assert_called_once_with()
    assert runtime[9].count(CURRENT_MARKET_CONTENT_LOOKUP) == 2


@pytest.mark.parametrize(
    "kind,reason",
    [("session", "NEW_COMPLETED_SESSION"), ("correction", "MARKET_CONTENT_CHANGED")],
)
def test_replaces_prior(runtime, tmp_path, kind, reason):
    prior = replace(CHECKPOINT, normalized_market_content_identity="sha256:" + "b" * 64)
    if kind == "session":
        previous = date(2026, 9, 22)
        prior = replace(
            prior,
            observed_completed_session=previous,
            content_scope=replace(SCOPE, history_end=previous),
        )
    RadarCheckpointFileStore(tmp_path).save(prior)
    result = run(runtime)
    assert result.pipeline_result.executed_results[0].reason_code == reason
    assert result.meaningful_change_decision.reason == "BASELINE_INITIALIZED"
    assert result.meaningful_change_decision.prior is None
    assert not result.meaningful_change_decision.meaningful_change
    runtime[3].assert_called_once_with(result.saved_state)
    assert result.saved_checkpoint == replace(CHECKPOINT, observed_at=COMPLETION)
    assert (
        RadarCheckpointFileStore(tmp_path).lookup(INSTRUMENT).checkpoint
        == result.saved_checkpoint
    )
    runtime[5].assert_called_once_with()


def test_unchanged_does_not_rewrite_or_reread(runtime, tmp_path, monkeypatch):
    RadarCheckpointFileStore(tmp_path).save_state(state_for())
    compare = Mock(
        side_effect=AssertionError("No new comparison for complete UNCHANGED")
    )
    monkeypatch.setattr(subject, "evaluate_meaningful_change", compare)
    path = next(tmp_path.glob("*.json"))
    before = path.read_bytes()
    result = run(runtime)
    assert_not_advanced(runtime, result, Outcome.FILTERED)
    assert result.pipeline_result.executed_results[0].reason_code == "UNCHANGED"
    assert path.read_bytes() == before
    runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP].assert_not_called()
    runtime[2].assert_called_once_with(INSTRUMENT)
    assert result.saved_state is result.meaningful_change_decision is None
    compare.assert_not_called()
    assert runtime[9].count(CURRENT_MARKET_CONTENT_LOOKUP) == 1
    runtime[5].assert_called_once_with()


def test_unavailable_prior(runtime, tmp_path):
    runtime[2].side_effect = RadarCheckpointFileStore(tmp_path / "missing").lookup_state
    assert_not_advanced(runtime, run(runtime), Outcome.ATTENTION)
    runtime[5].assert_not_called()


def test_malformed_prior(runtime, tmp_path):
    RadarCheckpointFileStore(tmp_path).save(CHECKPOINT)
    next(tmp_path.glob("*.json")).write_text("broken", encoding="utf-8")
    result = run(runtime)
    assert_not_advanced(runtime, result, Outcome.FAILED)
    assert result.pipeline_result.failure.occurrence == TRIGGER
    runtime[5].assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_incomplete_downstream(runtime, fails):
    if fails:
        runtime[7].evaluate.side_effect = RuntimeError("gate error")
    else:
        runtime[7].evaluate.return_value = RadarGateResult(
            OTHER, Disposition.ATTENTION, "RETRY"
        )
    result = run(runtime, profile(TRIGGER, OTHER))
    assert_not_advanced(runtime, result, Outcome.FAILED if fails else Outcome.ATTENTION)
    assert result.pipeline_result.executed_results[0].disposition is Disposition.PASS
    assert runtime[9].count(CURRENT_MARKET_CONTENT_LOOKUP) == 1


def test_earlier_drop_keeps_lookup_lazy(runtime):
    runtime[7].evaluate.return_value = RadarGateResult(
        OTHER, Disposition.DROP, "BASELINE_REQUIRED"
    )
    assert_not_advanced(
        runtime, run(runtime, profile(OTHER, TRIGGER)), Outcome.FILTERED
    )
    runtime[2].assert_not_called()
    runtime[5].assert_not_called()
    assert runtime[9] == []


@pytest.mark.parametrize("outcome", list(Outcome))
def test_zero_trigger_never_advances_even_familiar_reason(runtime, outcome):
    if outcome is Outcome.FAILED:
        runtime[7].evaluate.side_effect = RuntimeError("failure")
    else:
        disposition = {
            Outcome.SELECTED: Disposition.PASS,
            Outcome.FILTERED: Disposition.DROP,
            Outcome.ATTENTION: Disposition.ATTENTION,
        }[outcome]
        runtime[7].evaluate.return_value = RadarGateResult(
            OTHER, disposition, "BASELINE_REQUIRED"
        )
    assert_not_advanced(runtime, run(runtime, profile(OTHER)), outcome)
    runtime[2].assert_not_called()
    runtime[5].assert_not_called()
    assert runtime[9] == []


def test_multiple_triggers_rejected_before_any_activity(runtime):
    with pytest.raises(RadarApplicationConfigurationError):
        run(runtime, profile(TRIGGER, replace(TRIGGER, occurrence_id="second")))
    for index in (2, 3, 4, 5, 8):
        runtime[index].assert_not_called()
    runtime[7].evaluate.assert_not_called()


@pytest.mark.parametrize(
    "key",
    [PRIOR_OBSERVATION_LOOKUP, RadarFactKey(PRIOR_OBSERVATION_LOOKUP.fact_id, str)],
)
def test_reserved_binding_rejected(runtime, key):
    runtime[6][key] = Mock()
    with pytest.raises(RadarApplicationConfigurationError):
        run(runtime)
    for index in (2, 3, 4, 5, 8):
        runtime[index].assert_not_called()


def test_mapping_detached_before_factory_runs(runtime):
    original = runtime[8].side_effect

    def factory(occurrence):
        runtime[6].clear()
        return original(occurrence)

    runtime[8].side_effect = factory
    assert run(runtime).advancement is RadarCheckpointAdvancement.SAVED
    runtime[5].assert_called_once_with()
    assert runtime[6] == {}


@pytest.mark.parametrize(
    "error", [OSError("disk"), RadarCheckpointStoreError("unsafe")]
)
def test_save_failure_retains_completed_result(runtime, tmp_path, error):
    runtime[3].side_effect = error
    with pytest.raises(RadarCheckpointAdvancementError) as caught:
        run(runtime)
    assert caught.value.__cause__ is error
    assert caught.value.pipeline_result.outcome is Outcome.SELECTED
    assert caught.value.pipeline_result.failure is None
    assert (
        caught.value.pipeline_result.executed_results[0].reason_code
        == "BASELINE_REQUIRED"
    )
    assert (
        RadarCheckpointFileStore(tmp_path).lookup(INSTRUMENT).status
        is RadarObservationLookupStatus.ABSENT
    )


def test_save_programming_error_retains_prepared_state(runtime):
    runtime[3].side_effect = TypeError("programming error")
    with pytest.raises(RadarCheckpointAdvancementError) as caught:
        run(runtime)
    assert isinstance(caught.value.__cause__, TypeError)
    assert caught.value.prepared_state == runtime[3].call_args.args[0]


@pytest.mark.parametrize("value", [datetime(2026, 9, 24), None, "invalid"])
def test_invalid_completion_clock_fails_before_save(runtime, value):
    runtime[4].return_value = value
    with pytest.raises(RadarObservationPreparationError):
        run(runtime)
    runtime[4].assert_called_once_with()
    runtime[3].assert_not_called()


def test_resolver_failure_stays_pre_execution(runtime):
    unsupported = replace(
        TRIGGER, gate_identity=replace(TRIGGER.gate_identity, behavioral_revision="2")
    )
    with pytest.raises(RadarResolutionError):
        run(runtime, profile(unsupported))
    for index in (2, 3, 4, 5, 8):
        runtime[index].assert_not_called()


def test_result_frozen_and_invariants(runtime):
    result = run(runtime)
    with pytest.raises(FrozenInstanceError):
        result.advancement = RadarCheckpointAdvancement.NOT_ADVANCED
    with pytest.raises(ValueError, match="SAVED requires"):
        RadarApplicationResult(result.pipeline_result, RadarCheckpointAdvancement.SAVED)
    with pytest.raises(ValueError, match="NOT_ADVANCED forbids"):
        RadarApplicationResult(
            result.pipeline_result,
            RadarCheckpointAdvancement.NOT_ADVANCED,
            result.saved_checkpoint,
        )
    with pytest.raises(TypeError):
        RadarApplicationResult(result.pipeline_result, "SAVED", result.saved_checkpoint)


@pytest.mark.parametrize("reason", ["UNRECOGNIZED_PASS", "BASELINE_REQUIRED"])
def test_trigger_pass_requires_known_reason_and_present_content(runtime, reason):
    gate = Mock()
    gate.identity = TRIGGER.gate_identity
    gate.evaluate.return_value = RadarGateResult(TRIGGER, Disposition.PASS, reason)
    runtime[8].side_effect = lambda occurrence: gate
    runtime[5].return_value = RadarCurrentMarketContentLookupResult(
        RadarCurrentMarketContentLookupStatus.UNAVAILABLE
    )
    if reason == "BASELINE_REQUIRED":
        with pytest.raises(RadarObservationPreparationError):
            run(runtime)
    else:
        assert_not_advanced(runtime, run(runtime), Outcome.SELECTED)
        runtime[5].assert_not_called()
    runtime[3].assert_not_called()
    runtime[4].assert_not_called()


def test_missing_content_after_qualifying_pass_is_invariant_failure(runtime):
    gate = Mock()
    gate.identity = TRIGGER.gate_identity
    gate.evaluate.return_value = RadarGateResult(
        TRIGGER, Disposition.PASS, "BASELINE_REQUIRED"
    )
    runtime[8].side_effect = lambda occurrence: gate
    runtime[6].clear()
    with pytest.raises(RadarObservationPreparationError) as caught:
        run(runtime)
    assert caught.value.__cause__ is not None
    runtime[3].assert_not_called()
    runtime[4].assert_not_called()


@pytest.mark.parametrize("mismatch", ["occurrence", "identity"])
def test_wrong_trigger_result_contract_cannot_advance(runtime, mismatch):
    wrong = (
        replace(TRIGGER, occurrence_id="wrong")
        if mismatch == "occurrence"
        else replace(
            TRIGGER,
            gate_identity=replace(TRIGGER.gate_identity, configuration={"wrong": True}),
        )
    )
    gate = Mock()
    gate.identity = TRIGGER.gate_identity
    gate.evaluate.return_value = RadarGateResult(
        wrong, Disposition.PASS, "BASELINE_REQUIRED"
    )
    runtime[8].side_effect = lambda occurrence: gate
    assert_not_advanced(runtime, run(runtime), Outcome.FAILED)
    runtime[5].assert_not_called()


@pytest.mark.parametrize("kind", ["session", "correction"])
@pytest.mark.parametrize("relation", [RadarEmaRelation.ABOVE, RadarEmaRelation.BELOW])
def test_complete_state_comparison(runtime, tmp_path, kind, relation):
    prior_light = replace(
        LIGHT,
        relation=relation,
        normalized_market_content_identity="sha256:" + "b" * 64,
    )
    if kind == "session":
        session = SESSION - timedelta(days=1)
        prior_light = replace(
            prior_light,
            completed_session=session,
            content_scope=replace(
                SCOPE, history_start=date(2026, 1, 1), history_end=session
            ),
        )
    prior_market = replace(
        CHECKPOINT,
        observed_completed_session=prior_light.completed_session,
        content_scope=prior_light.content_scope,
        normalized_market_content_identity=prior_light.normalized_market_content_identity,
    )
    prior = state_for(prior_market, prior_light)
    # Profile provenance is independent of mathematical observation comparison.
    prior = replace(prior, profile_fingerprint="sha256:" + "f" * 64)
    RadarCheckpointFileStore(tmp_path).save_state(prior)
    result = run(runtime)
    decision = result.meaningful_change_decision
    assert decision.prior == prior_light
    assert decision.current is LIGHT
    assert decision.meaningful_change is (relation is RadarEmaRelation.BELOW)
    assert decision.reason == (
        "STATE_UNCHANGED"
        if relation is RadarEmaRelation.ABOVE
        else "NEW_SESSION_STATE_TRANSITION"
        if kind == "session"
        else "CORRECTED_CONTENT_STATE_TRANSITION"
    )
    assert result.saved_state.profile_fingerprint == profile().fingerprint
    runtime[2].assert_called_once_with(INSTRUMENT)
    runtime[3].assert_called_once_with(result.saved_state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("definition_id", "another_observation"),
        ("calculation_revision", "2"),
        ("observation_schema", "radar_observation/v2"),
    ],
)
def test_valid_incompatible_prior_initializes_explicit_baseline(
    runtime, tmp_path, field, value
):
    prior_light = replace(
        LIGHT,
        **{field: value},
        normalized_market_content_identity="sha256:" + "b" * 64,
    )
    prior_market = replace(
        CHECKPOINT,
        normalized_market_content_identity=prior_light.normalized_market_content_identity,
    )
    RadarCheckpointFileStore(tmp_path).save_state(state_for(prior_market, prior_light))
    result = run(runtime)
    assert (
        result.meaningful_change_decision.reason == "INCOMPARABLE_BASELINE_INITIALIZED"
    )
    assert not result.meaningful_change_decision.meaningful_change
    assert result.meaningful_change_decision.prior == prior_light
    runtime[3].assert_called_once_with(result.saved_state)


def test_legacy_unchanged_bootstrap_preserves_actual_pipeline(
    runtime, tmp_path, monkeypatch
):
    RadarCheckpointFileStore(tmp_path).save(CHECKPOINT)
    ema = RadarGateOccurrence(
        "ema",
        RadarGateIdentity(
            EMA8_EMA20_RELATION_KEY.gate_id,
            EMA8_EMA20_RELATION_KEY.behavioral_revision,
            EMA8_EMA20_RELATION_KEY.configuration_schema,
            {"accepted_relations": ["ABOVE"]},
        ),
    )
    calendar = Mock(spec=ExchangeSessionCalendar)
    calendar.latest_completed_session.return_value = SESSION
    calendar.is_session.return_value = True
    runtime[0]._resolver = RadarGateResolver(
        [
            RadarGateFactoryBinding(
                SESSION_CONTENT_TRIGGER_KEY,
                lambda item: RadarSessionContentTriggerGate(item, calendar),
            ),
            RadarGateFactoryBinding(
                EMA8_EMA20_RELATION_KEY, RadarEma8Ema20RelationGate
            ),
        ]
    )
    gate = Mock(side_effect=AssertionError("Skipped EMA must not execute"))
    monkeypatch.setattr(RadarEma8Ema20RelationGate, "evaluate", gate)
    completed = []
    original = RadarPipeline.evaluate

    def evaluate(pipeline, context):
        result = original(pipeline, context)
        completed.append(result)
        return result

    monkeypatch.setattr(RadarPipeline, "evaluate", evaluate)

    def observe():
        assert len(completed) == 1  # Resolve only AFTER actual Pipeline termination.
        return LIGHT_LOOKUP

    runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP].side_effect = observe
    result = run(runtime, profile(TRIGGER, ema))
    assert result.pipeline_result is completed[0]
    assert result.pipeline_result.outcome is Outcome.FILTERED
    assert result.pipeline_result.executed_results == (
        RadarGateResult(TRIGGER, Disposition.DROP, "UNCHANGED"),
    )
    assert result.advancement is RadarCheckpointAdvancement.SAVED
    assert result.saved_checkpoint == replace(CHECKPOINT, observed_at=COMPLETION)
    assert result.meaningful_change_decision.reason == "BASELINE_INITIALIZED"
    assert not result.meaningful_change_decision.meaningful_change
    assert result.meaningful_change_decision.prior is None
    runtime[2].assert_called_once_with(INSTRUMENT)
    runtime[3].assert_called_once_with(result.saved_state)
    runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP].assert_called_once_with()
    gate.assert_not_called()
    stored = RadarCheckpointFileStore(tmp_path).lookup_state(INSTRUMENT)
    assert stored.status is RadarObservationStateLookupStatus.PRESENT_COMPLETE_STATE
    assert stored.state == result.saved_state


@pytest.mark.parametrize("bootstrap", [False, True])
@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "unavailable",
        "malformed",
        "instrument",
        "session",
        "content",
        "scope",
        "as_of",
        "calculation",
    ],
)
def test_preparation_failure_preserves_pipeline_and_prior_bytes(
    runtime, tmp_path, bootstrap, failure
):
    if bootstrap:
        RadarCheckpointFileStore(tmp_path).save(CHECKPOINT)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    loader = runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP]
    if failure == "missing":
        del runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP]
    elif failure == "unavailable":
        loader.return_value = RadarLightweightObservationLookupResult(
            RadarLightweightObservationLookupStatus.UNAVAILABLE
        )
    elif failure == "malformed":
        loader.return_value = object()
    elif failure == "calculation":
        loader.side_effect = ValueError("private preparation detail")
    else:
        changes = {
            "instrument": {"instrument": CanonicalInstrumentId("other")},
            "session": {
                "completed_session": SESSION - timedelta(days=1),
                "content_scope": replace(
                    SCOPE, history_end=SESSION - timedelta(days=1)
                ),
            },
            "content": {"normalized_market_content_identity": "sha256:" + "b" * 64},
            "scope": {"content_scope": replace(SCOPE, history_start=date(2026, 1, 1))},
            "as_of": {"as_of": AS_OF + timedelta(seconds=1)},
        }[failure]
        loader.return_value = replace(
            LIGHT_LOOKUP, observation=replace(LIGHT, **changes)
        )
    with pytest.raises(RadarObservationPreparationError) as caught:
        run(runtime)
    pipeline = caught.value.pipeline_result
    assert pipeline.outcome is (Outcome.FILTERED if bootstrap else Outcome.SELECTED)
    assert pipeline.executed_results == (
        RadarGateResult(
            TRIGGER,
            Disposition.DROP if bootstrap else Disposition.PASS,
            "UNCHANGED" if bootstrap else "BASELINE_REQUIRED",
        ),
    )
    assert pipeline.failure is None
    assert str(caught.value) == "Radar observation preparation failed"
    assert caught.value.__cause__ is not None
    runtime[3].assert_not_called()
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP] = Mock(return_value=LIGHT_LOOKUP)
    assert run(runtime).advancement is RadarCheckpointAdvancement.SAVED


def test_bootstrap_replace_failure_preserves_legacy_and_allows_retry(
    runtime, tmp_path, monkeypatch
):
    RadarCheckpointFileStore(tmp_path).save(CHECKPOINT)
    path = next(tmp_path.glob("*.json"))
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(
            "market_platform.radar.checkpoint_store.os.replace",
            Mock(side_effect=OSError("private replace detail")),
        )
        with pytest.raises(RadarCheckpointAdvancementError) as caught:
            run(runtime)
    assert caught.value.pipeline_result.outcome is Outcome.FILTERED
    assert (
        caught.value.prepared_state.committed_decision.reason == "BASELINE_INITIALIZED"
    )
    assert caught.value.prepared_state == runtime[3].call_args.args[0]
    assert path.read_bytes() == before
    assert list(tmp_path.glob(".radar-*")) == []
    assert run(runtime).advancement is RadarCheckpointAdvancement.SAVED


def test_semantic_lookup_is_retained_separately_from_store_preflight(
    runtime, tmp_path, monkeypatch
):
    prior_light = replace(
        LIGHT,
        relation=RadarEmaRelation.BELOW,
        normalized_market_content_identity="sha256:" + "b" * 64,
    )
    prior_market = replace(
        CHECKPOINT,
        normalized_market_content_identity=prior_light.normalized_market_content_identity,
    )
    RadarCheckpointFileStore(tmp_path).save_state(state_for(prior_market, prior_light))
    physical = Mock(wraps=runtime[1]._lookup_state)
    monkeypatch.setattr(runtime[1], "_lookup_state", physical)
    result = run(runtime)
    runtime[2].assert_called_once_with(INSTRUMENT)
    assert (
        physical.call_count == 2
    )  # Semantic lookup plus unchanged publication preflight.
    assert result.meaningful_change_decision.prior == prior_light
    assert result.meaningful_change_decision.meaningful_change


def test_result_validation_failure_occurs_before_publication(runtime, monkeypatch):
    monkeypatch.setattr(
        RadarApplicationResult,
        "__post_init__",
        Mock(side_effect=ValueError("result construction")),
    )
    with pytest.raises(RadarObservationPreparationError) as caught:
        run(runtime)
    assert caught.value.pipeline_result.outcome is Outcome.SELECTED
    runtime[3].assert_not_called()


@pytest.mark.parametrize(
    "field", ["instrument", "profile", "outcome", "checkpoint", "decision", "as_of"]
)
def test_application_result_rejects_contradictory_correspondence(runtime, field):
    result = run(runtime)
    state = result.saved_state
    changes = {}
    if field == "checkpoint":
        changes["saved_checkpoint"] = replace(
            result.saved_checkpoint, observed_at=AS_OF
        )
    elif field == "decision":
        changes["meaningful_change_decision"] = evaluate_meaningful_change(LIGHT, LIGHT)
    else:
        if field == "profile":
            state = replace(state, profile_fingerprint="sha256:" + "b" * 64)
        elif field == "outcome":
            state = replace(state, pipeline_outcome=Outcome.FILTERED)
        else:
            observation = replace(
                LIGHT,
                **(
                    {"instrument": CanonicalInstrumentId("other")}
                    if field == "instrument"
                    else {"as_of": AS_OF + timedelta(seconds=1)}
                ),
            )
            state = replace(
                state,
                market_observation=replace(
                    state.market_observation, instrument=observation.instrument
                ),
                lightweight_observation=observation,
                committed_decision=evaluate_meaningful_change(None, observation),
            )
        changes = dict(
            saved_state=state,
            saved_checkpoint=state.market_observation,
            meaningful_change_decision=state.committed_decision,
        )
    with pytest.raises(ValueError, match="Saved state must correspond"):
        replace(result, **changes)


@pytest.mark.parametrize(
    "field", ["saved_checkpoint", "saved_state", "meaningful_change_decision"]
)
def test_not_advanced_forbids_each_current_execution_payload(runtime, field):
    saved = run(runtime)
    with pytest.raises(ValueError, match="NOT_ADVANCED forbids"):
        RadarApplicationResult(
            saved.pipeline_result,
            RadarCheckpointAdvancement.NOT_ADVANCED,
            **{field: getattr(saved, field)},
        )


@pytest.mark.parametrize(
    "corruption",
    [
        "malformed",
        "unknown_schema",
        "incomplete",
        "instrument",
        "nested",
        "operational",
    ],
)
def test_publication_preflight_remains_fail_closed_without_new_semantic_lookup(
    runtime, tmp_path, monkeypatch, corruption
):
    RadarCheckpointFileStore(tmp_path).save(CHECKPOINT)
    path = next(tmp_path.glob("*.json"))
    original_lookup = runtime[1]._lookup_state
    reads = Mock(wraps=original_lookup)
    monkeypatch.setattr(runtime[1], "_lookup_state", reads)
    corrupted_bytes = []

    def observe():
        # Alter the target after the semantic read to exercise the store safety check,
        # not to simulate a supported overlapping writer or require CAS.
        if corruption == "operational":
            reads.side_effect = PermissionError("private read failure")
            corrupted_bytes.append(path.read_bytes())
            return LIGHT_LOOKUP
        payload = state_for().to_dict()
        if corruption == "unknown_schema":
            payload["schema_version"] = "unknown/v2"
        elif corruption == "incomplete":
            del payload["lightweight_observation"]
        elif corruption == "instrument":
            other = CanonicalInstrumentId("other")
            other_light = replace(LIGHT, instrument=other)
            payload = state_for(
                replace(CHECKPOINT, instrument=other), other_light
            ).to_dict()
        elif corruption == "nested":
            payload["committed_decision"]["meaningful_change"] = True
        path.write_text(
            "broken" if corruption == "malformed" else json.dumps(payload),
            encoding="utf-8",
        )
        corrupted_bytes.append(path.read_bytes())
        return LIGHT_LOOKUP

    runtime[6][EMA8_EMA20_OBSERVATION_LOOKUP].side_effect = observe
    with pytest.raises(RadarCheckpointAdvancementError) as caught:
        run(runtime)
    assert caught.value.pipeline_result.outcome is Outcome.FILTERED
    assert caught.value.prepared_state.committed_decision.prior is None
    assert (
        caught.value.prepared_state.committed_decision.reason == "BASELINE_INITIALIZED"
    )
    runtime[2].assert_called_once_with(INSTRUMENT)
    runtime[3].assert_called_once_with(caught.value.prepared_state)
    assert reads.call_count == 2
    assert path.read_bytes() == corrupted_bytes[0]


@pytest.mark.parametrize(
    "kind", ["wrong_market", "wrong_light", "future", "same_session_scope"]
)
def test_invalid_retained_prior_correspondence_cannot_reset_baseline(runtime, kind):
    prior = state_for()
    if kind == "wrong_market":
        other = CanonicalInstrumentId("other")
        prior = state_for(
            replace(CHECKPOINT, instrument=other), replace(LIGHT, instrument=other)
        )
    elif kind == "wrong_light":
        # Corrupt injected data must fail even when Trigger's market projection passes.
        prior = state_for(
            replace(
                CHECKPOINT, normalized_market_content_identity="sha256:" + "b" * 64
            ),
            replace(LIGHT, normalized_market_content_identity="sha256:" + "b" * 64),
        )
        object.__setattr__(
            prior,
            "lightweight_observation",
            replace(
                prior.lightweight_observation, instrument=CanonicalInstrumentId("other")
            ),
        )
    elif kind == "future":
        session = SESSION + timedelta(days=1)
        scope = replace(SCOPE, history_end=session)
        prior = state_for(
            replace(
                CHECKPOINT, observed_completed_session=session, content_scope=scope
            ),
            replace(LIGHT, completed_session=session, content_scope=scope),
        )
    else:
        scope = replace(SCOPE, history_start=date(2026, 1, 1))
        prior = state_for(
            replace(CHECKPOINT, content_scope=scope),
            replace(LIGHT, content_scope=scope),
        )
    runtime[2].return_value = RadarObservationStateLookupResult(
        RadarObservationStateLookupStatus.PRESENT_COMPLETE_STATE, state=prior
    )
    if kind == "wrong_light":
        with pytest.raises(RadarObservationPreparationError):
            run(runtime)
    else:
        assert_not_advanced(runtime, run(runtime), Outcome.ATTENTION)
    runtime[3].assert_not_called()


def test_meaningful_change_failure_keeps_completed_pipeline(runtime, monkeypatch):
    compare = Mock(side_effect=ValueError("incoherent comparison"))
    monkeypatch.setattr(subject, "evaluate_meaningful_change", compare)
    with pytest.raises(RadarObservationPreparationError) as caught:
        run(runtime)
    assert caught.value.pipeline_result.outcome is Outcome.SELECTED
    compare.assert_called_once_with(None, LIGHT)
    runtime[3].assert_not_called()


def test_filtered_transition_preserves_selection_and_records_only_observation(
    runtime, tmp_path
):
    previous = replace(
        LIGHT,
        relation=RadarEmaRelation.BELOW,
        normalized_market_content_identity="sha256:" + "b" * 64,
    )
    market = replace(
        CHECKPOINT,
        normalized_market_content_identity=previous.normalized_market_content_identity,
    )
    RadarCheckpointFileStore(tmp_path).save_state(state_for(market, previous))
    runtime[7].evaluate.return_value = RadarGateResult(
        OTHER, Disposition.DROP, "FILTER"
    )
    result = run(runtime, profile(TRIGGER, OTHER))
    assert result.pipeline_result.outcome is Outcome.FILTERED
    assert result.meaningful_change_decision.meaningful_change
    assert result.saved_state.pipeline_outcome is Outcome.FILTERED
    runtime[3].assert_called_once_with(result.saved_state)
