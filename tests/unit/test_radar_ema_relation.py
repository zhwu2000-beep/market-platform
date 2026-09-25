"""FAST PURE / LOCAL APPLICATION tests; no network or governed fixtures."""

from dataclasses import replace
from datetime import UTC, datetime, time
from itertools import combinations
from unittest.mock import Mock, call
from zoneinfo import ZoneInfo

import pytest

from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.indicators.trend import calculate_ema
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMappingSourceIdentity,
)
from market_platform.instruments.mapping import InstrumentMapping
from market_platform.radar import ema_relation
from market_platform.radar.application import (
    RadarApplicationService,
    RadarCheckpointAdvancement,
)
from market_platform.radar.calendar import (
    ExchangeCalendarsSessionCalendar,
    ExchangeSessionCalendar,
)
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.context import RadarContextError, RadarEvaluationContext
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.current_content import (
    COMPLETED_DAILY_HISTORY_LOOKUP,
    RadarCompletedDailyHistoryLookupResult,
    RadarCompletedDailyHistoryLookupStatus,
    bind_completed_daily_current_content,
)
from market_platform.radar.ema_relation import (
    EMA8_EMA20_RELATION_KEY,
    RadarEma8Ema20RelationGate,
    RadarEmaRelation,
)
from market_platform.radar.observation import (
    RadarObservationCheckpoint,
    RadarObservationLookupResult,
    RadarObservationLookupStatus,
)
from market_platform.radar.pipeline import RadarPipeline, RadarPipelineFailureCategory
from market_platform.radar.resolver import (
    RadarGateFactoryBinding,
    RadarGateImplementationKey,
    RadarGateResolver,
    RadarResolutionCategory,
    RadarResolutionError,
)
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP,
    PRIOR_OBSERVATION_LOOKUP,
    SESSION_CONTENT_TRIGGER_KEY,
    RadarCurrentMarketContentLookupResult,
    RadarCurrentMarketContentLookupStatus,
    RadarSessionContentTriggerGate,
)
from market_platform.trading import TradingInstrumentIdentity

AS_OF = datetime(2026, 9, 24, tzinfo=UTC)
INSTRUMENT = CanonicalInstrumentId("registry_nvda")
EXTERNAL = ExternalInstrumentIdentity("polygon", "NVDA")
MAPPING = InstrumentMapping(
    EXTERNAL,
    CanonicalInstrument(
        INSTRUMENT,
        TradingInstrumentIdentity("NVDA", "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    ),
    InstrumentMappingSourceIdentity("registry", "1"),
    datetime(2000, 1, 1, tzinfo=UTC),
)
UNAVAILABLE = RadarCompletedDailyHistoryLookupResult(
    RadarCompletedDailyHistoryLookupStatus.UNAVAILABLE
)


def occurrence(configuration, key=EMA8_EMA20_RELATION_KEY, name="ema"):
    return RadarGateOccurrence(
        name,
        RadarGateIdentity(
            key.gate_id,
            key.behavioral_revision,
            key.configuration_schema,
            configuration,
        ),
    )


def profile(*occurrences):
    return RadarProfile("test", "1", "test/v1", occurrences)


def resolver(calendar=None):
    bindings = [
        RadarGateFactoryBinding(EMA8_EMA20_RELATION_KEY, RadarEma8Ema20RelationGate)
    ]
    if calendar is not None:
        bindings.append(
            RadarGateFactoryBinding(
                SESSION_CONTENT_TRIGGER_KEY,
                lambda item: RadarSessionContentTriggerGate(item, calendar),
            )
        )
    return RadarGateResolver(bindings)


def context(loaders):
    return RadarEvaluationContext(INSTRUMENT, AS_OF, loaders)


def pipeline(item):
    chosen = profile(item)
    return RadarPipeline(chosen, resolver().resolve_profile(chosen))


@pytest.fixture(scope="module")
def sessions():
    calendar = ExchangeCalendarsSessionCalendar()
    latest = calendar.latest_completed_session(AS_OF)
    start = latest
    for _ in range(249):
        start = calendar.previous_session(start)
    return calendar.sessions_in_range(start, latest)


@pytest.fixture
def runtime(sessions):
    calendar = Mock(spec=ExchangeSessionCalendar)
    calendar.latest_completed_session.return_value = sessions[-1]
    calendar.previous_session.side_effect = lambda label: sessions[
        sessions.index(label) - 1
    ]
    calendar.sessions_in_range.return_value = sessions
    calendar.is_session.side_effect = lambda label: label in sessions
    rows = tuple(
        PolygonCompletedDailyAggregate(
            int(
                datetime.combine(
                    label, time(), ZoneInfo("America/New_York")
                ).timestamp()
                * 1000
            ),
            100,
            400,
            1,
            100 + index,
            1000,
        )
        for index, label in enumerate(sessions)
    )
    acquisition = PolygonCompletedDailyAcquisition(
        requested_ticker="NVDA",
        requested_from=sessions[0].isoformat(),
        requested_to=sessions[-1].isoformat(),
        response_ticker_is_present=True,
        response_ticker="NVDA",
        response_adjusted_is_present=True,
        response_adjusted=True,
        request_id_is_present=False,
        request_id=None,
        query_count_is_present=False,
        query_count=None,
        results_count_is_present=True,
        results_count=250,
        count_is_present=True,
        count=250,
        next_url_is_present=False,
        next_page_reference=None,
        results_is_present=True,
        rows=rows,
        response_received_at=AS_OF,
    )
    return calendar, Mock(return_value=acquisition)


def bind(runtime):
    return bind_completed_daily_current_content(
        instrument=INSTRUMENT,
        as_of=AS_OF,
        calendar=runtime[0],
        external_identity=EXTERNAL,
        mappings=(MAPPING,),
        acquire_completed_daily=runtime[1],
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("gate_id", "other"),
        ("behavioral_revision", "2"),
        ("configuration_schema", "ema8_ema20_relation/v2"),
    ],
)
def test_wrong_implementation_rejected(field, value):
    key = replace(EMA8_EMA20_RELATION_KEY, **{field: value})
    with pytest.raises(ValueError, match="Unsupported"):
        RadarEma8Ema20RelationGate(occurrence({"accepted_relations": ["ABOVE"]}, key))


def test_exact_implementation_key():
    assert (
        RadarGateImplementationKey("ema8_ema20_relation", "1", "ema8_ema20_relation/v1")
        == EMA8_EMA20_RELATION_KEY
    )
    assert tuple(relation.value for relation in RadarEmaRelation) == (
        "ABOVE",
        "EQUAL",
        "BELOW",
    )


@pytest.mark.parametrize(
    "accepted",
    [
        values
        for size in (1, 2, 3)
        for values in combinations(("ABOVE", "EQUAL", "BELOW"), size)
    ],
)
def test_canonical_configuration_and_occurrence(accepted):
    item = occurrence({"accepted_relations": list(accepted)})
    gate = RadarEma8Ema20RelationGate(item)
    assert gate.identity is item.gate_identity
    result = gate.evaluate(
        context({COMPLETED_DAILY_HISTORY_LOOKUP: lambda: UNAVAILABLE})
    )
    assert result.occurrence is item
    assert item.gate_identity.configuration["accepted_relations"] == accepted


@pytest.mark.parametrize(
    "configuration",
    [
        {},
        {"accepted_relations": []},
        {"accepted_relations": ["ABOVE", "ABOVE"]},
        {"accepted_relations": ["UNKNOWN"]},
        {"accepted_relations": ["above"]},
        {"accepted_relations": "ABOVE"},
        {"accepted_relations": None},
        {"accepted_relations": 1},
        {"accepted_relations": True},
        {"accepted_relations": [1]},
        {"accepted_relations": [None]},
        {"accepted_relations": {"ABOVE": True}},
        {"accepted_relations": ["ABOVE"], "epsilon": 0},
        {"accepted_relations": ["BELOW", "ABOVE"]},
        {"accepted_relations": ["EQUAL", "ABOVE"]},
        {"accepted_relations": ["BELOW", "EQUAL"]},
    ],
)
def test_invalid_configuration_fails_at_construction_and_resolution(configuration):
    item = occurrence(configuration)
    with pytest.raises((TypeError, ValueError)):
        RadarEma8Ema20RelationGate(item)
    with pytest.raises(RadarResolutionError) as caught:
        resolver().resolve_profile(profile(item))
    assert caught.value.category is RadarResolutionCategory.FACTORY_FAILURE


@pytest.mark.parametrize("relation", ["ABOVE", "EQUAL", "BELOW"])
@pytest.mark.parametrize("accept", [True, False])
def test_relations_reuse_full_history_without_mutation(
    runtime, relation, accept, monkeypatch
):
    rows = runtime[1].return_value.rows
    closes = {
        "ABOVE": tuple(100 + i for i in range(250)),
        "EQUAL": (128,) * 250,
        "BELOW": tuple(350 - i for i in range(250)),
    }[relation]
    runtime[1].return_value = replace(
        runtime[1].return_value,
        rows=tuple(
            replace(row, close=close) for row, close in zip(rows, closes, strict=True)
        ),
    )
    retained = context(bind(runtime)).get_fact(COMPLETED_DAILY_HISTORY_LOOKUP)
    series = retained.history.series
    before = tuple(series.full_prefix().iter_rows())
    fingerprint = series.content_fingerprint
    loader = Mock(return_value=retained)
    ctx = context({COMPLETED_DAILY_HISTORY_LOOKUP: loader})
    get_fact = Mock(wraps=ctx.get_fact)
    # Patch the class surface because context has slots.
    monkeypatch.setattr(
        RadarEvaluationContext, "get_fact", lambda self, key: get_fact(key)
    )
    materialize = Mock(side_effect=AssertionError("No DataFrame materialization"))
    monkeypatch.setattr(HistoricalPriceSeries, "to_dataframe", materialize)
    calculator = Mock(wraps=calculate_ema)
    monkeypatch.setattr(ema_relation, "calculate_ema", calculator)
    accepted = [relation] if accept else ["EQUAL" if relation != "EQUAL" else "BELOW"]
    item = occurrence({"accepted_relations": accepted})
    result = RadarEma8Ema20RelationGate(item).evaluate(ctx)
    assert result.disposition is (
        RadarGateDisposition.PASS if accept else RadarGateDisposition.DROP
    )
    assert result.reason_code == f"EMA8_{relation}_EMA20"
    assert result.detail is None
    assert result.occurrence is item
    get_fact.assert_called_once_with(COMPLETED_DAILY_HISTORY_LOOKUP)
    loader.assert_called_once_with()
    assert calculator.call_args_list == [
        call(closes, period=8),
        call(closes, period=20),
    ]
    assert calculator.call_args_list[0].args[0] is calculator.call_args_list[1].args[0]
    assert tuple(series.full_prefix().iter_rows()) == before
    assert series.content_fingerprint == fingerprint
    materialize.assert_not_called()
    assert runtime[1].call_count == 1


def test_unavailable_does_not_calculate(monkeypatch):
    calculator = Mock(side_effect=AssertionError("Must not calculate"))
    monkeypatch.setattr(ema_relation, "calculate_ema", calculator)
    item = occurrence({"accepted_relations": ["BELOW"]})
    result = RadarEma8Ema20RelationGate(item).evaluate(
        context({COMPLETED_DAILY_HISTORY_LOOKUP: lambda: UNAVAILABLE})
    )
    assert result.disposition is RadarGateDisposition.ATTENTION
    assert result.reason_code == "HISTORY_UNAVAILABLE"
    assert result.detail is None
    calculator.assert_not_called()


@pytest.mark.parametrize(
    "kind", ["missing", "wrong_type", "loader_exception", "malformed"]
)
def test_fact_errors_escape_and_fail_pipeline(kind):
    loader = Mock(return_value=object())
    error = RadarContextError
    if kind == "loader_exception":
        loader.side_effect = RuntimeError("loader failed")
        error = RuntimeError
    if kind == "malformed":
        loader.side_effect = lambda: RadarCompletedDailyHistoryLookupResult(
            RadarCompletedDailyHistoryLookupStatus.PRESENT
        )
        error = ValueError
    ctx = context({} if kind == "missing" else {COMPLETED_DAILY_HISTORY_LOOKUP: loader})
    item = occurrence({"accepted_relations": ["ABOVE"]})
    with pytest.raises(error):
        RadarEma8Ema20RelationGate(item).evaluate(ctx)
    result = pipeline(item).evaluate(ctx)
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.executed_results == ()
    assert result.failure.category is RadarPipelineFailureCategory.GATE_EXCEPTION


def test_history_instrument_mismatch_fails_before_calculation(runtime, monkeypatch):
    retained = context(bind(runtime)).get_fact(COMPLETED_DAILY_HISTORY_LOOKUP)
    assert retained.status is RadarCompletedDailyHistoryLookupStatus.PRESENT
    assert retained.history.instrument == INSTRUMENT
    ctx = RadarEvaluationContext(
        CanonicalInstrumentId("registry_other"),
        AS_OF,
        {COMPLETED_DAILY_HISTORY_LOOKUP: lambda: retained},
    )
    calculator = Mock(
        side_effect=AssertionError("Must not calculate mismatched history")
    )
    monkeypatch.setattr(ema_relation, "calculate_ema", calculator)
    item = occurrence({"accepted_relations": ["ABOVE"]})
    with pytest.raises(
        ValueError, match="^Completed daily history instrument must match context$"
    ):
        RadarEma8Ema20RelationGate(item).evaluate(ctx)
    calculator.assert_not_called()

    result = pipeline(item).evaluate(ctx)
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.failure.category is RadarPipelineFailureCategory.GATE_EXCEPTION
    assert result.executed_results == ()
    calculator.assert_not_called()


@pytest.mark.parametrize("period", [8, 20])
@pytest.mark.parametrize("bad", [(), (None,) * 250, RuntimeError("calculation failed")])
def test_calculation_invariant_failure_escapes(runtime, monkeypatch, period, bad):
    retained = context(bind(runtime)).get_fact(COMPLETED_DAILY_HISTORY_LOOKUP)

    def calculate(values, *, period):
        if period == failing_period:
            if isinstance(bad, Exception):
                raise bad
            return bad
        return calculate_ema(values, period=period)

    failing_period = period
    monkeypatch.setattr(ema_relation, "calculate_ema", calculate)
    ctx = context({COMPLETED_DAILY_HISTORY_LOOKUP: lambda: retained})
    item = occurrence({"accepted_relations": ["ABOVE"]})
    with pytest.raises((ValueError, RuntimeError)):
        RadarEma8Ema20RelationGate(item).evaluate(ctx)
    result = pipeline(item).evaluate(ctx)
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.failure.category is RadarPipelineFailureCategory.GATE_EXCEPTION
    assert result.executed_results == ()


def test_resolution_is_lazy(runtime, monkeypatch):
    calculator = Mock(side_effect=AssertionError("No construction calculation"))
    monkeypatch.setattr(ema_relation, "calculate_ema", calculator)
    loaders = bind(runtime)
    history = Mock(wraps=loaders[COMPLETED_DAILY_HISTORY_LOOKUP])
    loaders[COMPLETED_DAILY_HISTORY_LOOKUP] = history
    ctx = context(loaders)
    item = occurrence({"accepted_relations": ["BELOW"]})
    resolved = resolver().resolve_profile(profile(item))
    assert isinstance(resolved[item.occurrence_id], RadarEma8Ema20RelationGate)
    assert resolved[item.occurrence_id].identity is item.gate_identity
    RadarPipeline(profile(item), resolved)
    history.assert_not_called()
    calculator.assert_not_called()
    runtime[1].assert_not_called()
    assert runtime[0].mock_calls == []
    assert ctx.instrument is INSTRUMENT


@pytest.mark.parametrize("mode", ["pass", "unchanged", "attention"])
def test_trigger_order_and_one_acquisition(runtime, monkeypatch, mode):
    loaders = bind(runtime)
    current_loader = loaders[CURRENT_MARKET_CONTENT_LOOKUP]
    retained_loader = loaders[COMPLETED_DAILY_HISTORY_LOOKUP]
    retained = []

    def load_current():
        current = current_loader()
        retained.append(retained_loader().history.series)
        return current

    loaders[CURRENT_MARKET_CONTENT_LOOKUP] = load_current
    prior = RadarObservationLookupResult(RadarObservationLookupStatus.ABSENT)
    if mode == "unchanged":
        # Prepare the prior execution independently of the measured acquisition.
        seed_runtime = (runtime[0], Mock(return_value=runtime[1].return_value))
        content = bind(seed_runtime)[CURRENT_MARKET_CONTENT_LOOKUP]().content
        prior = RadarObservationLookupResult(
            RadarObservationLookupStatus.PRESENT,
            RadarObservationCheckpoint(
                INSTRUMENT,
                content.completed_session,
                content.normalized_market_content_identity,
                AS_OF,
                content.content_scope,
            ),
        )
    if mode == "attention":
        loaders[CURRENT_MARKET_CONTENT_LOOKUP] = lambda: (
            RadarCurrentMarketContentLookupResult(
                RadarCurrentMarketContentLookupStatus.UNAVAILABLE
            )
        )
    loaders[PRIOR_OBSERVATION_LOOKUP] = lambda: prior
    history_loader = Mock(wraps=loaders[COMPLETED_DAILY_HISTORY_LOOKUP])
    loaders[COMPLETED_DAILY_HISTORY_LOOKUP] = history_loader
    calculator = Mock(wraps=calculate_ema)
    monkeypatch.setattr(ema_relation, "calculate_ema", calculator)
    evaluate = Mock(wraps=RadarEma8Ema20RelationGate.evaluate)
    monkeypatch.setattr(
        RadarEma8Ema20RelationGate, "evaluate", lambda self, ctx: evaluate(self, ctx)
    )
    trigger = occurrence({}, SESSION_CONTENT_TRIGGER_KEY, "trigger")
    item = occurrence({"accepted_relations": ["ABOVE"]})
    chosen = profile(trigger, item)
    ctx = context(loaders)
    result = RadarPipeline(
        chosen, resolver(runtime[0]).resolve_profile(chosen)
    ).evaluate(ctx)
    if mode == "pass":
        assert result.outcome is RadarPipelineOutcome.SELECTED
        assert len(result.executed_results) == 2
        assert result.executed_results[1].occurrence is item
        assert calculator.call_count == 2
        evaluate.assert_called_once()
        history_loader.assert_called_once_with()
        assert (
            ctx.get_fact(COMPLETED_DAILY_HISTORY_LOOKUP).history.series is retained[0]
        )
    else:
        assert len(result.executed_results) == 1
        assert result.executed_results[0].reason_code == (
            "UNCHANGED" if mode == "unchanged" else "CURRENT_CONTENT_UNAVAILABLE"
        )
        calculator.assert_not_called()
        evaluate.assert_not_called()
        history_loader.assert_not_called()
    assert runtime[1].call_count == (0 if mode == "attention" else 1)


@pytest.mark.parametrize("mode", ["drop", "attention", "failure"])
def test_application_checkpoint_after_technical_gate(
    runtime, tmp_path, monkeypatch, mode
):
    loaders = bind(runtime)
    if mode == "attention":
        loaders[COMPLETED_DAILY_HISTORY_LOOKUP] = lambda: UNAVAILABLE
    if mode == "failure":
        monkeypatch.setattr(
            ema_relation, "calculate_ema", Mock(side_effect=RuntimeError("EMA failed"))
        )
    store = RadarCheckpointFileStore(tmp_path)
    save = Mock(wraps=store.save)
    monkeypatch.setattr(store, "save", save)
    trigger = occurrence({}, SESSION_CONTENT_TRIGGER_KEY, "trigger")
    item = occurrence({"accepted_relations": ["BELOW"]})
    service = RadarApplicationService(resolver(runtime[0]), store, lambda: AS_OF)
    result = service.evaluate(profile(trigger, item), INSTRUMENT, AS_OF, loaders)
    assert (
        result.pipeline_result.executed_results[0].disposition
        is RadarGateDisposition.PASS
    )
    assert runtime[1].call_count == 1
    assert (
        result.pipeline_result.outcome
        is {
            "drop": RadarPipelineOutcome.FILTERED,
            "attention": RadarPipelineOutcome.ATTENTION,
            "failure": RadarPipelineOutcome.FAILED,
        }[mode]
    )
    if mode == "drop":
        assert result.advancement is RadarCheckpointAdvancement.SAVED
        save.assert_called_once_with(result.saved_checkpoint)
        assert store.lookup(INSTRUMENT).checkpoint == result.saved_checkpoint
        assert (
            result.pipeline_result.executed_results[1].reason_code == "EMA8_ABOVE_EMA20"
        )
    else:
        assert result.advancement is RadarCheckpointAdvancement.NOT_ADVANCED
        assert result.saved_checkpoint is None
        save.assert_not_called()
        assert store.lookup(INSTRUMENT).status is RadarObservationLookupStatus.ABSENT
