"""FAST PURE / LOCAL APPLICATION tests; no acquisition or authority fixtures."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import Mock, call

import pytest

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.calendar import (
    CalendarCoverageError,
    ExchangeSessionCalendar,
)
from market_platform.radar.context import RadarContextError, RadarEvaluationContext
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
    RadarObservationLookupResult,
    RadarObservationLookupStatus,
)
from market_platform.radar.pipeline import RadarPipeline, RadarPipelineFailureCategory
from market_platform.radar.resolver import (
    RadarGateFactoryBinding,
    RadarGateResolver,
    RadarResolutionCategory,
    RadarResolutionError,
)
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP,
    PRIOR_OBSERVATION_LOOKUP,
    SESSION_CONTENT_TRIGGER_KEY,
    RadarCurrentMarketContent,
    RadarCurrentMarketContentError,
    RadarCurrentMarketContentLookupResult,
    RadarCurrentMarketContentLookupStatus,
    RadarSessionContentTriggerGate,
)

INSTRUMENT = CanonicalInstrumentId("NASDAQ_NVDA")
OTHER = CanonicalInstrumentId("NASDAQ_AAPL")
LATEST = date(2026, 9, 23)
PREVIOUS = date(2026, 9, 22)
AS_OF = datetime(2026, 9, 24, tzinfo=UTC)
SCOPE = RadarMarketContentScope(date(2026, 1, 2), LATEST)
CONTENT = RadarCurrentMarketContent(INSTRUMENT, LATEST, "sha256:" + "a" * 64, SCOPE)
CHECKPOINT = RadarObservationCheckpoint(
    INSTRUMENT, LATEST, CONTENT.normalized_market_content_identity, AS_OF, SCOPE
)
ABSENT = RadarObservationLookupResult(RadarObservationLookupStatus.ABSENT)
PRESENT = RadarObservationLookupResult(RadarObservationLookupStatus.PRESENT, CHECKPOINT)
CURRENT = RadarCurrentMarketContentLookupResult(
    RadarCurrentMarketContentLookupStatus.PRESENT, CONTENT
)
UNAVAILABLE = RadarCurrentMarketContentLookupResult(
    RadarCurrentMarketContentLookupStatus.UNAVAILABLE
)
IDENTITY = RadarGateIdentity(
    SESSION_CONTENT_TRIGGER_KEY.gate_id,
    SESSION_CONTENT_TRIGGER_KEY.behavioral_revision,
    SESSION_CONTENT_TRIGGER_KEY.configuration_schema,
)
OCCURRENCE = RadarGateOccurrence("trigger", IDENTITY)
PROFILE = RadarProfile("test", "1", "test/v1", (OCCURRENCE,))


def prior_at(session: date) -> RadarObservationLookupResult:
    return replace(
        PRESENT,
        checkpoint=replace(
            CHECKPOINT,
            observed_completed_session=session,
            content_scope=replace(SCOPE, history_end=session),
        ),
    )


def current_at(session: date) -> RadarCurrentMarketContentLookupResult:
    return replace(
        CURRENT,
        content=replace(
            CONTENT,
            completed_session=session,
            content_scope=replace(SCOPE, history_end=session),
        ),
    )


def wiring(prior: object = PRESENT, current: object = CURRENT) -> tuple[Any, ...]:
    calendar = Mock(spec=ExchangeSessionCalendar)
    calendar.latest_completed_session.return_value = LATEST
    calendar.is_session.return_value = True
    prior_loader = Mock(return_value=prior)
    current_loader = Mock(return_value=current)
    context = RadarEvaluationContext(
        INSTRUMENT,
        AS_OF,
        {
            PRIOR_OBSERVATION_LOOKUP: prior_loader,
            CURRENT_MARKET_CONTENT_LOOKUP: current_loader,
        },
    )
    gate = RadarSessionContentTriggerGate(OCCURRENCE, calendar)
    return gate, calendar, context, prior_loader, current_loader


def test_construction_and_fact_contracts() -> None:
    gate, calendar, _, prior, current = wiring()
    assert gate.identity is OCCURRENCE.gate_identity
    assert calendar.mock_calls == []
    prior.assert_not_called()
    current.assert_not_called()
    assert PRIOR_OBSERVATION_LOOKUP.fact_id == "radar.prior_observation_lookup/v1"
    assert PRIOR_OBSERVATION_LOOKUP.value_type is RadarObservationLookupResult
    assert (
        CURRENT_MARKET_CONTENT_LOOKUP.fact_id
        == "radar.current_market_content_lookup/v1"
    )
    assert (
        CURRENT_MARKET_CONTENT_LOOKUP.value_type
        is RadarCurrentMarketContentLookupResult
    )


@pytest.mark.parametrize(
    "change",
    [
        {"configuration": {"enabled": True}},
        {"configuration": {"ignored": None}},
        {"gate_id": "other"},
        {"behavioral_revision": "2"},
        {"configuration_schema": "session_content_trigger/v2"},
    ],
)
def test_unsupported_construction(change: dict[str, Any]) -> None:
    calendar = Mock(spec=ExchangeSessionCalendar)
    with pytest.raises(ValueError):
        RadarSessionContentTriggerGate(
            replace(OCCURRENCE, gate_identity=replace(IDENTITY, **change)), calendar
        )
    assert calendar.mock_calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"instrument": "NASDAQ_NVDA"},
        {"completed_session": AS_OF},
        {"completed_session": PREVIOUS},
        {"content_scope": None},
        {"normalized_market_content_identity": None},
        {"normalized_market_content_identity": "sha256:" + "A" * 64},
        {"normalized_market_content_identity": "sha256:" + "a" * 63},
        {"normalized_market_content_identity": "sha256:" + "a" * 64 + "\n"},
    ],
)
def test_malformed_current_content(change: dict[str, Any]) -> None:
    with pytest.raises(RadarCurrentMarketContentError):
        replace(CONTENT, **change)


@pytest.mark.parametrize(
    "status,content",
    [
        ("PRESENT", CONTENT),
        ("ABSENT", None),
        (RadarCurrentMarketContentLookupStatus.PRESENT, None),
        (RadarCurrentMarketContentLookupStatus.PRESENT, CHECKPOINT),
        (RadarCurrentMarketContentLookupStatus.UNAVAILABLE, CONTENT),
        (RadarCurrentMarketContentLookupStatus.UNAVAILABLE, RuntimeError("offline")),
    ],
)
def test_malformed_lookup(status: Any, content: Any) -> None:
    with pytest.raises(RadarCurrentMarketContentError):
        RadarCurrentMarketContentLookupResult(status, content)


def test_values_are_frozen() -> None:
    for value, attribute in ((CONTENT, "instrument"), (CURRENT, "content")):
        with pytest.raises(FrozenInstanceError):
            setattr(value, attribute, None)


@pytest.mark.parametrize(
    "prior,current,disposition,reason",
    [
        (ABSENT, CURRENT, "PASS", "BASELINE_REQUIRED"),
        (ABSENT, UNAVAILABLE, "ATTENTION", "CURRENT_CONTENT_UNAVAILABLE"),
        (prior_at(PREVIOUS), CURRENT, "PASS", "NEW_COMPLETED_SESSION"),
        (
            prior_at(PREVIOUS),
            replace(
                CURRENT,
                content=replace(
                    CONTENT, normalized_market_content_identity="sha256:" + "b" * 64
                ),
            ),
            "PASS",
            "NEW_COMPLETED_SESSION",
        ),
        (PRESENT, CURRENT, "DROP", "UNCHANGED"),
        (
            PRESENT,
            replace(
                CURRENT,
                content=replace(
                    CONTENT, normalized_market_content_identity="sha256:" + "b" * 64
                ),
            ),
            "PASS",
            "MARKET_CONTENT_CHANGED",
        ),
        (
            PRESENT,
            replace(
                CURRENT,
                content=replace(
                    CONTENT, content_scope=replace(SCOPE, history_start=PREVIOUS)
                ),
            ),
            "ATTENTION",
            "INCOMPARABLE_CONTENT_SCOPE",
        ),
        (PRESENT, UNAVAILABLE, "ATTENTION", "CURRENT_CONTENT_UNAVAILABLE"),
        (
            PRESENT,
            replace(CURRENT, content=replace(CONTENT, instrument=OTHER)),
            "ATTENTION",
            "CURRENT_INSTRUMENT_MISMATCH",
        ),
        (ABSENT, current_at(PREVIOUS), "ATTENTION", "CURRENT_SESSION_MISMATCH"),
        (
            prior_at(PREVIOUS),
            current_at(PREVIOUS),
            "ATTENTION",
            "CURRENT_SESSION_MISMATCH",
        ),
        (PRESENT, current_at(PREVIOUS), "ATTENTION", "CURRENT_SESSION_MISMATCH"),
        (
            PRESENT,
            current_at(date(2026, 9, 24)),
            "ATTENTION",
            "CURRENT_SESSION_MISMATCH",
        ),
    ],
)
def test_decisions(
    prior: RadarObservationLookupResult,
    current: RadarCurrentMarketContentLookupResult,
    disposition: str,
    reason: str,
) -> None:
    gate, calendar, context, prior_loader, current_loader = wiring(prior, current)
    before = (repr(prior), repr(current))
    result = gate.evaluate(context)
    assert result.disposition is RadarGateDisposition(disposition)
    assert result.reason_code == reason
    assert result.occurrence is OCCURRENCE
    assert result.detail is None
    assert (repr(prior), repr(current)) == before
    calendar.latest_completed_session.assert_called_once_with(AS_OF)
    assert gate.evaluate(context) == result
    prior_loader.assert_called_once_with()
    current_loader.assert_called_once_with()


@pytest.mark.parametrize(
    "prior,is_session,reason",
    [
        (
            RadarObservationLookupResult(RadarObservationLookupStatus.UNAVAILABLE),
            True,
            "PRIOR_STATE_UNAVAILABLE",
        ),
        (
            replace(PRESENT, checkpoint=replace(CHECKPOINT, instrument=OTHER)),
            True,
            "PRIOR_INSTRUMENT_MISMATCH",
        ),
        (prior_at(date(2026, 9, 20)), False, "PRIOR_NOT_SESSION"),
        (prior_at(date(2026, 9, 24)), True, "PRIOR_SESSION_AHEAD"),
    ],
)
def test_prior_short_circuits(
    prior: RadarObservationLookupResult, is_session: bool, reason: str
) -> None:
    gate, calendar, context, prior_loader, current_loader = wiring(prior)
    calendar.is_session.return_value = is_session
    result = gate.evaluate(context)
    assert result.disposition is RadarGateDisposition.ATTENTION
    assert result.reason_code == reason
    assert result.occurrence is OCCURRENCE
    current_loader.assert_not_called()
    prior_loader.assert_called_once_with()
    if reason == "PRIOR_STATE_UNAVAILABLE":
        assert calendar.mock_calls == []
    elif reason != "PRIOR_INSTRUMENT_MISMATCH":
        assert calendar.mock_calls == [
            call.latest_completed_session(AS_OF),
            call.is_session(prior.checkpoint.observed_completed_session),
        ]


@pytest.mark.parametrize("method", ["latest_completed_session", "is_session"])
@pytest.mark.parametrize("error_type", [CalendarCoverageError, RuntimeError])
def test_calendar_failures_escape(method: str, error_type: type[Exception]) -> None:
    gate, calendar, context, _, current = wiring()
    error = error_type("calendar failure")
    getattr(calendar, method).side_effect = error
    with pytest.raises(error_type) as caught:
        gate.evaluate(context)
    assert caught.value is error
    result = RadarPipeline(PROFILE, {"trigger": gate}).evaluate(context)
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.failure.category is RadarPipelineFailureCategory.GATE_EXCEPTION
    assert result.failure.occurrence is OCCURRENCE
    assert result.executed_results == ()
    current.assert_not_called()


@pytest.mark.parametrize(
    "key", [PRIOR_OBSERVATION_LOOKUP, CURRENT_MARKET_CONTENT_LOOKUP]
)
@pytest.mark.parametrize("mode", ["exception", "missing", "wrong_type", "recursive"])
def test_fact_failure_boundary(key: Any, mode: str) -> None:
    gate, _, _, prior_loader, current_loader = wiring()
    loaders = {
        PRIOR_OBSERVATION_LOOKUP: prior_loader,
        CURRENT_MARKET_CONTENT_LOOKUP: current_loader,
    }
    loader = loaders[key]
    error = RuntimeError("unexpected loader failure")
    if mode == "missing":
        del loaders[key]
    elif mode == "exception":
        loader.side_effect = error
    elif mode == "wrong_type":
        loader.return_value = object()
    else:
        loader.side_effect = lambda: context.get_fact(key)
    context = RadarEvaluationContext(INSTRUMENT, AS_OF, loaders)
    expected = RuntimeError if mode == "exception" else RadarContextError
    with pytest.raises(expected):
        gate.evaluate(context)
    result = RadarPipeline(PROFILE, {"trigger": gate}).evaluate(context)
    assert result.outcome is RadarPipelineOutcome.FAILED
    assert result.failure.category is RadarPipelineFailureCategory.GATE_EXCEPTION
    assert result.failure.occurrence is OCCURRENCE
    assert result.executed_results == ()
    assert loader.call_count == (0 if mode == "missing" else 1)
    if key is PRIOR_OBSERVATION_LOOKUP:
        current_loader.assert_not_called()


def test_resolver_to_pipeline() -> None:
    _, calendar, context, prior, current = wiring(ABSENT)
    factory = Mock(
        side_effect=lambda occurrence: RadarSessionContentTriggerGate(
            occurrence, calendar
        )
    )
    resolver = RadarGateResolver(
        [RadarGateFactoryBinding(SESSION_CONTENT_TRIGGER_KEY, factory)]
    )
    resolved = resolver.resolve_profile(PROFILE)
    assert resolved["trigger"].identity is IDENTITY
    assert factory.call_args.args[0] is OCCURRENCE
    factory.assert_called_once_with(OCCURRENCE)
    assert calendar.mock_calls == []
    prior.assert_not_called()
    current.assert_not_called()
    result = RadarPipeline(PROFILE, resolved).evaluate(context)
    assert result.outcome is RadarPipelineOutcome.SELECTED
    assert result.executed_results[0].occurrence is OCCURRENCE
    assert result.executed_results[0].reason_code == "BASELINE_REQUIRED"


def test_resolver_rejects_nonempty_configuration() -> None:
    calendar = Mock(spec=ExchangeSessionCalendar)
    resolver = RadarGateResolver(
        [
            RadarGateFactoryBinding(
                SESSION_CONTENT_TRIGGER_KEY,
                lambda occurrence: RadarSessionContentTriggerGate(occurrence, calendar),
            )
        ]
    )
    profile = replace(
        PROFILE,
        gates=(
            replace(
                OCCURRENCE,
                gate_identity=replace(IDENTITY, configuration={"unused": False}),
            ),
        ),
    )
    with pytest.raises(RadarResolutionError) as caught:
        resolver.resolve_profile(profile)
    assert caught.value.category is RadarResolutionCategory.FACTORY_FAILURE
    assert calendar.mock_calls == []
