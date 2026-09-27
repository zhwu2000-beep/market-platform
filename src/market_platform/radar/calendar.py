"""Regular exchange session facts, independent of provider data availability."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import UTC, date, datetime
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

import exchange_calendars as _exchange_calendars  # type: ignore[import-untyped]


class CalendarError(Exception):
    """Calendar infrastructure failure, with no governed authority meaning."""


class CalendarInputError(CalendarError):
    """The query does not satisfy the calendar input contract."""


class CalendarNonSessionError(CalendarError):
    """The operation requires a real session."""


class CalendarCoverageError(CalendarError):
    """The query or its answer falls outside supported coverage."""


class ExchangeSessionCalendar(Protocol):
    """Session facts only; completion does not establish data availability."""

    def is_session(self, session_date: date) -> bool:
        """Return whether an in-coverage date is a regular session."""
        ...

    def session_open(self, session_date: date) -> datetime:
        """Return a real session's open as an aware UTC datetime."""
        ...

    def session_close(self, session_date: date) -> datetime:
        """Return a real session's actual close as an aware UTC datetime."""
        ...

    def is_early_close(self, session_date: date) -> bool:
        """Return the early-close fact for a real session."""
        ...

    def previous_session(self, session_date: date) -> date:
        """Return the nearest session strictly before the supplied date."""
        ...

    def next_session(self, session_date: date) -> date:
        """Return the nearest session strictly after the supplied date."""
        ...

    def latest_completed_session(self, as_of: datetime) -> date:
        """Return the latest session whose actual close is <= aware as_of."""
        ...

    def sessions_in_range(self, start: date, end: date) -> tuple[date, ...]:
        """Return ordered sessions in an inclusive, in-coverage date range."""
        ...


class ExchangeCalendarsSessionCalendar:
    """NASDAQ regular sessions supplied by the approved external backend.

    Snapshot the backend instance's full schedule into private stdlib values.
    Coverage is inclusive from its first through last session, not a fixed
    production horizon. As-of coverage uses the exchange-local calendar date.
    The snapshot retains the coverage supplied at construction.
    """

    def __init__(self) -> None:
        # This mapping is private infrastructure, not public instrument identity.
        try:
            backend = _exchange_calendars.get_calendar("XNYS")
            self._first: date = backend.first_session.date()
            self._last: date = backend.last_session.date()
            self._timezone = ZoneInfo(str(backend.tz))
            self._sessions: tuple[date, ...] = tuple(
                label.date() for label in backend.sessions
            )
            self._opens: tuple[datetime, ...] = tuple(
                value.to_pydatetime().astimezone(UTC) for value in backend.opens
            )
            self._closes: tuple[datetime, ...] = tuple(
                value.to_pydatetime().astimezone(UTC) for value in backend.closes
            )
            self._early_closes: frozenset[date] = frozenset(
                label.date() for label in backend.early_closes
            )
        except Exception as exc:
            # All third-party execution is contained in this construction boundary.
            raise CalendarError("Unable to load the NASDAQ session calendar") from exc

    @property
    def venue(self) -> Literal["NASDAQ"]:
        """Public market-platform venue identity."""
        return "NASDAQ"

    def is_session(self, session_date: date) -> bool:
        self._validate_date(session_date)
        index = bisect_left(self._sessions, session_date)
        return index < len(self._sessions) and self._sessions[index] == session_date

    def session_open(self, session_date: date) -> datetime:
        return self._opens[self._session_index(session_date)]

    def session_close(self, session_date: date) -> datetime:
        return self._closes[self._session_index(session_date)]

    def is_early_close(self, session_date: date) -> bool:
        self._session_index(session_date)
        return session_date in self._early_closes

    def previous_session(self, session_date: date) -> date:
        self._validate_date(session_date)
        index = bisect_left(self._sessions, session_date) - 1
        return self._session_at(index)

    def next_session(self, session_date: date) -> date:
        self._validate_date(session_date)
        index = bisect_right(self._sessions, session_date)
        return self._session_at(index)

    def latest_completed_session(self, as_of: datetime) -> date:
        if not isinstance(as_of, datetime):
            raise CalendarInputError("as_of must be a timezone-aware datetime")
        try:
            if as_of.utcoffset() is None:
                raise CalendarInputError("as_of must be a timezone-aware datetime")
            instant = as_of.astimezone(UTC)
            local_date = instant.astimezone(self._timezone).date()
        except OverflowError as exc:
            raise CalendarCoverageError("as_of is outside NASDAQ coverage") from exc
        except ValueError as exc:
            raise CalendarInputError("as_of cannot be normalized") from exc
        self._validate_date(local_date)
        return self._session_at(bisect_right(self._closes, instant) - 1)

    def sessions_in_range(self, start: date, end: date) -> tuple[date, ...]:
        self._validate_date(start)
        self._validate_date(end)
        if start > end:
            raise CalendarInputError("start must be on or before end")
        return self._sessions[
            bisect_left(self._sessions, start) : bisect_right(self._sessions, end)
        ]

    def _validate_date(self, value: date) -> None:
        if not isinstance(value, date) or isinstance(value, datetime):
            raise CalendarInputError("session date must be a date, not a datetime")
        if not self._first <= value <= self._last:
            raise CalendarCoverageError(
                f"NASDAQ calendar coverage is {self._first} through {self._last}"
            )

    def _session_index(self, session_date: date) -> int:
        if not self.is_session(session_date):
            raise CalendarNonSessionError(f"{session_date} is not a NASDAQ session")
        return bisect_left(self._sessions, session_date)

    def _session_at(self, index: int) -> date:
        if not 0 <= index < len(self._sessions):
            raise CalendarCoverageError("Required NASDAQ session is outside coverage")
        return self._sessions[index]
