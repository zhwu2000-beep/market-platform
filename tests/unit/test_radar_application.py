"""FAST PURE / LOCAL APPLICATION orchestration tests."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.application import (
    RadarApplicationConfigurationError,
    RadarApplicationInvariantError,
    RadarApplicationResult,
    RadarApplicationService,
    RadarCheckpointAdvancement,
    RadarCheckpointAdvancementError,
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
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
    RadarObservationLookupStatus,
    RadarObservationStateError,
)
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


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    store = RadarCheckpointFileStore(tmp_path)
    lookup = Mock(wraps=store.lookup)
    save = Mock(wraps=store.save)
    monkeypatch.setattr(store, "lookup", lookup)
    monkeypatch.setattr(store, "save", save)
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
    loaders = {CURRENT_MARKET_CONTENT_LOOKUP: loader}
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
    runtime[3].assert_called_once_with(expected)
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
    assert result.saved_checkpoint == replace(CHECKPOINT, observed_at=COMPLETION)
    assert (
        RadarCheckpointFileStore(tmp_path).lookup(INSTRUMENT).checkpoint
        == result.saved_checkpoint
    )
    runtime[5].assert_called_once_with()


def test_unchanged_does_not_rewrite_or_reread(runtime, tmp_path):
    RadarCheckpointFileStore(tmp_path).save(CHECKPOINT)
    path = next(tmp_path.glob("*.json"))
    before = path.read_bytes()
    result = run(runtime)
    assert_not_advanced(runtime, result, Outcome.FILTERED)
    assert result.pipeline_result.executed_results[0].reason_code == "UNCHANGED"
    assert path.read_bytes() == before
    assert runtime[9].count(CURRENT_MARKET_CONTENT_LOOKUP) == 1
    runtime[5].assert_called_once_with()


def test_unavailable_prior(runtime, tmp_path):
    runtime[2].side_effect = RadarCheckpointFileStore(tmp_path / "missing").lookup
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


def test_save_programming_error_is_not_wrapped(runtime):
    runtime[3].side_effect = TypeError("programming error")
    with pytest.raises(TypeError, match="programming error"):
        run(runtime)


@pytest.mark.parametrize("value", [datetime(2026, 9, 24), None, "invalid"])
def test_invalid_completion_clock_fails_before_save(runtime, value):
    runtime[4].return_value = value
    with pytest.raises(RadarObservationStateError):
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
        with pytest.raises(RadarApplicationInvariantError):
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
    with pytest.raises(RadarApplicationInvariantError) as caught:
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
