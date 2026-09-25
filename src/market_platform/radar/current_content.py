"""Fresh synchronous completed-daily Radar inputs under ADR0048, without authority."""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from market_platform.data.exceptions import NetworkError, RateLimitError
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.models import PRICE_COLUMNS
from market_platform.data.providers.polygon import PolygonCompletedDailyAcquisition
from market_platform.instruments.errors import (
    InstrumentMappingInactiveError,
    InstrumentMappingNotFoundError,
)
from market_platform.instruments.identity import (
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
)
from market_platform.instruments.mapping import InstrumentMapping
from market_platform.instruments.resolver import resolve_instrument_mapping
from market_platform.radar.calendar import (
    CalendarCoverageError,
    ExchangeSessionCalendar,
)
from market_platform.radar.context import RadarFactKey
from market_platform.radar.observation import RadarMarketContentScope
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP,
    RadarCurrentMarketContent,
    RadarCurrentMarketContentLookupResult,
    RadarCurrentMarketContentLookupStatus,
)


class CompletedDailyAcquirer(Protocol):
    """Outer runtime composition owns any bridge to the async Polygon API."""

    def __call__(
        self, ticker: str, start: date, end: date, /
    ) -> PolygonCompletedDailyAcquisition: ...


@dataclass(frozen=True, slots=True)
class RadarCompletedDailyHistory:
    """Read-only execution-local history; the binding proves correspondence."""

    instrument: CanonicalInstrumentId
    completed_session: date
    content_scope: RadarMarketContentScope
    series: HistoricalPriceSeries

    def __post_init__(self) -> None:
        if type(self.instrument) is not CanonicalInstrumentId:
            raise TypeError("instrument must be a CanonicalInstrumentId")
        if type(self.content_scope) is not RadarMarketContentScope:
            raise TypeError("content_scope must be a RadarMarketContentScope")
        if type(self.completed_session) is not date:
            raise TypeError("completed_session must be a date")
        if self.completed_session != self.content_scope.history_end:
            raise ValueError("completed_session must equal history_end")
        if type(self.series) is not HistoricalPriceSeries:
            raise TypeError("series must be a HistoricalPriceSeries")
        labels = tuple(self.series.timestamp_at(i) for i in range(len(self.series)))
        if (
            len(labels) != 250
            or labels[0].date() != self.content_scope.history_start
            or labels[-1].date() != self.completed_session
            or any(label.time() != time() for label in labels)
        ):
            raise ValueError("series must retain the exact 250-session daily scope")


class RadarCompletedDailyHistoryLookupStatus(StrEnum):
    PRESENT = "PRESENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class RadarCompletedDailyHistoryLookupResult:
    status: RadarCompletedDailyHistoryLookupStatus
    history: RadarCompletedDailyHistory | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not RadarCompletedDailyHistoryLookupStatus:
            raise TypeError("status must be RadarCompletedDailyHistoryLookupStatus")
        if self.status is RadarCompletedDailyHistoryLookupStatus.PRESENT:
            if type(self.history) is not RadarCompletedDailyHistory:
                raise ValueError("PRESENT requires history")
        elif self.history is not None:
            raise ValueError("UNAVAILABLE forbids history")


COMPLETED_DAILY_HISTORY_LOOKUP = RadarFactKey(
    "radar.completed_daily_history_lookup/v1", RadarCompletedDailyHistoryLookupResult
)


def bind_completed_daily_current_content(
    *,
    instrument: CanonicalInstrumentId,
    as_of: datetime,
    calendar: ExchangeSessionCalendar,
    external_identity: ExternalInstrumentIdentity,
    mappings: tuple[InstrumentMapping, ...],
    acquire_completed_daily: CompletedDailyAcquirer,
) -> dict[RadarFactKey[object], Callable[[], object]]:
    """Create lazy loaders for one evaluation; call again for each new execution.

    No calendar or acquisition work occurs here. Validation is lazy. The retained
    HistoricalPriceSeries owns its frame; consumers must treat it as read-only.
    """
    producer = _HistoryProducer(
        lambda: _acquire_history(
            instrument,
            as_of,
            calendar,
            external_identity,
            mappings,
            acquire_completed_daily,
        )
    )

    def current_content() -> RadarCurrentMarketContentLookupResult:
        lookup = producer.get()
        if lookup.history is None:
            return RadarCurrentMarketContentLookupResult(
                RadarCurrentMarketContentLookupStatus.UNAVAILABLE
            )
        history = lookup.history
        return RadarCurrentMarketContentLookupResult(
            RadarCurrentMarketContentLookupStatus.PRESENT,
            RadarCurrentMarketContent(
                instrument=history.instrument,
                completed_session=history.completed_session,
                normalized_market_content_identity=history.series.content_fingerprint,
                content_scope=history.content_scope,
            ),
        )

    return {
        COMPLETED_DAILY_HISTORY_LOOKUP: producer.get,
        CURRENT_MARKET_CONTENT_LOOKUP: current_content,
    }


class _HistoryProducer:
    def __init__(self, produce: Callable[[], RadarCompletedDailyHistoryLookupResult]):
        self._produce = produce
        self._result: RadarCompletedDailyHistoryLookupResult | None = None
        self._failure: Exception | None = None

    def get(self) -> RadarCompletedDailyHistoryLookupResult:
        if self._failure is not None:
            raise self._failure
        if self._result is None:
            try:
                self._result = self._produce()
            except Exception as error:
                self._failure = error
                raise
        return self._result


def _unavailable() -> RadarCompletedDailyHistoryLookupResult:
    return RadarCompletedDailyHistoryLookupResult(
        RadarCompletedDailyHistoryLookupStatus.UNAVAILABLE
    )


def _window_mapping(
    instrument: CanonicalInstrumentId,
    external: ExternalInstrumentIdentity,
    mappings: tuple[InstrumentMapping, ...],
    sessions: tuple[date, ...],
) -> InstrumentMapping | None:
    if (
        type(external) is not ExternalInstrumentIdentity
        or external.namespace != "polygon"
    ):
        raise ValueError("external identity must belong to Polygon")
    selected: InstrumentMapping | None = None
    unavailable = False
    # Resolve every label, even after a gap, so unavailable cannot mask conflicts.
    for label in sessions:
        try:
            mapping = resolve_instrument_mapping(
                external, mappings, datetime.combine(label, time(), UTC)
            ).mapping
        except InstrumentMappingNotFoundError, InstrumentMappingInactiveError:
            unavailable = True
            continue
        if mapping.canonical_instrument.instrument_id != instrument:
            raise ValueError("mapping resolves to another canonical instrument")
        if selected is not None and selected != mapping:
            unavailable = True  # Never stitch successive mapping records.
        selected = mapping
    for mapping in mappings:
        if mapping.external_identity == external:
            for bound in (mapping.valid_from, mapping.expires_at):
                if bound is not None and (
                    bound.tzinfo is not UTC or bound.time() != time()
                ):
                    raise ValueError("partial-day mapping boundary is unsupported")
    return None if unavailable else selected


def _acquire_history(
    instrument: CanonicalInstrumentId,
    as_of: datetime,
    calendar: ExchangeSessionCalendar,
    external: ExternalInstrumentIdentity,
    mappings: tuple[InstrumentMapping, ...],
    acquire: CompletedDailyAcquirer,
) -> RadarCompletedDailyHistoryLookupResult:
    if type(instrument) is not CanonicalInstrumentId:
        raise TypeError("instrument must be a CanonicalInstrumentId")
    latest = calendar.latest_completed_session(as_of)
    start = latest
    for _ in range(249):
        start = calendar.previous_session(start)
    expected = calendar.sessions_in_range(start, latest)
    if (
        len(expected) != 250
        or expected[0] != start
        or expected[-1] != latest
        or tuple(sorted(set(expected))) != expected
    ):
        raise CalendarCoverageError("Calendar must supply exactly 250 ordered sessions")
    mapping = _window_mapping(instrument, external, mappings, expected)
    if mapping is None:
        return _unavailable()
    try:
        acquisition = acquire(external.external_symbol, start, latest)
    except NetworkError, RateLimitError:
        return _unavailable()
    _validate_metadata(acquisition, external.external_symbol, start, latest)
    # This is the production bridge's normalized market symbol, distinct from
    # both the opaque canonical ID and the external provider alias.
    symbol = mapping.canonical_instrument.trading_identity.symbol
    rows: list[tuple[object, ...]] = []
    timestamps: set[int | Decimal] = set()
    labels: set[date] = set()
    for row in acquisition.rows:
        replace(row)  # Public contract: exact finite source numbers.
        if row.timestamp != int(row.timestamp):
            raise ValueError("daily timestamp must be integral Unix milliseconds")
        if row.timestamp in timestamps:
            raise ValueError("duplicate raw timestamp")
        timestamps.add(row.timestamp)
        instant = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            milliseconds=int(row.timestamp)
        )
        label = instant.astimezone(ZoneInfo("America/New_York")).date()
        if label in labels:
            raise ValueError("duplicate daily session label")
        labels.add(label)
        if not start <= label <= latest:
            raise ValueError("daily label outside requested bounds")
        if not calendar.is_session(label):
            raise ValueError("daily label is not a Calendar session")
        values = (row.open, row.high, row.low, row.close, row.volume)
        # Validate raw rows before short/page responses become UNAVAILABLE.
        # Float compatibility follows HistoricalPriceSeries normalization.
        normalized = tuple(float(value) for value in values)
        if any(not math.isfinite(value) for value in normalized):
            raise ValueError("OHLCV must be finite in normalized representation")
        if (
            min(normalized[:4]) <= 0
            or row.volume < 0
            or row.high < max(row.open, row.low, row.close)
            or row.low > min(row.open, row.close)
        ):
            raise ValueError("incompatible OHLCV")
        rows.append((symbol, datetime.combine(label, time(), UTC), *values, "polygon"))
    if (
        acquisition.additional_page_indicated
        or not acquisition.results_is_present
        or tuple(sorted(labels)) != expected
    ):
        return _unavailable()
    series = HistoricalPriceSeries(
        pd.DataFrame(rows, columns=PRICE_COLUMNS), symbol=symbol
    )
    if tuple(series.timestamp_at(i).date() for i in range(len(series))) != expected:
        raise ValueError("normalized history differs from Calendar scope")
    _ = series.content_fingerprint  # Memoize fingerprint failures in the producer.
    return RadarCompletedDailyHistoryLookupResult(
        RadarCompletedDailyHistoryLookupStatus.PRESENT,
        RadarCompletedDailyHistory(
            instrument, latest, RadarMarketContentScope(start, latest), series
        ),
    )


def _validate_metadata(
    acquisition: PolygonCompletedDailyAcquisition, ticker: str, start: date, end: date
) -> None:
    if type(acquisition) is not PolygonCompletedDailyAcquisition:
        raise TypeError("acquirer must return PolygonCompletedDailyAcquisition")
    # Public constructor validates presence/value types and sanitized pagination.
    validated = replace(acquisition)
    if validated != acquisition:
        raise ValueError("acquisition does not retain canonical transport state")
    if (
        acquisition.requested_ticker != ticker
        or acquisition.requested_from != start.isoformat()
        or acquisition.requested_to != end.isoformat()
    ):
        raise ValueError("acquisition request correspondence mismatch")
    if (
        not acquisition.response_adjusted_is_present
        or acquisition.response_adjusted is not True
    ):
        raise ValueError("response must prove adjusted is exact boolean true")
    if (
        acquisition.response_ticker is not None
        and acquisition.response_ticker != ticker
    ):
        raise ValueError("response ticker mismatch")
    if (
        acquisition.next_page_reference is not None
        and not acquisition.next_page_reference.strip()
    ):
        raise ValueError("empty pagination reference")
    for name in ("query_count", "results_count", "count"):
        value = getattr(acquisition, name)
        if value is not None:
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")
            # queryCount counts underlying aggregates, not returned daily rows.
            if name != "query_count" and value != len(acquisition.rows):
                raise ValueError(f"{name} contradicts returned row count")
