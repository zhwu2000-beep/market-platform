"""Pure governed ingress for Polygon completed-daily OHLCV acquisitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

from market_platform._fingerprint import canonical_fingerprint
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.evidence.authorization import (
    _POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION,
    EvidenceMaterialSchemaReference,
)
from market_platform.evidence.models import (
    EvidenceArtifact,
    EvidenceProvenance,
    EvidenceTemporalIdentity,
)
from market_platform.evidence.polygon_completed_daily_ohlcv import (
    _create_polygon_completed_daily_ohlcv_evidence_artifact,
)
from market_platform.evidence.references import (
    EvidenceIdentityReference,
    EvidenceSourceReference,
    EvidenceSubjectReference,
)
from market_platform.instruments import (
    CANONICAL_INSTRUMENT_SCHEMA_VERSION,
    ExternalInstrumentIdentity,
    InstrumentMapping,
    InstrumentResolution,
    resolve_instrument_mapping,
)

MAX_CANONICAL_NUMERIC_TEXT_LENGTH = 1024

_API_BASE = "https://api.polygon.io"
_ROUTE_TEMPLATE = "/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}"
_MULTIPLIER = 1
_REQUEST_TIMESPAN = "day"
_MATERIAL_TIMESPAN = "1_day"
_ADJUSTED = True
_SORT = "asc"
_LIMIT = 50000
_MARKET_TIMEZONE_NAME = "America/New_York"
_MARKET_TIMEZONE = ZoneInfo(_MARKET_TIMEZONE_NAME)
_SESSION_SCOPE = "polygon_qualifying_trades_all_sessions"
_PRICE_ADJUSTMENT = "split_adjusted_not_dividend_adjusted"
_MATERIAL_SCHEMA_VERSION = "polygon_completed_daily_ohlcv_material/1.0.0"
_REQUEST_PROVENANCE_SCHEMA_VERSION = (
    "polygon_completed_daily_ohlcv_request_provenance/v1"
)
_ARTIFACT_IDENTITY_SCHEMA_VERSION = "polygon_completed_daily_ohlcv_artifact_identity/v1"
_ARTIFACT_VERSION_SCHEMA_VERSION = "polygon_completed_daily_ohlcv_artifact_version/v1"
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_GOVERNED_DEFINITION = _POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION.contract_definition
_GOVERNED_SOURCE = _POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION.authorized_source
_GOVERNED_MATERIAL_SCHEMA = _GOVERNED_DEFINITION.material_schema
_GOVERNING_CONTRACT = _GOVERNED_DEFINITION.governing_contract
_PRODUCER = EvidenceIdentityReference(
    namespace="market_platform.evidence_ingress",
    identity_id="polygon_completed_daily_ohlcv",
    identity_version="1.0.0",
    identity_fingerprint=None,
)


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyOhlcvMaterialRow:
    """One immutable normalized row in the governed material."""

    session_date: str
    open: str
    high: str
    low: str
    close: str
    volume: str

    def to_dict(self) -> dict[str, object]:
        """Return the exact normalized-row projection."""

        return {
            "session_date": self.session_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True, slots=True)
class _PolygonCompletedDailyOhlcvRequestProvenance:
    """Exact immutable request provenance nested in material v1."""

    resolved_route: str
    requested_ticker: str
    requested_from: str
    requested_to: str
    schema_version: str = field(
        init=False,
        default=_REQUEST_PROVENANCE_SCHEMA_VERSION,
    )
    api_base: str = field(init=False, default=_API_BASE)
    multiplier: int = field(init=False, default=_MULTIPLIER)
    timespan: str = field(init=False, default=_REQUEST_TIMESPAN)
    adjusted: bool = field(init=False, default=_ADJUSTED)
    sort: str = field(init=False, default=_SORT)
    limit: int = field(init=False, default=_LIMIT)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "api_base": self.api_base,
            "resolved_route": self.resolved_route,
            "requested_ticker": self.requested_ticker,
            "requested_from": self.requested_from,
            "requested_to": self.requested_to,
            "multiplier": self.multiplier,
            "timespan": self.timespan,
            "adjusted": self.adjusted,
            "sort": self.sort,
            "limit": self.limit,
        }


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyOhlcvMaterial:
    """Immutable canonical ADR0038 material and its fingerprint."""

    external_instrument_identity: ExternalInstrumentIdentity
    canonical_subject: EvidenceSubjectReference
    mapping_resolution_provenance: InstrumentResolution
    start_session_date: str
    end_session_date: str
    query_as_of: datetime
    request_provenance: _PolygonCompletedDailyOhlcvRequestProvenance
    provider_request_id: str | None
    rows: tuple[PolygonCompletedDailyOhlcvMaterialRow, ...]
    schema_version: str = field(init=False, default=_MATERIAL_SCHEMA_VERSION)
    material_schema: EvidenceMaterialSchemaReference = field(
        init=False,
        default=_GOVERNED_MATERIAL_SCHEMA,
    )
    source_reference: EvidenceSourceReference = field(
        init=False,
        default=_GOVERNED_SOURCE,
    )
    vendor_service: str = field(
        init=False,
        default="massive.com_formerly_polygon.io",
    )
    api_base: str = field(init=False, default=_API_BASE)
    route_template: str = field(init=False, default=_ROUTE_TEMPLATE)
    multiplier: int = field(init=False, default=_MULTIPLIER)
    timespan: str = field(init=False, default=_MATERIAL_TIMESPAN)
    adjusted: bool = field(init=False, default=_ADJUSTED)
    sort: str = field(init=False, default=_SORT)
    limit: int = field(init=False, default=_LIMIT)
    market_timezone: str = field(init=False, default=_MARKET_TIMEZONE_NAME)
    session_scope: str = field(init=False, default=_SESSION_SCOPE)
    price_adjustment: str = field(init=False, default=_PRICE_ADJUSTMENT)
    adjusted_response: bool = field(init=False, default=True)
    row_count: int = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_count", len(self.rows))
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "material_schema": self.material_schema.to_dict(),
            "source_reference": self.source_reference.to_dict(),
            "vendor_service": self.vendor_service,
            "api_base": self.api_base,
            "route_template": self.route_template,
            "multiplier": self.multiplier,
            "timespan": self.timespan,
            "adjusted": self.adjusted,
            "sort": self.sort,
            "limit": self.limit,
            "external_instrument_identity": (
                self.external_instrument_identity.to_dict()
            ),
            "canonical_subject": self.canonical_subject.to_dict(),
            "mapping_resolution_provenance": (
                self.mapping_resolution_provenance.to_dict()
            ),
            "start_session_date": self.start_session_date,
            "end_session_date": self.end_session_date,
            "query_as_of": self.query_as_of.isoformat(),
            "market_timezone": self.market_timezone,
            "session_scope": self.session_scope,
            "price_adjustment": self.price_adjustment,
            "adjusted_response": self.adjusted_response,
            "request_provenance": self.request_provenance.to_dict(),
            "provider_request_id": self.provider_request_id,
            "rows": [row.to_dict() for row in self.rows],
            "row_count": self.row_count,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the exact material inspection projection."""

        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyOhlcvEvidenceIngressResult:
    """Canonical material and its governed Candidate Evidence Artifact."""

    material: PolygonCompletedDailyOhlcvMaterial
    artifact: EvidenceArtifact


def create_polygon_completed_daily_ohlcv_evidence(
    *,
    acquisition: PolygonCompletedDailyAcquisition,
    external_identity: ExternalInstrumentIdentity,
    mappings: list[InstrumentMapping] | tuple[InstrumentMapping, ...],
    query_as_of: datetime,
    artifact_created_at: datetime,
) -> PolygonCompletedDailyOhlcvEvidenceIngressResult:
    """Create one governed, unvalidated Candidate from a preserved acquisition."""

    acquisition_rows = _require_canonical_acquisition(acquisition)
    _require_profile_correspondence(acquisition)
    _require_response_correspondence(
        acquisition,
        external_identity,
        raw_row_count=len(acquisition_rows),
    )

    normalized_query_as_of = _normalize_timestamp(query_as_of, "query_as_of")
    normalized_created_at = _normalize_timestamp(
        artifact_created_at,
        "artifact_created_at",
    )
    received_at = acquisition.response_received_at
    if normalized_query_as_of > received_at:
        raise ValueError("query_as_of must not be later than response_received_at")
    if normalized_created_at < received_at:
        raise ValueError(
            "artifact_created_at must not be earlier than response_received_at"
        )

    resolution = resolve_instrument_mapping(
        external_identity,
        mappings,
        normalized_query_as_of,
    )
    if (
        resolution.resolved_as_of != normalized_query_as_of
        or resolution.resolved_as_of.tzinfo is not UTC
    ):
        raise ValueError("instrument resolution does not correspond to query_as_of")

    canonical_instrument = resolution.mapping.canonical_instrument
    subject = EvidenceSubjectReference(
        namespace="canonical_instrument",
        subject_id=canonical_instrument.instrument_id.instrument_id,
        subject_version=CANONICAL_INSTRUMENT_SCHEMA_VERSION,
        subject_fingerprint=canonical_instrument.fingerprint,
    )
    requested_from = _canonical_date(acquisition.requested_from, "requested_from")
    requested_to = _canonical_date(acquisition.requested_to, "requested_to")
    normalized_rows = _normalize_completed_rows(
        acquisition_rows,
        requested_from=requested_from,
        requested_to=requested_to,
        query_as_of=normalized_query_as_of,
    )
    material = PolygonCompletedDailyOhlcvMaterial(
        external_instrument_identity=external_identity,
        canonical_subject=subject,
        mapping_resolution_provenance=resolution,
        start_session_date=acquisition.requested_from,
        end_session_date=acquisition.requested_to,
        query_as_of=normalized_query_as_of,
        request_provenance=_PolygonCompletedDailyOhlcvRequestProvenance(
            resolved_route=acquisition.resolved_route,
            requested_ticker=acquisition.requested_ticker,
            requested_from=acquisition.requested_from,
            requested_to=acquisition.requested_to,
        ),
        provider_request_id=acquisition.request_id,
        rows=normalized_rows,
    )
    temporal_identity = _create_temporal_identity(
        requested_from=requested_from,
        requested_to=requested_to,
        material_fingerprint=material.fingerprint,
        platform_received_at=received_at,
        artifact_created_at=normalized_created_at,
    )
    provenance = EvidenceProvenance(
        origin=_GOVERNED_SOURCE,
        producer=_PRODUCER,
        source_references=(_GOVERNED_SOURCE,),
        transformations=(),
        predecessors=(),
    )
    artifact_id = canonical_fingerprint(
        {
            "schema_version": _ARTIFACT_IDENTITY_SCHEMA_VERSION,
            "governing_contract": _GOVERNING_CONTRACT.to_dict(),
            "canonical_subject_id": canonical_instrument.instrument_id.to_dict(),
            "requested_from": acquisition.requested_from,
            "requested_to": acquisition.requested_to,
        }
    )
    artifact_version = canonical_fingerprint(
        {
            "schema_version": _ARTIFACT_VERSION_SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "material_fingerprint": material.fingerprint,
            "temporal_identity": temporal_identity.to_dict(),
            "provenance": provenance.to_dict(),
        }
    )
    artifact = _create_polygon_completed_daily_ohlcv_evidence_artifact(
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        subjects=(subject,),
        temporal_identity=temporal_identity,
        provenance=provenance,
        material_fingerprint=material.fingerprint,
    )
    return PolygonCompletedDailyOhlcvEvidenceIngressResult(
        material=material,
        artifact=artifact,
    )


def _require_canonical_acquisition(
    acquisition: PolygonCompletedDailyAcquisition,
) -> tuple[PolygonCompletedDailyAggregate, ...]:
    if type(acquisition) is not PolygonCompletedDailyAcquisition:
        raise TypeError("acquisition must be a PolygonCompletedDailyAcquisition")
    rows = acquisition.rows
    exact_rows = _require_exact_acquisition_rows(rows)
    if acquisition.response_received_at.tzinfo is not UTC:
        raise ValueError("acquisition does not retain canonical transport state")
    return exact_rows


def _require_exact_acquisition_rows(
    rows: object,
) -> tuple[PolygonCompletedDailyAggregate, ...]:
    if type(rows) is not tuple:
        raise TypeError("acquisition rows must be an exact tuple")
    untrusted_rows = cast(tuple[object, ...], rows)
    if any(type(row) is not PolygonCompletedDailyAggregate for row in untrusted_rows):
        raise TypeError(
            "acquisition rows must contain exact PolygonCompletedDailyAggregate values"
        )
    return cast(tuple[PolygonCompletedDailyAggregate, ...], untrusted_rows)


def _require_profile_correspondence(
    acquisition: PolygonCompletedDailyAcquisition,
) -> None:
    exact_profile: tuple[tuple[object, type[object], object], ...] = (
        (acquisition.request_base_url, str, _API_BASE),
        (acquisition.multiplier, int, _MULTIPLIER),
        (acquisition.timespan, str, _REQUEST_TIMESPAN),
        (acquisition.adjusted, bool, _ADJUSTED),
        (acquisition.sort, str, _SORT),
        (acquisition.limit, int, _LIMIT),
    )
    if any(
        type(value) is not expected_type or value != expected
        for value, expected_type, expected in exact_profile
    ):
        raise ValueError("acquisition does not match the governed Polygon profile")
    expected_route = (
        f"/v2/aggs/ticker/{quote(acquisition.requested_ticker, safe='')}/range/"
        f"1/day/{acquisition.requested_from}/{acquisition.requested_to}"
    )
    if (
        type(acquisition.resolved_route) is not str
        or acquisition.resolved_route != expected_route
    ):
        raise ValueError(
            "acquisition route does not match the governed Polygon profile"
        )


def _require_response_correspondence(
    acquisition: PolygonCompletedDailyAcquisition,
    external_identity: ExternalInstrumentIdentity,
    *,
    raw_row_count: int,
) -> None:
    if not acquisition.results_is_present:
        raise ValueError("Polygon completed-daily results must be present")
    if acquisition.additional_page_indicated:
        raise ValueError(
            "Polygon completed-daily response indicates an additional page"
        )

    for field_name, is_present, value in (
        ("query_count", acquisition.query_count_is_present, acquisition.query_count),
        (
            "results_count",
            acquisition.results_count_is_present,
            acquisition.results_count,
        ),
        ("count", acquisition.count_is_present, acquisition.count),
    ):
        if is_present and value is not None:
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be an exact nonnegative integer")
            if value != raw_row_count:
                raise ValueError(f"{field_name} does not match the raw row count")

    if type(external_identity) is not ExternalInstrumentIdentity:
        raise TypeError("external_identity must be an ExternalInstrumentIdentity")
    external_identity._validate()
    if (
        external_identity.namespace != "polygon"
        or external_identity.external_symbol != acquisition.requested_ticker
    ):
        raise ValueError(
            "external identity does not match the requested Polygon ticker"
        )
    if (
        acquisition.response_ticker_is_present
        and acquisition.response_ticker is not None
        and acquisition.response_ticker != acquisition.requested_ticker
    ):
        raise ValueError("response ticker does not match the requested Polygon ticker")
    if (
        not acquisition.response_adjusted_is_present
        or acquisition.response_adjusted is not True
    ):
        raise ValueError("response must prove adjusted is exact boolean true")


def _normalize_timestamp(value: datetime, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError(
            f"{field_name} is outside the supported datetime range"
        ) from error


def _canonical_date(value: str, field_name: str) -> date:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an exact YYYY-MM-DD date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be an exact YYYY-MM-DD date")
    return parsed


def _normalize_completed_rows(
    rows: tuple[PolygonCompletedDailyAggregate, ...],
    *,
    requested_from: date,
    requested_to: date,
    query_as_of: datetime,
) -> tuple[PolygonCompletedDailyOhlcvMaterialRow, ...]:
    cutoff_session_date = query_as_of.astimezone(_MARKET_TIMEZONE).date()
    seen_dates: set[date] = set()
    retained: list[
        tuple[
            date,
            int | Decimal,
            int | Decimal,
            int | Decimal,
            int | Decimal,
            int | Decimal,
        ]
    ] = []
    for row in rows:
        (
            timestamp,
            open_value,
            high_value,
            low_value,
            close_value,
            volume_value,
        ) = _snapshot_completed_daily_row(row)
        session_date = _session_date_from_unix_milliseconds(timestamp)
        if session_date < requested_from or session_date > requested_to:
            raise ValueError("Polygon completed-daily row is outside requested bounds")
        if session_date in seen_dates:
            raise ValueError(
                "Polygon completed-daily rows contain a duplicate session date"
            )
        seen_dates.add(session_date)
        if session_date < cutoff_session_date:
            retained.append(
                (
                    session_date,
                    open_value,
                    high_value,
                    low_value,
                    close_value,
                    volume_value,
                )
            )

    retained.sort(key=lambda item: item[0])
    return tuple(
        PolygonCompletedDailyOhlcvMaterialRow(
            session_date=session_date.isoformat(),
            open=_canonical_numeric_text(open_value, "open"),
            high=_canonical_numeric_text(high_value, "high"),
            low=_canonical_numeric_text(low_value, "low"),
            close=_canonical_numeric_text(close_value, "close"),
            volume=_canonical_numeric_text(volume_value, "volume"),
        )
        for (
            session_date,
            open_value,
            high_value,
            low_value,
            close_value,
            volume_value,
        ) in retained
    )


def _snapshot_completed_daily_row(
    row: PolygonCompletedDailyAggregate,
) -> tuple[
    int,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
]:
    if type(row) is not PolygonCompletedDailyAggregate:
        raise TypeError("row must be an exact PolygonCompletedDailyAggregate")
    timestamp = row.timestamp
    open_value = row.open
    high_value = row.high
    low_value = row.low
    close_value = row.close
    volume_value = row.volume
    if type(timestamp) is not int:
        raise TypeError("Polygon completed-daily timestamp must be an exact int")
    return timestamp, open_value, high_value, low_value, close_value, volume_value


def _session_date_from_unix_milliseconds(timestamp: int) -> date:
    whole_seconds, remaining_milliseconds = divmod(timestamp, 1000)
    try:
        source_utc = _UNIX_EPOCH + timedelta(
            seconds=whole_seconds,
            milliseconds=remaining_milliseconds,
        )
        return source_utc.astimezone(_MARKET_TIMEZONE).date()
    except (OverflowError, ValueError) as error:
        raise ValueError(
            "Polygon completed-daily timestamp is outside the supported datetime range"
        ) from error


def _canonical_numeric_text(value: int | Decimal, field_name: str) -> str:
    if type(value) is int:
        decimal_value = Decimal(value)
    elif type(value) is Decimal:
        decimal_value = value
    else:
        raise TypeError(f"{field_name} must be an exact int or Decimal")
    if not decimal_value.is_finite():
        raise ValueError(f"{field_name} must be finite")

    decimal_tuple = decimal_value.as_tuple()
    digits = decimal_tuple.digits
    start = 0
    while start < len(digits) and digits[start] == 0:
        start += 1
    if start == len(digits):
        return "0"

    end = len(digits)
    exponent = cast(int, decimal_tuple.exponent)
    while end > start and digits[end - 1] == 0:
        end -= 1
        exponent += 1

    coefficient_length = end - start
    sign_length = 1 if decimal_tuple.sign else 0
    if exponent >= 0:
        body_length = coefficient_length + exponent
    elif coefficient_length + exponent > 0:
        body_length = coefficient_length + 1
    else:
        body_length = 2 + (-(coefficient_length + exponent)) + coefficient_length
    if sign_length + body_length > MAX_CANONICAL_NUMERIC_TEXT_LENGTH:
        raise ValueError(
            f"{field_name} canonical text exceeds "
            f"{MAX_CANONICAL_NUMERIC_TEXT_LENGTH} characters"
        )

    coefficient = "".join(str(digit) for digit in digits[start:end])
    if exponent >= 0:
        body = coefficient + ("0" * exponent)
    else:
        point = coefficient_length + exponent
        if point > 0:
            body = coefficient[:point] + "." + coefficient[point:]
        else:
            body = "0." + ("0" * (-point)) + coefficient
    return ("-" if decimal_tuple.sign else "") + body


def _create_temporal_identity(
    *,
    requested_from: date,
    requested_to: date,
    material_fingerprint: str,
    platform_received_at: datetime,
    artifact_created_at: datetime,
) -> EvidenceTemporalIdentity:
    try:
        end_date = requested_to + timedelta(days=1)
        observation_start = datetime.combine(
            requested_from,
            time.min,
            tzinfo=_MARKET_TIMEZONE,
        ).astimezone(UTC)
        observation_end = datetime.combine(
            end_date,
            time.min,
            tzinfo=_MARKET_TIMEZONE,
        ).astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError(
            "requested interval is outside the supported datetime range"
        ) from error
    return EvidenceTemporalIdentity(
        observed_at=None,
        observation_period_start=observation_start,
        observation_period_end=observation_end,
        effective_from=None,
        effective_until=None,
        published_at=None,
        source_revision=material_fingerprint,
        platform_received_at=platform_received_at,
        artifact_created_at=artifact_created_at,
    )


__all__ = [
    "MAX_CANONICAL_NUMERIC_TEXT_LENGTH",
    "PolygonCompletedDailyOhlcvEvidenceIngressResult",
    "PolygonCompletedDailyOhlcvMaterial",
    "PolygonCompletedDailyOhlcvMaterialRow",
    "create_polygon_completed_daily_ohlcv_evidence",
]
