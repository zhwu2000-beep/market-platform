from __future__ import annotations

import ast
import inspect
import json
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

import market_platform.evidence.authorization as evidence_authorization
import market_platform.evidence_ingress.polygon_completed_daily_ohlcv as ingress
from market_platform._fingerprint import canonical_fingerprint
from market_platform.data.providers.polygon import (
    PolygonCompletedDailyAcquisition,
    PolygonCompletedDailyAggregate,
)
from market_platform.evidence import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence_ingress import (
    MAX_CANONICAL_NUMERIC_TEXT_LENGTH,
    PolygonCompletedDailyOhlcvEvidenceIngressResult,
    create_polygon_completed_daily_ohlcv_evidence,
)
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingAmbiguousError,
    InstrumentMappingConflictError,
    InstrumentMappingInactiveError,
    InstrumentMappingNotFoundError,
    InstrumentMappingSourceIdentity,
)
from market_platform.trading import TradingInstrumentIdentity

_NY = ZoneInfo("America/New_York")
_QUERY = datetime(2026, 8, 24, 10, tzinfo=UTC)
_RECEIVED = datetime(2026, 8, 24, 12, tzinfo=UTC)
_CREATED = datetime(2026, 8, 24, 13, tzinfo=UTC)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _unix_milliseconds(
    session_date: date,
    *,
    hour: int = 12,
    milliseconds: int = 0,
) -> int:
    instant = datetime.combine(
        session_date,
        time(hour=hour, microsecond=milliseconds * 1000),
        tzinfo=_NY,
    ).astimezone(UTC)
    return (instant - _EPOCH) // timedelta(milliseconds=1)


def _row(
    session_date: date = date(2026, 8, 20),
    *,
    timestamp: int | Decimal | None = None,
    open: int | Decimal = Decimal("100.00"),
    high: int | Decimal = Decimal("102.50"),
    low: int | Decimal = 99,
    close: int | Decimal = Decimal("101.2500"),
    volume: int | Decimal = Decimal("1000.5000"),
) -> PolygonCompletedDailyAggregate:
    return PolygonCompletedDailyAggregate(
        timestamp=(
            _unix_milliseconds(session_date) if timestamp is None else timestamp
        ),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _acquisition(
    *,
    rows: tuple[PolygonCompletedDailyAggregate, ...] | None = None,
    requested_ticker: str = "AAPL",
    requested_from: str = "2026-08-20",
    requested_to: str = "2026-08-24",
    response_received_at: datetime = _RECEIVED,
    **changes: object,
) -> PolygonCompletedDailyAcquisition:
    retained_rows = (
        (_row(date(2026, 8, 21)), _row(date(2026, 8, 20))) if rows is None else rows
    )
    row_count = len(retained_rows)
    values: dict[str, object] = {
        "requested_ticker": requested_ticker,
        "requested_from": requested_from,
        "requested_to": requested_to,
        "response_ticker_is_present": True,
        "response_ticker": requested_ticker,
        "response_adjusted_is_present": True,
        "response_adjusted": True,
        "request_id_is_present": True,
        "request_id": "request-123",
        "query_count_is_present": True,
        "query_count": row_count,
        "results_count_is_present": True,
        "results_count": row_count,
        "count_is_present": True,
        "count": row_count,
        "next_url_is_present": False,
        "next_page_reference": None,
        "results_is_present": True,
        "rows": retained_rows,
        "response_received_at": response_received_at,
    }
    values.update(changes)
    return PolygonCompletedDailyAcquisition(**values)  # type: ignore[arg-type]


def _external(symbol: str = "AAPL") -> ExternalInstrumentIdentity:
    return ExternalInstrumentIdentity(namespace="polygon", external_symbol=symbol)


def _canonical(
    symbol: str = "AAPL",
    *,
    instrument_id: str | None = None,
) -> CanonicalInstrument:
    return CanonicalInstrument(
        instrument_id=CanonicalInstrumentId(instrument_id or f"us_equity.{symbol}"),
        trading_identity=TradingInstrumentIdentity(symbol=symbol, venue="NASDAQ"),
        asset_class=InstrumentAssetClass.EQUITY,
        trading_currency="USD",
    )


def _mapping(
    *,
    external: ExternalInstrumentIdentity | None = None,
    canonical: CanonicalInstrument | None = None,
    source_id: str = "test_registry",
    valid_from: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    expires_at: datetime | None = None,
    configuration_fingerprint: str | None = None,
) -> InstrumentMapping:
    return InstrumentMapping(
        external_identity=external or _external(),
        canonical_instrument=canonical or _canonical(),
        source=InstrumentMappingSourceIdentity(
            source_id=source_id,
            source_version="1.0.0",
            configuration_fingerprint=configuration_fingerprint,
        ),
        valid_from=valid_from,
        expires_at=expires_at,
    )


def _create(
    *,
    acquisition: PolygonCompletedDailyAcquisition | None = None,
    external_identity: ExternalInstrumentIdentity | None = None,
    mappings: list[InstrumentMapping] | tuple[InstrumentMapping, ...] | None = None,
    query_as_of: datetime = _QUERY,
    artifact_created_at: datetime = _CREATED,
) -> PolygonCompletedDailyOhlcvEvidenceIngressResult:
    return create_polygon_completed_daily_ohlcv_evidence(
        acquisition=acquisition or _acquisition(),
        external_identity=external_identity or _external(),
        mappings=(_mapping(),) if mappings is None else mappings,
        query_as_of=query_as_of,
        artifact_created_at=artifact_created_at,
    )


def test_top_level_acquisition_duck_type_fails_before_minting() -> None:
    class EqualitySpoofAcquisition:
        def __init__(self) -> None:
            self.equality_calls = 0

        def __eq__(self, other: object) -> bool:
            self.equality_calls += 1
            return True

    spoof = EqualitySpoofAcquisition()
    with (
        patch.object(
            ingress,
            "_create_polygon_completed_daily_ohlcv_evidence_artifact",
        ) as mint,
        pytest.raises(TypeError, match="PolygonCompletedDailyAcquisition"),
    ):
        create_polygon_completed_daily_ohlcv_evidence(
            acquisition=spoof,  # type: ignore[arg-type]
            external_identity=_external(),
            mappings=(_mapping(),),
            query_as_of=_QUERY,
            artifact_created_at=_CREATED,
        )
    mint.assert_not_called()
    assert spoof.equality_calls == 0


@pytest.mark.parametrize(
    "rows",
    (
        [_row()],
        type("AggregateTupleSubclass", (tuple,), {})((_row(),)),
        iter((_row(),)),
    ),
    ids=("list", "tuple_subclass", "arbitrary_iterable"),
)
def test_acquisition_rows_require_exact_builtin_tuple(rows: object) -> None:
    with pytest.raises(TypeError, match="exact tuple"):
        ingress._require_exact_acquisition_rows(rows)


def test_equality_spoof_row_cannot_replace_exact_aggregate() -> None:
    valid = _row()

    class EqualitySpoofRow:
        def __init__(self) -> None:
            self.timestamp = valid.timestamp
            self.open = valid.open
            self.high = valid.high
            self.low = valid.low
            self.close = valid.close
            self.volume = valid.volume
            self.equality_calls = 0

        def __eq__(self, other: object) -> bool:
            self.equality_calls += 1
            return True

    spoof = EqualitySpoofRow()
    with (
        patch.object(
            ingress,
            "_create_polygon_completed_daily_ohlcv_evidence_artifact",
        ) as mint,
        pytest.raises(TypeError, match="exact PolygonCompletedDailyAggregate"),
    ):
        ingress._require_exact_acquisition_rows((spoof,))
    mint.assert_not_called()
    assert spoof.equality_calls == 0


def test_stateful_timestamp_row_is_rejected_without_observing_timestamp() -> None:
    valid_timestamp = _unix_milliseconds(date(2026, 8, 20))

    class StatefulTimestampRow:
        open = 1
        high = 1
        low = 1
        close = 1
        volume = 1

        def __init__(self) -> None:
            self.timestamp_reads = 0

        @property
        def timestamp(self) -> int | float:
            self.timestamp_reads += 1
            if self.timestamp_reads == 1:
                return valid_timestamp
            return float(valid_timestamp)

    spoof = StatefulTimestampRow()
    with (
        patch.object(
            ingress,
            "_create_polygon_completed_daily_ohlcv_evidence_artifact",
        ) as mint,
        pytest.raises(TypeError, match="exact PolygonCompletedDailyAggregate"),
    ):
        ingress._snapshot_completed_daily_row(spoof)  # type: ignore[arg-type]
    mint.assert_not_called()
    assert spoof.timestamp_reads == 0


def test_aggregate_subclass_and_attribute_standin_are_rejected() -> None:
    valid = _row()

    class AggregateSubclass(PolygonCompletedDailyAggregate):
        pass

    subclass = AggregateSubclass(
        timestamp=valid.timestamp,
        open=valid.open,
        high=valid.high,
        low=valid.low,
        close=valid.close,
        volume=valid.volume,
    )
    standin = type(
        "AggregateStandin",
        (),
        {
            "timestamp": valid.timestamp,
            "open": valid.open,
            "high": valid.high,
            "low": valid.low,
            "close": valid.close,
            "volume": valid.volume,
        },
    )()
    assert type(subclass) is not PolygonCompletedDailyAggregate
    assert type(standin) is not PolygonCompletedDailyAggregate
    for value in (subclass, standin):
        with pytest.raises(TypeError, match="exact PolygonCompletedDailyAggregate"):
            ingress._require_exact_acquisition_rows((value,))


def test_row_snapshot_is_read_once_and_same_values_drive_normalization() -> None:
    timestamp = _unix_milliseconds(date(2026, 8, 20))
    open_value = Decimal("100.00")
    high_value = Decimal("102.50")
    low_value = Decimal("99.00")
    close_value = Decimal("101.2500")
    volume_value = Decimal("1000.5000")
    row = _row(
        timestamp=timestamp,
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=volume_value,
    )

    snapshot = ingress._snapshot_completed_daily_row(row)
    assert snapshot[0] == timestamp
    assert snapshot[1] is open_value
    assert snapshot[2] is high_value
    assert snapshot[3] is low_value
    assert snapshot[4] is close_value
    assert snapshot[5] is volume_value

    snapshot_source = inspect.getsource(ingress._snapshot_completed_daily_row)
    normalize_source = inspect.getsource(ingress._normalize_completed_rows)
    for field_name in ("timestamp", "open", "high", "low", "close", "volume"):
        assert snapshot_source.count(f"row.{field_name}") == 1
        assert f"row.{field_name}" not in normalize_source

    original_conversion = ingress._session_date_from_unix_milliseconds
    original_normalization = ingress._canonical_numeric_text
    with (
        patch.object(
            ingress,
            "_session_date_from_unix_milliseconds",
            wraps=original_conversion,
        ) as conversion,
        patch.object(
            ingress,
            "_canonical_numeric_text",
            wraps=original_normalization,
        ) as normalization,
    ):
        normalized = ingress._normalize_completed_rows(
            (row,),
            requested_from=date(2026, 8, 20),
            requested_to=date(2026, 8, 24),
            query_as_of=_QUERY,
        )
    conversion.assert_called_once_with(timestamp)
    assert [item.args for item in normalization.call_args_list] == [
        (open_value, "open"),
        (high_value, "high"),
        (low_value, "low"),
        (close_value, "close"),
        (volume_value, "volume"),
    ]
    assert normalized[0].to_dict() == {
        "session_date": "2026-08-20",
        "open": "100",
        "high": "102.5",
        "low": "99",
        "close": "101.25",
        "volume": "1000.5",
    }


def test_exact_canonical_input_preserves_pre_fix_identity() -> None:
    acquisition = _acquisition()
    assert type(acquisition) is PolygonCompletedDailyAcquisition
    assert type(acquisition.rows) is tuple
    assert all(type(row) is PolygonCompletedDailyAggregate for row in acquisition.rows)

    result = _create(acquisition=acquisition)
    artifact = result.artifact
    assert {
        "material": result.material.fingerprint,
        "artifact_id": artifact.artifact_id,
        "artifact_version": artifact.artifact_version,
        "artifact": artifact.fingerprint,
        "subject": artifact.subjects[0].fingerprint,
        "temporal": artifact.temporal_identity.fingerprint,
        "provenance": artifact.provenance.fingerprint,
        "authorization": artifact.contract_authorization.fingerprint,
    } == {
        "material": (
            "sha256:0ded24c24c72c5ff8d5fbe482c09c96bccc681be486f42e977b6399181a6328a"
        ),
        "artifact_id": (
            "sha256:99fa1da5074000d842f679403091c7a87012f9a06e7ae567191d613388fd93e2"
        ),
        "artifact_version": (
            "sha256:466b62577c86c7d39708e98bf3cde8f70e9946cd67284d14dc5bf68a02c9473b"
        ),
        "artifact": (
            "sha256:79ea6ca7fdcf41d74b008afe8bb463190de6ebe2c79ebc045f243403444e81a2"
        ),
        "subject": (
            "sha256:ba6d88aa70d0f5b59a91722403c6fbbb8304be6daf8861f748d5591f2acdd65d"
        ),
        "temporal": (
            "sha256:7e182bd618601f8dc692f1a183b32b75c4ae3614287c8a339f5c7649cc5ae4a3"
        ),
        "provenance": (
            "sha256:b38b039d948e60db3709b5c6d5955a273a353b884bfb072386a804eab0a45f6c"
        ),
        "authorization": (
            "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
        ),
    }


def test_valid_candidate_uses_exact_trust_root_and_private_minting_path() -> None:
    original_mint = ingress._create_polygon_completed_daily_ohlcv_evidence_artifact
    with patch.object(
        ingress,
        "_create_polygon_completed_daily_ohlcv_evidence_artifact",
        wraps=original_mint,
    ) as mint:
        result = _create()

    mint.assert_called_once()
    artifact = result.artifact
    approved = evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION
    assert artifact.contract_authorization == approved
    assert artifact.authority is EvidenceAuthority.EXTERNAL_ORIGIN
    assert artifact.information_class is EvidenceInformationClass.SOURCE_MEASUREMENT
    assert artifact.evidence_type == "polygon_completed_daily_ohlcv"
    assert artifact.material_schema_version == "1.0.0"
    assert artifact.provenance.origin == approved.authorized_source
    assert not hasattr(result, "acquisition")


def test_public_api_is_narrow_and_result_material_is_immutable() -> None:
    parameters = inspect.signature(
        create_polygon_completed_daily_ohlcv_evidence
    ).parameters
    assert tuple(parameters) == (
        "acquisition",
        "external_identity",
        "mappings",
        "query_as_of",
        "artifact_created_at",
    )
    prohibited = {
        "authorization",
        "catalog",
        "provider",
        "http_client",
        "api_key",
        "producer",
        "artifact_id",
        "artifact_version",
        "subject",
        "provenance",
        "temporal_identity",
        "material_fingerprint",
    }
    assert prohibited.isdisjoint(parameters)
    result = _create()
    assert "__slots__" in type(result).__dict__
    assert "__slots__" in type(result.material).__dict__
    with pytest.raises(FrozenInstanceError):
        result.material.provider_request_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("request_base_url", "https://api.massive.com"),
        ("resolved_route", "/v2/aggs/ticker/AAPL/range/2/day/x/y"),
        ("multiplier", 2),
        ("timespan", "hour"),
        ("adjusted", False),
        ("sort", "desc"),
        ("limit", 49999),
    ),
)
def test_tampered_fixed_profile_fails_closed(field_name: str, value: object) -> None:
    acquisition = _acquisition()
    object.__setattr__(acquisition, field_name, value)

    with pytest.raises(ValueError):
        _create(acquisition=acquisition)


def test_exact_profile_and_resolved_route_are_retained_in_material() -> None:
    material = _create().material.to_dict()
    request = material["request_provenance"]
    assert material["api_base"] == "https://api.polygon.io"
    assert material["multiplier"] == 1
    assert material["timespan"] == "1_day"
    assert material["adjusted"] is True
    assert material["sort"] == "asc"
    assert material["limit"] == 50000
    assert isinstance(request, dict)
    assert request == {
        "schema_version": "polygon_completed_daily_ohlcv_request_provenance/v1",
        "api_base": "https://api.polygon.io",
        "resolved_route": ("/v2/aggs/ticker/AAPL/range/1/day/2026-08-20/2026-08-24"),
        "requested_ticker": "AAPL",
        "requested_from": "2026-08-20",
        "requested_to": "2026-08-24",
        "multiplier": 1,
        "timespan": "day",
        "adjusted": True,
        "sort": "asc",
        "limit": 50000,
    }


@pytest.mark.parametrize(
    ("changes", "succeeds"),
    (
        (
            {"response_ticker_is_present": False, "response_ticker": None},
            True,
        ),
        (
            {"response_ticker_is_present": True, "response_ticker": None},
            True,
        ),
        (
            {"response_ticker_is_present": True, "response_ticker": "AAPL"},
            True,
        ),
        (
            {"response_ticker_is_present": True, "response_ticker": "aapl"},
            False,
        ),
        (
            {"response_ticker_is_present": True, "response_ticker": "MSFT"},
            False,
        ),
    ),
)
def test_response_ticker_correspondence(
    changes: dict[str, object], succeeds: bool
) -> None:
    acquisition = _acquisition(**changes)
    if succeeds:
        _create(acquisition=acquisition)
    else:
        with pytest.raises(ValueError, match="response ticker"):
            _create(acquisition=acquisition)


def test_external_identity_correspondence_is_exact_and_case_sensitive() -> None:
    _create(external_identity=_external("AAPL"))
    with pytest.raises(ValueError, match="external identity"):
        _create(external_identity=_external("aapl"))
    with pytest.raises(ValueError, match="external identity"):
        _create(
            external_identity=ExternalInstrumentIdentity(
                namespace="other", external_symbol="AAPL"
            )
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"response_adjusted_is_present": False, "response_adjusted": None},
        {"response_adjusted_is_present": True, "response_adjusted": None},
        {"response_adjusted_is_present": True, "response_adjusted": False},
    ),
)
def test_response_adjusted_must_be_present_exact_true(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="adjusted"):
        _create(acquisition=_acquisition(**changes))


def test_malformed_response_adjusted_fails_closed() -> None:
    acquisition = _acquisition()
    object.__setattr__(acquisition, "response_adjusted", 1)
    with pytest.raises(ValueError, match="adjusted"):
        _create(acquisition=acquisition)


def test_results_absent_fails_but_present_empty_mints_zero_row_candidate() -> None:
    absent = _acquisition(
        rows=(),
        results_is_present=False,
        query_count=0,
        results_count=0,
        count=0,
    )
    with pytest.raises(ValueError, match="results must be present"):
        _create(acquisition=absent)

    result = _create(acquisition=_acquisition(rows=()))
    assert result.material.rows == ()
    assert result.material.row_count == 0
    rendered = json.dumps(result.artifact.to_dict(), sort_keys=True).lower()
    assert "admission" not in rendered
    assert "consumable" not in rendered
    assert "freshness" not in rendered


def test_pagination_absent_and_present_null_pass_without_affecting_identity() -> None:
    absent = _create(
        acquisition=_acquisition(
            next_url_is_present=False,
            next_page_reference=None,
        )
    )
    present_null = _create(
        acquisition=_acquisition(
            next_url_is_present=True,
            next_page_reference=None,
        )
    )
    assert absent.material.to_dict() == present_null.material.to_dict()
    assert absent.artifact.fingerprint == present_null.artifact.fingerprint


def test_non_null_continuation_fails_without_echo_or_network_action() -> None:
    reference = "https://api.polygon.io/v2/aggs?cursor=cursor-secret"
    acquisition = _acquisition(
        next_url_is_present=True,
        next_page_reference=reference,
    )
    with pytest.raises(ValueError, match="additional page") as captured:
        _create(acquisition=acquisition)
    assert "cursor-secret" not in str(captured.value)


@pytest.mark.parametrize(
    ("is_present", "value"),
    ((False, None), (True, None), (True, 2)),
)
@pytest.mark.parametrize(
    ("presence_field", "value_field"),
    (
        ("query_count_is_present", "query_count"),
        ("results_count_is_present", "results_count"),
        ("count_is_present", "count"),
    ),
)
def test_optional_counts_absent_null_or_consistent_pass(
    presence_field: str,
    value_field: str,
    is_present: bool,
    value: int | None,
) -> None:
    _create(
        acquisition=_acquisition(**{presence_field: is_present, value_field: value})
    )


@pytest.mark.parametrize("value", (-1, 0, 3))
def test_count_negative_or_raw_row_mismatch_fails(value: int) -> None:
    with pytest.raises(ValueError, match="query_count"):
        _create(acquisition=_acquisition(query_count=value))


def test_cross_field_count_contradiction_fails_before_completion_filtering() -> None:
    current_row = _row(date(2026, 8, 24))
    acquisition = _acquisition(
        rows=(current_row,),
        query_count=0,
        results_count=1,
        count=1,
    )
    with pytest.raises(ValueError, match="raw row count"):
        _create(acquisition=acquisition)


def test_counts_are_construction_only_and_do_not_change_identity() -> None:
    known = _create()
    unknown = _create(
        acquisition=_acquisition(
            query_count_is_present=False,
            query_count=None,
            results_count_is_present=True,
            results_count=None,
            count_is_present=False,
            count=None,
        )
    )
    assert known.material.to_dict() == unknown.material.to_dict()
    assert known.artifact.fingerprint == unknown.artifact.fingerprint


def test_resolution_receives_exact_normalized_query_as_of() -> None:
    local_query = datetime(
        2026,
        8,
        24,
        18,
        tzinfo=timezone(timedelta(hours=8)),
    )
    original_resolver = ingress.resolve_instrument_mapping
    with patch.object(
        ingress,
        "resolve_instrument_mapping",
        wraps=original_resolver,
    ) as resolver:
        result = _create(query_as_of=local_query)
    resolver.assert_called_once_with(_external(), (_mapping(),), _QUERY)
    assert result.material.query_as_of == _QUERY
    assert result.material.mapping_resolution_provenance.resolved_as_of == _QUERY


def test_resolution_not_found_and_inactive_outcomes_propagate() -> None:
    with pytest.raises(InstrumentMappingNotFoundError):
        _create(mappings=[])
    with pytest.raises(InstrumentMappingInactiveError):
        _create(mappings=(_mapping(valid_from=_CREATED),))


def test_resolution_ambiguous_and_conflict_outcomes_propagate() -> None:
    ambiguous = (
        _mapping(source_id="registry_a"),
        _mapping(source_id="registry_b"),
    )
    with pytest.raises(InstrumentMappingAmbiguousError):
        _create(mappings=ambiguous)

    conflict = (
        _mapping(source_id="registry_a"),
        _mapping(
            source_id="registry_b",
            canonical=_canonical("MSFT"),
        ),
    )
    with pytest.raises(InstrumentMappingConflictError):
        _create(mappings=conflict)


@pytest.mark.parametrize(
    ("query_as_of", "created_at", "message"),
    (
        (datetime(2026, 8, 24), _CREATED, "query_as_of"),
        (_QUERY, datetime(2026, 8, 24), "artifact_created_at"),
        (_RECEIVED + timedelta(microseconds=1), _CREATED, "query_as_of"),
        (_QUERY, _RECEIVED - timedelta(microseconds=1), "artifact_created_at"),
    ),
)
def test_query_receipt_creation_ordering_fails_closed(
    query_as_of: datetime,
    created_at: datetime,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _create(query_as_of=query_as_of, artifact_created_at=created_at)


def test_non_utc_inputs_normalize_and_equal_time_boundaries_are_permitted() -> None:
    result = _create(
        query_as_of=datetime(
            2026,
            8,
            24,
            20,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        artifact_created_at=datetime(
            2026,
            8,
            24,
            20,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    )
    assert result.material.query_as_of == _RECEIVED
    assert result.artifact.temporal_identity.platform_received_at == _RECEIVED
    assert result.artifact.temporal_identity.artifact_created_at == _RECEIVED


@pytest.mark.parametrize(
    "timestamp",
    (Decimal("1787241600000"), 1.0, True, "1787241600000", None),
)
def test_timestamp_requires_exact_runtime_int(timestamp: object) -> None:
    row = _row()
    object.__setattr__(row, "timestamp", timestamp)
    acquisition = _acquisition(rows=(row,))
    with pytest.raises((TypeError, ValueError)):
        _create(acquisition=acquisition)


def test_timestamp_outside_datetime_range_fails_without_float_normalization() -> None:
    row = _row()
    object.__setattr__(row, "timestamp", 10**100)
    with pytest.raises(ValueError, match="datetime range"):
        _create(acquisition=_acquisition(rows=(row,)))


def test_exact_integer_milliseconds_derive_new_york_session_date() -> None:
    timestamp = _unix_milliseconds(date(2026, 8, 20), milliseconds=999)
    result = _create(acquisition=_acquisition(rows=(_row(timestamp=timestamp),)))
    assert result.material.rows[0].session_date == "2026-08-20"


def test_completion_filters_current_and_future_but_retains_prior_date() -> None:
    rows = (
        _row(date(2026, 8, 25)),
        _row(date(2026, 8, 24)),
        _row(date(2026, 8, 23)),
    )
    result = _create(
        acquisition=_acquisition(
            rows=rows,
            requested_from="2026-08-23",
            requested_to="2026-08-25",
        )
    )
    assert tuple(row.session_date for row in result.material.rows) == ("2026-08-23",)


def test_out_of_bounds_row_fails_even_when_completion_would_filter_it() -> None:
    acquisition = _acquisition(
        rows=(_row(date(2026, 8, 25)),),
        requested_to="2026-08-24",
    )
    with pytest.raises(ValueError, match="outside requested bounds"):
        _create(acquisition=acquisition)


def test_duplicate_session_date_fails_even_when_rows_would_be_filtered() -> None:
    first = _row(date(2026, 8, 24))
    second = _row(
        date(2026, 8, 24),
        timestamp=_unix_milliseconds(date(2026, 8, 24), hour=13),
    )
    with pytest.raises(ValueError, match="duplicate session date"):
        _create(acquisition=_acquisition(rows=(first, second)))


def test_weekend_is_not_rejected_and_retained_rows_are_sorted() -> None:
    assert date(2026, 8, 22).weekday() == 5
    rows = (
        _row(date(2026, 8, 23)),
        _row(date(2026, 8, 20)),
        _row(date(2026, 8, 22)),
    )
    result = _create(acquisition=_acquisition(rows=rows))
    assert tuple(row.session_date for row in result.material.rows) == (
        "2026-08-20",
        "2026-08-22",
        "2026-08-23",
    )


@pytest.mark.parametrize(
    ("requested_from", "requested_to", "query", "received", "start", "end"),
    (
        (
            "2026-03-07",
            "2026-03-08",
            datetime(2026, 3, 9, tzinfo=UTC),
            datetime(2026, 3, 9, 1, tzinfo=UTC),
            datetime(2026, 3, 7, 5, tzinfo=UTC),
            datetime(2026, 3, 9, 4, tzinfo=UTC),
        ),
        (
            "2026-10-31",
            "2026-11-01",
            datetime(2026, 11, 2, tzinfo=UTC),
            datetime(2026, 11, 2, 1, tzinfo=UTC),
            datetime(2026, 10, 31, 4, tzinfo=UTC),
            datetime(2026, 11, 2, 5, tzinfo=UTC),
        ),
    ),
)
def test_observation_interval_is_half_open_and_dst_aware(
    requested_from: str,
    requested_to: str,
    query: datetime,
    received: datetime,
    start: datetime,
    end: datetime,
) -> None:
    acquisition = _acquisition(
        rows=(),
        requested_from=requested_from,
        requested_to=requested_to,
        response_received_at=received,
    )
    result = _create(
        acquisition=acquisition,
        query_as_of=query,
        artifact_created_at=received,
    )
    temporal = result.artifact.temporal_identity
    assert temporal.observation_period_start == start
    assert temporal.observation_period_end == end
    assert temporal.observation_period_end > temporal.observation_period_start


def test_requested_to_plus_one_day_overflow_fails_closed() -> None:
    instant = datetime(9999, 12, 31, 12, tzinfo=UTC)
    acquisition = _acquisition(
        rows=(),
        requested_from="9999-12-31",
        requested_to="9999-12-31",
        response_received_at=instant,
    )
    with pytest.raises(ValueError, match="requested interval"):
        _create(
            acquisition=acquisition,
            query_as_of=instant,
            artifact_created_at=instant,
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (1, "1"),
        (Decimal("1.0"), "1"),
        (Decimal("1.000"), "1"),
        (Decimal("123E-2"), "1.23"),
        (Decimal("1.2300"), "1.23"),
        (Decimal("-0.000"), "0"),
        (Decimal("1E-3"), "0.001"),
        (Decimal("1E+3"), "1000"),
        (
            Decimal("123456789012345678901234567890.123456789"),
            "123456789012345678901234567890.123456789",
        ),
    ),
)
def test_decimal_tuple_canonicalization(value: int | Decimal, expected: str) -> None:
    assert ingress._canonical_numeric_text(value, "open") == expected


def test_decimal_canonicalization_is_context_independent() -> None:
    outputs: list[str] = []
    for precision in (1, 7, 50):
        with localcontext() as context:
            context.prec = precision
            outputs.append(
                ingress._canonical_numeric_text(
                    Decimal("123456789.123450000"),
                    "close",
                )
            )
    assert outputs == ["123456789.12345"] * 3


def test_numeric_resource_gate_allows_1024_and_rejects_1025() -> None:
    permitted = ingress._canonical_numeric_text(Decimal("1E+1023"), "volume")
    assert len(permitted) == MAX_CANONICAL_NUMERIC_TEXT_LENGTH
    with pytest.raises(ValueError, match="1024"):
        ingress._canonical_numeric_text(Decimal("1E+1024"), "volume")
    with pytest.raises(ValueError, match="1024"):
        ingress._canonical_numeric_text(Decimal("1E-1023"), "volume")


@pytest.mark.parametrize("value", (Decimal("1E+1000000000"), Decimal("1E-1000000000")))
def test_extreme_exponents_fail_before_padding_allocation(value: Decimal) -> None:
    with pytest.raises(ValueError, match="1024"):
        ingress._canonical_numeric_text(value, "open")


def test_numeric_helper_has_no_context_sensitive_or_float_operations() -> None:
    source = inspect.getsource(ingress._canonical_numeric_text)
    for forbidden in (".normalize(", ".quantize(", "float(", "format("):
        assert forbidden not in source


def test_material_projection_is_exact_and_fingerprint_recomputes() -> None:
    result = _create()
    material = result.material
    projection = material.to_dict()
    fingerprint = projection.pop("fingerprint")
    assert set(projection) == {
        "schema_version",
        "material_schema",
        "source_reference",
        "vendor_service",
        "api_base",
        "route_template",
        "multiplier",
        "timespan",
        "adjusted",
        "sort",
        "limit",
        "external_instrument_identity",
        "canonical_subject",
        "mapping_resolution_provenance",
        "start_session_date",
        "end_session_date",
        "query_as_of",
        "market_timezone",
        "session_scope",
        "price_adjustment",
        "adjusted_response",
        "request_provenance",
        "provider_request_id",
        "rows",
        "row_count",
    }
    assert projection["schema_version"] == (
        "polygon_completed_daily_ohlcv_material/1.0.0"
    )
    assert projection["material_schema"] == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_MATERIAL_SCHEMA.to_dict()
    )
    assert projection["source_reference"] == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_SOURCE.to_dict()
    )
    assert projection["rows"] == [
        {
            "session_date": "2026-08-20",
            "open": "100",
            "high": "102.5",
            "low": "99",
            "close": "101.25",
            "volume": "1000.5",
        },
        {
            "session_date": "2026-08-21",
            "open": "100",
            "high": "102.5",
            "low": "99",
            "close": "101.25",
            "volume": "1000.5",
        },
    ]
    assert projection["row_count"] == 2
    assert fingerprint == material.fingerprint == canonical_fingerprint(projection)


def test_request_id_null_rules_and_identity_sensitivity() -> None:
    absent = _create(
        acquisition=_acquisition(
            request_id_is_present=False,
            request_id=None,
        )
    )
    present_null = _create(
        acquisition=_acquisition(
            request_id_is_present=True,
            request_id=None,
        )
    )
    changed = _create(acquisition=_acquisition(request_id="request-other"))
    assert absent.material.to_dict() == present_null.material.to_dict()
    assert absent.material.provider_request_id is None
    assert changed.material.fingerprint != absent.material.fingerprint
    assert changed.artifact.artifact_id == absent.artifact.artifact_id
    assert changed.artifact.artifact_version != absent.artifact.artifact_version


def test_response_ticker_availability_does_not_change_identity() -> None:
    absent = _create(
        acquisition=_acquisition(
            response_ticker_is_present=False,
            response_ticker=None,
        )
    )
    present = _create()
    assert absent.material.to_dict() == present.material.to_dict()
    assert absent.artifact.fingerprint == present.artifact.fingerprint


def test_subject_and_producer_are_exact_and_fingerprints_recompute() -> None:
    artifact = _create().artifact
    canonical = _canonical()
    subject = artifact.subjects[0]
    assert subject.namespace == "canonical_instrument"
    assert subject.subject_id == canonical.instrument_id.instrument_id
    assert subject.subject_version == "canonical_instrument/v1"
    assert subject.subject_fingerprint == canonical.fingerprint
    assert subject.fingerprint == canonical_fingerprint(
        {key: value for key, value in subject.to_dict().items() if key != "fingerprint"}
    )
    producer = artifact.provenance.producer
    assert producer.to_dict() == {
        "schema_version": "evidence_identity_reference/v1",
        "namespace": "market_platform.evidence_ingress",
        "identity_id": "polygon_completed_daily_ohlcv",
        "identity_version": "1.0.0",
        "identity_fingerprint": None,
        "fingerprint": (
            "sha256:16c2e69b6bd2727c020169f6828f3f40c354c53d96f079962419ae20d1770fcd"
        ),
    }
    assert artifact.provenance.source_references == (artifact.provenance.origin,)
    assert artifact.provenance.transformations == ()
    assert artifact.provenance.predecessors == ()


def test_temporal_identity_keeps_all_times_distinct_and_exact() -> None:
    result = _create()
    temporal = result.artifact.temporal_identity
    assert temporal.observed_at is None
    assert temporal.effective_from is None
    assert temporal.effective_until is None
    assert temporal.published_at is None
    assert temporal.source_revision == result.material.fingerprint
    assert temporal.platform_received_at == _RECEIVED
    assert temporal.artifact_created_at == _CREATED
    assert result.material.query_as_of == _QUERY


def test_artifact_id_projection_recomputes_exactly() -> None:
    result = _create()
    artifact = result.artifact
    expected = canonical_fingerprint(
        {
            "schema_version": ("polygon_completed_daily_ohlcv_artifact_identity/v1"),
            "governing_contract": artifact.governing_contract.to_dict(),
            "canonical_subject_id": {"instrument_id": "us_equity.AAPL"},
            "requested_from": "2026-08-20",
            "requested_to": "2026-08-24",
        }
    )
    assert artifact.artifact_id == expected


def test_artifact_id_stability_and_bound_sensitivity() -> None:
    baseline = _create()
    corrected = _create(
        acquisition=_acquisition(
            rows=(
                _row(date(2026, 8, 20), close=Decimal("101.26")),
                _row(date(2026, 8, 21)),
            )
        )
    )
    later_query = _create(query_as_of=_QUERY + timedelta(hours=1))
    wider_bounds = _create(acquisition=_acquisition(requested_to="2026-08-25"))
    assert baseline.artifact.artifact_id == corrected.artifact.artifact_id
    assert baseline.artifact.artifact_id == later_query.artifact.artifact_id
    assert baseline.artifact.artifact_id != wider_bounds.artifact.artifact_id
    assert baseline.material.fingerprint != corrected.material.fingerprint


def test_query_changes_artifact_id_only_when_canonical_subject_changes() -> None:
    boundary = datetime(2026, 8, 24, 11, tzinfo=UTC)
    first = _mapping(expires_at=boundary, source_id="registry_first")
    second = _mapping(
        canonical=_canonical("MSFT", instrument_id="us_equity.MSFT"),
        valid_from=boundary,
        source_id="registry_second",
    )
    before = _create(mappings=(first, second), query_as_of=_QUERY)
    after = _create(mappings=(first, second), query_as_of=boundary)
    assert before.artifact.artifact_id != after.artifact.artifact_id


def test_artifact_version_projection_recomputes_exactly() -> None:
    result = _create()
    artifact = result.artifact
    expected = canonical_fingerprint(
        {
            "schema_version": ("polygon_completed_daily_ohlcv_artifact_version/v1"),
            "artifact_id": artifact.artifact_id,
            "material_fingerprint": result.material.fingerprint,
            "temporal_identity": artifact.temporal_identity.to_dict(),
            "provenance": artifact.provenance.to_dict(),
        }
    )
    assert artifact.artifact_version == expected


def test_artifact_version_changes_with_material_receipt_creation_and_mapping() -> None:
    baseline = _create()
    changed_material = _create(acquisition=_acquisition(request_id="different-request"))
    changed_receipt = _create(
        acquisition=_acquisition(response_received_at=_RECEIVED + timedelta(minutes=1))
    )
    changed_creation = _create(artifact_created_at=_CREATED + timedelta(minutes=1))
    changed_mapping = _create(
        mappings=(
            _mapping(
                configuration_fingerprint=canonical_fingerprint(
                    {"schema_version": "mapping_config/v1", "revision": 2}
                )
            ),
        )
    )
    variants = (
        changed_material,
        changed_receipt,
        changed_creation,
        changed_mapping,
    )
    assert all(
        item.artifact.artifact_version != baseline.artifact.artifact_version
        for item in variants
    )
    assert changed_receipt.material.fingerprint == baseline.material.fingerprint
    assert changed_creation.material.fingerprint == baseline.material.fingerprint
    assert changed_mapping.artifact.artifact_id == baseline.artifact.artifact_id


def test_equivalent_decimal_spellings_have_identical_evidence_identity() -> None:
    integer = _create(
        acquisition=_acquisition(rows=(_row(open=1, high=1, low=1, close=1, volume=1),))
    )
    decimal = _create(
        acquisition=_acquisition(
            rows=(
                _row(
                    open=Decimal("1.0"),
                    high=Decimal("1.000"),
                    low=Decimal("1E+0"),
                    close=Decimal("100E-2"),
                    volume=Decimal("1.0000"),
                ),
            )
        )
    )
    assert integer.material.to_dict() == decimal.material.to_dict()
    assert integer.artifact.fingerprint == decimal.artifact.fingerprint


def test_final_artifact_fingerprint_recomputes_and_no_lifecycle_is_manufactured() -> (
    None
):
    artifact = _create().artifact
    projection = artifact.to_dict()
    fingerprint = projection.pop("fingerprint")
    assert fingerprint == canonical_fingerprint(projection)
    assert artifact.contract_authorization == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION
    )
    forbidden_attributes = (
        "validation",
        "admission",
        "validity",
        "freshness",
        "consumability",
        "status",
    )
    assert all(not hasattr(artifact, name) for name in forbidden_attributes)


def test_deterministic_replay_is_byte_equivalent() -> None:
    first = _create()
    second = _create()
    first_bytes = json.dumps(
        first.material.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    second_bytes = json.dumps(
        second.material.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert first_bytes == second_bytes
    assert first.artifact.artifact_id == second.artifact.artifact_id
    assert first.artifact.artifact_version == second.artifact.artifact_version
    assert first.artifact.fingerprint == second.artifact.fingerprint


def test_dependency_direction_and_no_network_or_alternate_minting_path() -> None:
    ingress_path = Path(
        "src/market_platform/evidence_ingress/polygon_completed_daily_ohlcv.py"
    )
    ingress_source = ingress_path.read_text(encoding="utf-8")
    ingress_tree = ast.parse(ingress_source)
    imported_names = {
        alias.name
        for node in ast.walk(ingress_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "PolygonProvider" not in imported_names
    assert "HTTPClient" not in imported_names
    assert "_create_evidence_artifact" not in imported_names
    assert "_GOVERNED_EVIDENCE_AUTHORIZATION_CATALOG" not in ingress_source
    assert "datetime.now" not in ingress_source
    assert "evaluate_evidence_admission_as_of" not in ingress_source
    assert (
        ingress_source.count("_create_polygon_completed_daily_ohlcv_evidence_artifact(")
        == 1
    )
    for forbidden in (
        "StrategyEvidence",
        "DailyResearchEvidence",
        "CompletedDailyPriceSeries",
        "HistoricalPriceSeries",
        "DailyInstrumentIntegrityEvidence",
        "pandas",
        "DataFrame",
    ):
        assert forbidden not in ingress_source

    polygon_source = Path("src/market_platform/data/providers/polygon.py").read_text(
        encoding="utf-8"
    )
    assert "market_platform.evidence" not in polygon_source
    for evidence_path in Path("src/market_platform/evidence").glob("*.py"):
        assert "evidence_ingress" not in evidence_path.read_text(encoding="utf-8")
    assert "evidence_ingress" not in Path(
        "src/market_platform/evidence/__init__.py"
    ).read_text(encoding="utf-8")
    assert "evidence_ingress" not in Path("src/market_platform/__init__.py").read_text(
        encoding="utf-8"
    )
    assert "PolygonCompletedDailyAcquisition" not in Path(
        "src/market_platform/data/provider.py"
    ).read_text(encoding="utf-8")


def test_normalized_rows_contain_exactly_six_frozen_fields() -> None:
    row = _create().material.rows[0]
    assert tuple(item.name for item in fields(row)) == (
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    assert set(row.to_dict()) == {
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    with pytest.raises(FrozenInstanceError):
        row.close = "0"  # type: ignore[misc]
