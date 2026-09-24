"""Bounded NASDAQ reference regressions approved in ADR0046."""

from datetime import UTC, date, datetime, time, timedelta
from typing import get_type_hints
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import exchange_calendars
import pytest

from market_platform.radar import calendar as calendar_module
from market_platform.radar.calendar import (
    CalendarCoverageError,
    CalendarError,
    CalendarInputError,
    CalendarNonSessionError,
    ExchangeCalendarsSessionCalendar,
    ExchangeSessionCalendar,
)

ET = ZoneInfo("America/New_York")
OPERATIONS = {
    "is_session",
    "session_open",
    "session_close",
    "is_early_close",
    "previous_session",
    "next_session",
    "latest_completed_session",
    "sessions_in_range",
}


@pytest.fixture(scope="module")
def calendar() -> ExchangeSessionCalendar:
    return ExchangeCalendarsSessionCalendar()


@pytest.mark.parametrize(
    "day",
    [
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-04-03",
        "2026-05-25",
        "2026-06-19",
        "2026-07-03",
        "2026-09-07",
        "2026-11-26",
        "2026-12-25",
    ],
)
def test_official_closed_dates(calendar: ExchangeSessionCalendar, day: str) -> None:
    assert calendar.is_session(date.fromisoformat(day)) is False


@pytest.mark.parametrize("day", [date(2026, 11, 27), date(2026, 12, 24)])
def test_official_early_closes(calendar: ExchangeSessionCalendar, day: date) -> None:
    assert calendar.is_session(day) is True
    assert calendar.is_early_close(day) is True
    assert calendar.session_open(day) == datetime.combine(day, time(9, 30), ET)
    assert calendar.session_close(day) == datetime.combine(day, time(13), ET)


def test_regular_session_and_stdlib_results(calendar: ExchangeSessionCalendar) -> None:
    day = date(2026, 6, 10)
    assert calendar.is_session(day) is True
    assert calendar.is_early_close(day) is False
    for actual, hour, minute in [
        (calendar.session_open(day), 9, 30),
        (calendar.session_close(day), 16, 0),
    ]:
        assert type(actual) is datetime
        assert actual.tzinfo is UTC
        assert actual == datetime.combine(day, time(hour, minute), ET)
    assert type(calendar.previous_session(day)) is date
    assert type(calendar.next_session(day)) is date
    assert type(calendar.latest_completed_session(calendar.session_close(day))) is date
    sessions = calendar.sessions_in_range(day, day)
    assert type(sessions) is tuple
    assert all(type(item) is date for item in sessions)


@pytest.mark.parametrize(
    ("day", "previous", "following"),
    [
        ("2026-06-10", "2026-06-09", "2026-06-11"),
        ("2026-06-13", "2026-06-12", "2026-06-15"),
        ("2026-04-03", "2026-04-02", "2026-04-06"),
        ("2026-04-06", "2026-04-02", "2026-04-07"),
        ("2026-07-03", "2026-07-02", "2026-07-06"),
        ("2026-07-02", "2026-07-01", "2026-07-06"),
        ("2026-11-26", "2026-11-25", "2026-11-27"),
        ("2026-11-27", "2026-11-25", "2026-11-30"),
    ],
)
def test_strict_navigation(
    calendar: ExchangeSessionCalendar, day: str, previous: str, following: str
) -> None:
    assert calendar.previous_session(date.fromisoformat(day)) == date.fromisoformat(
        previous
    )
    assert calendar.next_session(date.fromisoformat(day)) == date.fromisoformat(
        following
    )


@pytest.mark.parametrize(
    ("day", "previous"),
    [
        (date(2026, 6, 10), date(2026, 6, 9)),
        (date(2026, 11, 27), date(2026, 11, 25)),
        (date(2026, 12, 24), date(2026, 12, 23)),
    ],
)
def test_completion_at_actual_close(
    calendar: ExchangeSessionCalendar, day: date, previous: date
) -> None:
    close = calendar.session_close(day)
    assert (
        calendar.latest_completed_session(close - timedelta(microseconds=1)) == previous
    )
    assert calendar.latest_completed_session(close) == day
    assert calendar.latest_completed_session(close.astimezone(ET)) == day


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        (datetime(2026, 6, 10, 8, tzinfo=ET), date(2026, 6, 9)),
        (datetime(2026, 6, 10, 12, tzinfo=ET), date(2026, 6, 9)),
        (datetime(2026, 6, 13, 12, tzinfo=ET), date(2026, 6, 12)),
        (datetime(2026, 4, 3, 17, tzinfo=ET), date(2026, 4, 2)),
        (datetime(2026, 7, 3, 17, tzinfo=ET), date(2026, 7, 2)),
        (datetime(2026, 11, 26, 17, tzinfo=ET), date(2026, 11, 25)),
    ],
)
def test_latest_completed(
    calendar: ExchangeSessionCalendar, instant: datetime, expected: date
) -> None:
    assert calendar.latest_completed_session(instant) == expected


@pytest.mark.parametrize(
    ("day", "open_hour", "close_hour"),
    [
        (date(2026, 3, 6), 14, 21),
        (date(2026, 3, 9), 13, 20),
        (date(2026, 10, 30), 13, 20),
        (date(2026, 11, 2), 14, 21),
    ],
)
def test_dst_utc_shift(
    calendar: ExchangeSessionCalendar, day: date, open_hour: int, close_hour: int
) -> None:
    assert calendar.session_open(day) == datetime.combine(day, time(open_hour, 30), UTC)
    assert calendar.session_close(day) == datetime.combine(day, time(close_hour), UTC)
    assert calendar.session_open(day).astimezone(ET).time() == time(9, 30)
    assert calendar.session_close(day).astimezone(ET).time() == time(16)


def test_ranges(calendar: ExchangeSessionCalendar) -> None:
    assert calendar.sessions_in_range(date(2026, 11, 25), date(2026, 11, 30)) == (
        date(2026, 11, 25),
        date(2026, 11, 27),
        date(2026, 11, 30),
    )
    assert calendar.sessions_in_range(date(2026, 4, 3), date(2026, 4, 5)) == ()
    assert calendar.sessions_in_range(date(2026, 6, 10), date(2026, 6, 10)) == (
        date(2026, 6, 10),
    )
    with pytest.raises(CalendarInputError):
        calendar.sessions_in_range(date(2026, 6, 11), date(2026, 6, 10))


@pytest.mark.parametrize(
    "operation", ["session_open", "session_close", "is_early_close"]
)
@pytest.mark.parametrize("day", [date(2026, 6, 13), date(2026, 4, 3)])
def test_non_session_errors(
    calendar: ExchangeSessionCalendar, operation: str, day: date
) -> None:
    with pytest.raises(CalendarNonSessionError, match="NASDAQ"):
        getattr(calendar, operation)(day)


@pytest.mark.parametrize(
    "value", [datetime(2026, 6, 10), date(2026, 6, 10), "2026-06-10", None]
)
def test_invalid_as_of(calendar: ExchangeSessionCalendar, value: object) -> None:
    with pytest.raises(CalendarInputError):
        calendar.latest_completed_session(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "instant", [datetime.min.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC)]
)
def test_extreme_as_of_coverage(
    calendar: ExchangeSessionCalendar, instant: datetime
) -> None:
    with pytest.raises(CalendarCoverageError):
        calendar.latest_completed_session(instant)


@pytest.mark.parametrize("invalid_start", [False, True])
def test_invalid_range_endpoint(
    calendar: ExchangeSessionCalendar, invalid_start: bool
) -> None:
    valid = date(2026, 6, 10)
    invalid = datetime(2026, 6, 10, tzinfo=UTC)
    with pytest.raises(CalendarInputError):
        calendar.sessions_in_range(
            invalid if invalid_start else valid, valid if invalid_start else invalid
        )


@pytest.mark.parametrize(
    "operation", sorted(OPERATIONS - {"latest_completed_session", "sessions_in_range"})
)
@pytest.mark.parametrize(
    "value", ["2026-06-10", datetime(2026, 6, 10, tzinfo=UTC), None]
)
def test_invalid_date(
    calendar: ExchangeSessionCalendar, operation: str, value: object
) -> None:
    with pytest.raises(CalendarInputError):
        getattr(calendar, operation)(value)


@pytest.fixture
def bounded_calendar(
    monkeypatch: pytest.MonkeyPatch,
) -> ExchangeCalendarsSessionCalendar:
    # Private adapter test seam: arbitrary backend coverage, not a public horizon.
    backend = exchange_calendars.get_calendar(
        "NASDAQ", start="2026-06-10", end="2026-06-16"
    )
    monkeypatch.setattr(
        calendar_module._exchange_calendars, "get_calendar", Mock(return_value=backend)
    )
    return ExchangeCalendarsSessionCalendar()


@pytest.mark.parametrize(
    "operation", sorted(OPERATIONS - {"latest_completed_session", "sessions_in_range"})
)
@pytest.mark.parametrize("day", [date(2026, 6, 9), date(2026, 6, 17)])
def test_date_coverage(
    bounded_calendar: ExchangeSessionCalendar, operation: str, day: date
) -> None:
    with pytest.raises(CalendarCoverageError):
        getattr(bounded_calendar, operation)(day)


def test_coverage_edges(bounded_calendar: ExchangeSessionCalendar) -> None:
    first, last = date(2026, 6, 10), date(2026, 6, 16)
    assert bounded_calendar.is_session(first)
    assert bounded_calendar.is_session(last)
    for operation, day in [
        (bounded_calendar.previous_session, first),
        (bounded_calendar.next_session, last),
    ]:
        with pytest.raises(CalendarCoverageError):
            operation(day)
    with pytest.raises(CalendarCoverageError):
        bounded_calendar.latest_completed_session(bounded_calendar.session_open(first))
    assert (
        bounded_calendar.latest_completed_session(bounded_calendar.session_close(first))
        == first
    )
    assert (
        bounded_calendar.latest_completed_session(bounded_calendar.session_close(last))
        == last
    )
    # UTC next date still falls on the final supported exchange-local date.
    assert (
        bounded_calendar.latest_completed_session(datetime(2026, 6, 17, 1, tzinfo=UTC))
        == last
    )
    for day in [first - timedelta(days=1), last + timedelta(days=1)]:
        with pytest.raises(CalendarCoverageError):
            bounded_calendar.latest_completed_session(
                datetime.combine(day, time(12), ET)
            )
    for start, end in [
        (first - timedelta(days=1), first),
        (last, last + timedelta(days=1)),
    ]:
        with pytest.raises(CalendarCoverageError):
            bounded_calendar.sessions_in_range(start, end)


def test_private_backend_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = Mock(wraps=exchange_calendars.get_calendar)
    monkeypatch.setattr(calendar_module._exchange_calendars, "get_calendar", factory)
    calendar = ExchangeCalendarsSessionCalendar()
    factory.assert_called_once_with("XNYS")  # Only the private adapter mapping.
    assert calendar.venue == "NASDAQ"
    assert "XNYS" not in repr(calendar)


@pytest.mark.parametrize("during_read", [False, True])
def test_backend_failure_containment(
    monkeypatch: pytest.MonkeyPatch, during_read: bool
) -> None:
    failure = exchange_calendars.errors.InvalidCalendarName(
        calendar_name="private-backend"
    )
    if during_read:
        backend = Mock()
        backend.first_session.date.side_effect = failure
        factory = Mock(return_value=backend)
    else:
        factory = Mock(side_effect=failure)
    monkeypatch.setattr(calendar_module._exchange_calendars, "get_calendar", factory)
    with pytest.raises(CalendarError, match="NASDAQ") as caught:
        ExchangeCalendarsSessionCalendar()
    assert type(caught.value) is CalendarError
    assert "private-backend" not in str(caught.value)
    assert caught.value.__cause__ is failure  # Private diagnostic detail only.


def test_session_fact_api_scope() -> None:
    # Narrow API/import inspection; no governed objects or AST coupling needed.
    assert {
        name for name in vars(ExchangeSessionCalendar) if not name.startswith("_")
    } == OPERATIONS
    assert {
        name
        for name in vars(ExchangeCalendarsSessionCalendar)
        if not name.startswith("_")
    } == OPERATIONS | {"venue"}
    for name in OPERATIONS:
        hints = get_type_hints(getattr(ExchangeSessionCalendar, name))
        assert set(hints.values()) <= {date, datetime, bool, tuple[date, ...]}
    assert not any(
        getattr(value, "__module__", "").startswith("market_platform.")
        and getattr(value, "__module__", "") != calendar_module.__name__
        for value in vars(calendar_module).values()
    )
