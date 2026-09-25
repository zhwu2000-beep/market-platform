"""FAST PURE / LOCAL APPLICATION tests; no provider or governed lifecycle."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from market_platform.data.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.instruments.errors import (
    InstrumentMappingAmbiguousError,
    InstrumentMappingConflictError,
    InstrumentMappingDuplicateError,
)
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMappingSourceIdentity,
)
from market_platform.instruments.mapping import InstrumentMapping
from market_platform.radar.application import (
    RadarApplicationService,
    RadarCheckpointAdvancement,
)
from market_platform.radar.calendar import (
    CalendarCoverageError,
    ExchangeCalendarsSessionCalendar,
    ExchangeSessionCalendar,
)
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.context import RadarEvaluationContext
from market_platform.radar.core import (
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarProfile,
)
from market_platform.radar.current_content import (
    COMPLETED_DAILY_HISTORY_LOOKUP as HISTORY,
)
from market_platform.radar.current_content import (
    RadarCompletedDailyHistoryLookupResult,
    bind_completed_daily_current_content,
)
from market_platform.radar.current_content import (
    RadarCompletedDailyHistoryLookupStatus as Status,
)
from market_platform.radar.observation import RadarMarketContentScope
from market_platform.radar.resolver import RadarGateFactoryBinding, RadarGateResolver
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP as CURRENT,
)
from market_platform.radar.trigger import (
    SESSION_CONTENT_TRIGGER_KEY,
    RadarSessionContentTriggerGate,
)
from market_platform.trading import TradingInstrumentIdentity

AS_OF = datetime(2026, 9, 24, tzinfo=UTC)
INSTRUMENT = CanonicalInstrumentId("registry_nvda")
EXTERNAL = ExternalInstrumentIdentity("polygon", "NVDA.ALIAS")
CANONICAL = CanonicalInstrument(
    INSTRUMENT,
    TradingInstrumentIdentity("NVDA", "NASDAQ"),
    InstrumentAssetClass.EQUITY,
    "USD",
)
MAPPING = InstrumentMapping(
    EXTERNAL,
    CANONICAL,
    InstrumentMappingSourceIdentity("registry", "1"),
    datetime(2000, 1, 1, tzinfo=UTC),
)


@pytest.fixture(scope="module")
def sessions():
    calendar = ExchangeCalendarsSessionCalendar()
    latest = calendar.latest_completed_session(AS_OF)
    start = latest
    for _ in range(249):
        start = calendar.previous_session(start)
    return calendar.sessions_in_range(start, latest)


def aggregate(label):
    timestamp = int(
        datetime.combine(label, time(), ZoneInfo("America/New_York")).timestamp() * 1000
    )
    return PolygonCompletedDailyAggregate(
        timestamp, Decimal("100.25"), 110, 90, 105, 1234
    )


@pytest.fixture
def runtime(sessions):
    calendar = Mock(spec=ExchangeSessionCalendar)
    calendar.latest_completed_session.return_value = sessions[-1]
    calendar.previous_session.side_effect = lambda label: sessions[
        sessions.index(label) - 1
    ]
    calendar.sessions_in_range.return_value = sessions
    calendar.is_session.side_effect = lambda label: label in sessions
    response = PolygonCompletedDailyAcquisition(
        requested_ticker=EXTERNAL.external_symbol,
        requested_from=sessions[0].isoformat(),
        requested_to=sessions[-1].isoformat(),
        response_ticker_is_present=True,
        response_ticker=EXTERNAL.external_symbol,
        response_adjusted_is_present=True,
        response_adjusted=True,
        request_id_is_present=False,
        request_id=None,
        query_count_is_present=True,
        query_count=900,
        results_count_is_present=True,
        results_count=250,
        count_is_present=True,
        count=250,
        next_url_is_present=False,
        next_page_reference=None,
        results_is_present=True,
        rows=tuple(aggregate(label) for label in sessions),
        response_received_at=AS_OF,
    )
    acquire = Mock(return_value=response)
    return calendar, acquire


def bind(runtime, **overrides):
    calendar, acquire = runtime
    return bind_completed_daily_current_content(
        **{
            "instrument": INSTRUMENT,
            "as_of": AS_OF,
            "calendar": calendar,
            "external_identity": EXTERNAL,
            "mappings": (MAPPING,),
            "acquire_completed_daily": acquire,
            **overrides,
        }
    )


def with_rows(runtime, rows, **changes):
    runtime[1].return_value = replace(
        runtime[1].return_value,
        rows=rows,
        count=len(rows),
        results_count=len(rows),
        **changes,
    )


@pytest.mark.parametrize("first", [HISTORY, CURRENT])
def test_lazy_present_and_shared_series(runtime, sessions, first, monkeypatch):
    # Count constructions without replacing the runtime class token.
    original = HistoricalPriceSeries.__init__
    calls = []

    def track(self, *args, **kwargs):
        calls.append(self)
        original(self, *args, **kwargs)

    monkeypatch.setattr(HistoricalPriceSeries, "__init__", track)
    loaders = bind(runtime)
    assert runtime[0].mock_calls == []
    runtime[1].assert_not_called()
    context = RadarEvaluationContext(INSTRUMENT, AS_OF, loaders)
    context.get_fact(first)
    history = context.get_fact(HISTORY).history
    current = context.get_fact(CURRENT).content
    assert history is not None and current is not None
    assert history.instrument == INSTRUMENT
    assert history.completed_session == sessions[-1]
    assert history.content_scope == RadarMarketContentScope(sessions[0], sessions[-1])
    assert len(history.series) == 250
    assert history.series.symbol == CANONICAL.trading_identity.symbol == "NVDA"
    assert history.series.symbol != EXTERNAL.external_symbol != INSTRUMENT.instrument_id
    assert tuple(history.series.timestamp_at(i).date() for i in range(250)) == sessions
    assert all(history.series.timestamp_at(i).time() == time() for i in range(250))
    assert (
        current.normalized_market_content_identity == history.series.content_fingerprint
    )
    assert current.completed_session == history.completed_session
    assert current.content_scope == history.content_scope
    assert loaders[HISTORY]().history is history
    assert calls == [history.series]
    assert runtime[0].previous_session.call_count == 249
    runtime[0].sessions_in_range.assert_called_once_with(sessions[0], sessions[-1])
    runtime[1].assert_called_once_with(
        EXTERNAL.external_symbol, sessions[0], sessions[-1]
    )
    with pytest.raises(FrozenInstanceError):
        history.completed_session = sessions[0]


@pytest.mark.parametrize("error", [NetworkError, RateLimitError])
def test_temporary_failure_is_retained(runtime, error):
    runtime[1].side_effect = error("temporary")
    loaders = bind(runtime)
    assert loaders[HISTORY]().status == Status.UNAVAILABLE
    assert loaders[CURRENT]().status.value == "UNAVAILABLE"
    assert loaders[HISTORY]() is loaders[HISTORY]()
    assert runtime[1].call_count == 1


@pytest.mark.parametrize(
    "error", [DataProviderError, AuthenticationError, ConfigurationError, ValueError]
)
def test_ordinary_failure_is_retained(runtime, error):
    failure = error("failure")
    runtime[1].side_effect = failure
    loaders = bind(runtime)
    for key in (CURRENT, HISTORY, CURRENT):
        with pytest.raises(error) as caught:
            loaders[key]()
        assert caught.value is failure
    assert runtime[1].call_count == 1


@pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
def test_process_control_propagates(runtime, error):
    runtime[1].side_effect = error()
    with pytest.raises(error):
        bind(runtime)[HISTORY]()


@pytest.mark.parametrize(
    "kind", ["latest", "internal", "empty", "absent", "short", "page"]
)
def test_unavailable_responses_retained(runtime, kind):
    rows = runtime[1].return_value.rows
    changes = {}
    if kind == "latest":
        rows = rows[:-1]
    if kind == "internal":
        rows = rows[:100] + rows[101:]
    if kind in ("empty", "absent"):
        rows = ()
    if kind == "absent":
        changes["results_is_present"] = False
    if kind == "short":
        rows = rows[-10:]
    if kind == "page":
        changes = {
            "next_url_is_present": True,
            "next_page_reference": "https://api.polygon.io/next?cursor=abc",
        }
    with_rows(runtime, rows, **changes)
    loaders = bind(runtime)
    assert loaders[HISTORY]().status == Status.UNAVAILABLE
    assert loaders[CURRENT]().status.value == "UNAVAILABLE"
    assert runtime[1].call_count == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"response_adjusted": False},
        {"response_adjusted_is_present": False, "response_adjusted": None},
        {"response_adjusted": None},
        {"response_adjusted": 1},
        {"response_ticker": "OTHER"},
        {"requested_ticker": "OTHER"},
        {"requested_from": "2020-01-01"},
        {"requested_to": "2026-09-24"},
        {"results_count": 249},
        {"count": 249},
        {"query_count": -1},
        {"query_count": True},
        {"count_is_present": False},
        {"results_is_present": False},
        {"next_url_is_present": "yes"},
        {"next_page_reference": "abc"},
        {"next_url_is_present": True, "next_page_reference": ""},
        {"next_url_is_present": True, "next_page_reference": 1},
    ],
)
def test_malformed_metadata_retained(runtime, changes):
    # Deliberately bypass frozen constructor to exercise the injected boundary.
    response = runtime[1].return_value
    for key, value in changes.items():
        object.__setattr__(response, key, value)
    loaders = bind(runtime)
    failure = None
    for key in (HISTORY, CURRENT):
        with pytest.raises((ValueError, TypeError, DataProviderError)) as caught:
            loaders[key]()
        if failure is not None:
            assert caught.value is failure
        failure = caught.value
    assert runtime[1].call_count == 1


@pytest.mark.parametrize(
    "kind", ["timestamp", "label", "non_session", "future", "before", "fraction"]
)
def test_bad_labels(runtime, sessions, kind):
    rows = runtime[1].return_value.rows
    extra = rows[0]
    if kind == "label":
        extra = replace(extra, timestamp=extra.timestamp + 1000)
    if kind == "fraction":
        extra = replace(extra, timestamp=Decimal(extra.timestamp) + Decimal("0.5"))
    if kind == "non_session":
        label = sessions[0]
        while label in sessions:
            label += timedelta(days=1)
        extra = aggregate(label)
    if kind == "future":
        extra = aggregate(sessions[-1] + timedelta(days=1))
    if kind == "before":
        extra = aggregate(sessions[0] - timedelta(days=1))
    with_rows(runtime, rows + (extra,))
    with pytest.raises(ValueError):
        bind(runtime)[HISTORY]()


@pytest.mark.parametrize(
    "field,value",
    [
        ("open", Decimal("NaN")),
        ("high", Decimal("Infinity")),
        ("low", -1),
        ("close", 200),
        ("volume", -1),
        ("open", "100"),
        ("volume", True),
        ("open", Decimal("1e1000")),
        ("open", Decimal("1e-1000")),
        ("high", 95),
        ("close", 0),
    ],
)
@pytest.mark.parametrize("short", [False, True])
def test_malformed_ohlcv_is_failure_even_when_short(runtime, field, value, short):
    rows = runtime[1].return_value.rows
    object.__setattr__(rows[0], field, value)
    with_rows(runtime, rows[:-1] if short else rows)
    with pytest.raises((ValueError, TypeError, DataProviderError)):
        bind(runtime)[HISTORY]()


def test_unsorted_normalizes_same_identity(runtime):
    first = bind(runtime)[HISTORY]().history
    with_rows(runtime, tuple(reversed(runtime[1].return_value.rows)))
    second = bind(runtime)[HISTORY]().history
    assert first.series.content_fingerprint == second.series.content_fingerprint
    assert first.series is not second.series
    assert runtime[1].call_count == 2  # Fresh execution, no process cache.


@pytest.mark.parametrize(
    "kind", ["missing", "inactive", "starts_late", "expires_last", "stitch"]
)
def test_mapping_unavailable(runtime, sessions, kind):
    mappings = (MAPPING,)
    if kind == "missing":
        mappings = ()
    if kind == "inactive":
        mappings = (replace(MAPPING, expires_at=datetime(2001, 1, 1, tzinfo=UTC)),)
    if kind == "starts_late":
        mappings = (
            replace(MAPPING, valid_from=datetime.combine(sessions[1], time(), UTC)),
        )
    if kind == "expires_last":
        mappings = (
            replace(MAPPING, expires_at=datetime.combine(sessions[-1], time(), UTC)),
        )
    if kind == "stitch":
        boundary = datetime.combine(sessions[100], time(), UTC)
        mappings = (
            replace(MAPPING, expires_at=boundary),
            replace(MAPPING, valid_from=boundary),
        )
    loaders = bind(runtime, mappings=mappings)
    assert loaders[HISTORY]().status == Status.UNAVAILABLE
    assert loaders[CURRENT]().status.value == "UNAVAILABLE"
    runtime[1].assert_not_called()


@pytest.mark.parametrize(
    "kind,error",
    [
        ("duplicate", InstrumentMappingDuplicateError),
        ("ambiguous", InstrumentMappingAmbiguousError),
        ("conflict", InstrumentMappingConflictError),
        ("wrong", ValueError),
        ("partial_start", ValueError),
        ("partial_end", ValueError),
        ("gap_then_conflict", InstrumentMappingAmbiguousError),
    ],
)
def test_mapping_failures(runtime, sessions, kind, error):
    other = replace(
        MAPPING,
        canonical_instrument=replace(
            CANONICAL, instrument_id=CanonicalInstrumentId("other")
        ),
    )
    mappings = (MAPPING,)
    if kind == "duplicate":
        mappings = (MAPPING, MAPPING)
    if kind == "ambiguous":
        mappings = (
            MAPPING,
            replace(MAPPING, source=InstrumentMappingSourceIdentity("other", "1")),
        )
    if kind == "conflict":
        mappings = (MAPPING, other)
    if kind == "wrong":
        mappings = (other,)
    if kind == "partial_start":
        mappings = (
            replace(MAPPING, valid_from=MAPPING.valid_from + timedelta(hours=1)),
        )
    if kind == "partial_end":
        mappings = (replace(MAPPING, expires_at=AS_OF + timedelta(hours=1)),)
    if kind == "gap_then_conflict":
        start = datetime.combine(sessions[10], time(), UTC)
        mappings = (
            replace(MAPPING, valid_from=start),
            replace(MAPPING, valid_from=start + timedelta(days=1)),
        )
    with pytest.raises(error):
        bind(runtime, mappings=mappings)[HISTORY]()
    runtime[1].assert_not_called()


def test_mapping_exact_inclusive_exclusive_boundaries(runtime, sessions):
    mapping = replace(
        MAPPING,
        valid_from=datetime.combine(sessions[0], time(), UTC),
        expires_at=datetime.combine(sessions[-1] + timedelta(days=1), time(), UTC),
    )
    assert bind(runtime, mappings=(mapping,))[HISTORY]().status == Status.PRESENT


@pytest.mark.parametrize("kind", ["short", "start", "end", "coverage"])
def test_calendar_failure_retained(runtime, sessions, kind):
    if kind == "short":
        runtime[0].sessions_in_range.return_value = sessions[:-1]
    if kind == "start":
        runtime[0].sessions_in_range.return_value = (
            sessions[0] - timedelta(days=1),
        ) + sessions[1:]
    if kind == "end":
        runtime[0].sessions_in_range.return_value = sessions[:-1] + (
            sessions[-1] + timedelta(days=1),
        )
    if kind == "coverage":
        runtime[0].previous_session.side_effect = CalendarCoverageError("coverage")
    loaders = bind(runtime)
    for key in (HISTORY, CURRENT):
        with pytest.raises(CalendarCoverageError):
            loaders[key]()
    runtime[1].assert_not_called()


def test_lookup_invariants_and_stable_key():
    assert HISTORY.fact_id == "radar.completed_daily_history_lookup/v1"
    assert HISTORY.value_type is RadarCompletedDailyHistoryLookupResult
    with pytest.raises(ValueError):
        RadarCompletedDailyHistoryLookupResult(Status.PRESENT)
    with pytest.raises(ValueError):
        RadarCompletedDailyHistoryLookupResult(Status.UNAVAILABLE, object())
    with pytest.raises(TypeError):
        RadarCompletedDailyHistoryLookupResult("UNAVAILABLE")


def test_real_trigger_application_and_durable_checkpoint(runtime, tmp_path):
    key = SESSION_CONTENT_TRIGGER_KEY
    occurrence = RadarGateOccurrence(
        "trigger",
        RadarGateIdentity(
            key.gate_id, key.behavioral_revision, key.configuration_schema
        ),
    )
    profile = RadarProfile("test", "1", "test/v1", (occurrence,))
    resolver = RadarGateResolver(
        [
            RadarGateFactoryBinding(
                key, lambda item: RadarSessionContentTriggerGate(item, runtime[0])
            )
        ]
    )
    store = RadarCheckpointFileStore(tmp_path)
    service = RadarApplicationService(resolver, store, lambda: AS_OF)
    loaders = bind(runtime)
    result = service.evaluate(profile, INSTRUMENT, AS_OF, loaders)
    assert result.advancement is RadarCheckpointAdvancement.SAVED
    assert result.pipeline_result.executed_results[0].reason_code == "BASELINE_REQUIRED"
    checkpoint = RadarCheckpointFileStore(tmp_path).lookup(INSTRUMENT).checkpoint
    history = loaders[HISTORY]().history
    assert checkpoint == result.saved_checkpoint
    assert (
        checkpoint.normalized_market_content_identity
        == history.series.content_fingerprint
    )
    assert checkpoint.content_scope == history.content_scope
    assert runtime[1].call_count == 1


@pytest.mark.parametrize("null", [False, True])
def test_optional_metadata_and_distinct_query_count(runtime, null):
    changes = {"next_url_is_present": True, "next_page_reference": None}
    for name in ("response_ticker", "request_id", "results_count", "count"):
        changes[name] = None
        changes[name + "_is_present"] = null
    runtime[1].return_value = replace(runtime[1].return_value, **changes)
    assert bind(runtime)[HISTORY]().status == Status.PRESENT


def test_pagination_does_not_hide_bad_rows(runtime):
    rows = runtime[1].return_value.rows
    with_rows(
        runtime,
        (replace(rows[0], close=200),),
        next_url_is_present=True,
        next_page_reference="https://api.polygon.io/next?cursor=abc",
    )
    with pytest.raises(ValueError, match="OHLCV"):
        bind(runtime)[CURRENT]()


def test_fingerprint_failure_is_retained(runtime, monkeypatch):
    failure = ValueError("fingerprint failure")

    def fail(self):
        raise failure

    monkeypatch.setattr(HistoricalPriceSeries, "content_fingerprint", property(fail))
    loaders = bind(runtime)
    for key in (HISTORY, CURRENT):
        with pytest.raises(ValueError) as caught:
            loaders[key]()
        assert caught.value is failure
    assert runtime[1].call_count == 1


def test_history_value_rejects_wrong_scope(runtime, sessions):
    history = bind(runtime)[HISTORY]().history
    with pytest.raises(ValueError):
        replace(history, completed_session=sessions[-2])
    with pytest.raises(ValueError):
        replace(
            history, content_scope=RadarMarketContentScope(sessions[1], sessions[-1])
        )


def test_wrong_provider_namespace_fails_lazily(runtime):
    loaders = bind(
        runtime, external_identity=ExternalInstrumentIdentity("other", "NVDA")
    )
    runtime[1].assert_not_called()
    with pytest.raises(ValueError, match="Polygon"):
        loaders[HISTORY]()


def test_daily_labels_use_new_york_date_across_dst(runtime, sessions):
    # A UTC date extraction would shift these source rows to the next day.
    rows = tuple(
        replace(
            row,
            timestamp=int(
                datetime.combine(
                    label, time(23), ZoneInfo("America/New_York")
                ).timestamp()
                * 1000
            ),
        )
        for row, label in zip(runtime[1].return_value.rows, sessions, strict=True)
    )
    assert {
        datetime.combine(label, time(), ZoneInfo("America/New_York")).utcoffset()
        for label in sessions
    } == {timedelta(hours=-4), timedelta(hours=-5)}
    with_rows(runtime, rows)
    history = bind(runtime)[HISTORY]().history
    assert tuple(history.series.timestamp_at(i).date() for i in range(250)) == sessions
