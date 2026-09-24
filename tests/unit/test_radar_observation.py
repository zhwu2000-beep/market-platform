import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo

import pandas as pd
import pytest

from market_platform.data.historical import HistoricalPriceSeries
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.observation import (
    RadarMarketContentScope,
    RadarObservationCheckpoint,
    RadarObservationLookupResult,
    RadarObservationLookupStatus,
    RadarObservationStateError,
)

START = date(2026, 9, 21)
END = date(2026, 9, 23)
IDENTITY = "sha256:" + "0123456789abcdef" * 4


def checkpoint() -> RadarObservationCheckpoint:
    return RadarObservationCheckpoint(
        CanonicalInstrumentId("us-msft"),
        END,
        IDENTITY,
        datetime(2026, 9, 24, 1, 2, 3, 456789, tzinfo=UTC),
        RadarMarketContentScope(START, END),
    )


def test_valid_checkpoint_and_deep_immutability() -> None:
    value = checkpoint()
    assert value.instrument == CanonicalInstrumentId("us-msft")
    assert value.normalized_market_content_identity == IDENTITY
    assert value.content_scope.history_end == value.observed_completed_session
    for target, field, replacement in (
        (value, "observed_at", datetime(2026, 1, 1, tzinfo=UTC)),
        (value.content_scope, "history_start", END),
        (value.instrument, "instrument_id", "other"),
        (
            RadarObservationLookupResult(RadarObservationLookupStatus.PRESENT, value),
            "checkpoint",
            None,
        ),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(target, field, replacement)


class MutableZone(tzinfo):
    offset = timedelta(hours=8)

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return self.offset

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)


class NoOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None


class CustomDatetime(datetime):
    pass


def test_utc_normalization_detaches_datetime_and_mutable_timezone() -> None:
    zone = MutableZone()
    supplied = CustomDatetime(2026, 9, 24, 8, 1, 2, 123456, tzinfo=zone)
    value = replace(checkpoint(), observed_at=supplied)
    zone.offset = timedelta(hours=3)
    assert type(value.observed_at) is datetime
    assert value.observed_at.tzinfo is UTC
    assert value.observed_at == datetime(2026, 9, 24, 0, 1, 2, 123456, tzinfo=UTC)


@pytest.mark.parametrize(
    "value",
    [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=NoOffset()), None, "2026-01-01"],
)
def test_rejects_nonaware_observed_at(value: object) -> None:
    with pytest.raises(RadarObservationStateError):
        replace(checkpoint(), observed_at=value)


def test_scope_range_and_correspondence() -> None:
    scope = RadarMarketContentScope(END, END)
    assert RadarMarketContentScope.from_dict(scope.to_dict()) == scope
    assert scope != checkpoint().content_scope
    with pytest.raises(RadarObservationStateError):
        RadarMarketContentScope(END, START)
    with pytest.raises(RadarObservationStateError):
        replace(checkpoint(), observed_completed_session=START)
    # Calendar membership is deliberately not a value-construction dependency.
    sunday = date(2026, 9, 20)
    assert replace(
        checkpoint(),
        observed_completed_session=sunday,
        content_scope=RadarMarketContentScope(sunday, sunday),
    )


@pytest.mark.parametrize("value", ["v2", "", None, 1])
def test_unsupported_schemas(value: object) -> None:
    for target in (checkpoint(), checkpoint().content_scope):
        with pytest.raises(RadarObservationStateError):
            replace(target, schema_version=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("instrument", "us-msft"),
        ("content_scope", {}),
        ("observed_completed_session", datetime(2026, 9, 23)),
        ("observed_completed_session", "2026-09-23"),
    ],
)
def test_wrong_runtime_checkpoint_types(field: str, value: object) -> None:
    with pytest.raises(RadarObservationStateError):
        replace(checkpoint(), **{field: value})


@pytest.mark.parametrize("value", [datetime(2026, 9, 21), "2026-09-21", None])
def test_wrong_runtime_scope_dates(value: object) -> None:
    with pytest.raises(RadarObservationStateError):
        RadarMarketContentScope(value, END)


@pytest.mark.parametrize(
    "value",
    [
        None,
        12,
        "",
        "a" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        IDENTITY + "\n",
        " " + IDENTITY,
    ],
)
def test_malformed_fingerprint(value: object) -> None:
    with pytest.raises(RadarObservationStateError):
        replace(checkpoint(), normalized_market_content_identity=value)


def test_existing_series_identity_stored_unchanged() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["MSFT", "MSFT"],
            "timestamp": [
                datetime(2026, 9, 21, tzinfo=UTC),
                datetime(2026, 9, 23, tzinfo=UTC),
            ],
            "open": [100, 101],
            "high": [103, 103],
            "low": [99, 99],
            "close": [101, 102],
            "volume": [1000, 2000],
            "provider": ["test", "test"],
        }
    )
    identity = HistoricalPriceSeries(frame).content_fingerprint
    value = replace(checkpoint(), normalized_market_content_identity=identity)
    assert value.normalized_market_content_identity == identity
    frame["provider"] = "other"
    assert HistoricalPriceSeries(frame).content_fingerprint == identity
    assert HistoricalPriceSeries(frame.iloc[1:]).content_fingerprint != identity
    frame.loc[0, "close"] = 102
    assert HistoricalPriceSeries(frame).content_fingerprint != identity


def test_passive_deterministic_roundtrip_and_detachment() -> None:
    value = checkpoint()
    raw = value.to_dict()
    encoded = json.dumps(raw)
    assert encoded == json.dumps(value.to_dict())
    assert RadarObservationCheckpoint.from_dict(json.loads(encoded)) == value
    raw["instrument"]["instrument_id"] = "changed"
    raw["content_scope"]["history_start"] = "2000-01-01"
    assert value == checkpoint()
    source = value.to_dict()
    decoded = RadarObservationCheckpoint.from_dict(source)
    source["content_scope"]["history_end"] = "2000-01-01"
    assert decoded == value


def test_decode_aware_offset_normalizes() -> None:
    value = checkpoint()
    raw = value.to_dict()
    raw["observed_at"] = value.observed_at.astimezone(
        timezone(timedelta(hours=8))
    ).isoformat()
    assert RadarObservationCheckpoint.from_dict(raw) == value


@pytest.mark.parametrize("field", list(checkpoint().to_dict()))
def test_missing_checkpoint_field(field: str) -> None:
    raw = checkpoint().to_dict()
    del raw[field]
    with pytest.raises(RadarObservationStateError):
        RadarObservationCheckpoint.from_dict(raw)


@pytest.mark.parametrize(
    "path,value",
    [
        (("extra",), True),
        (("schema_version",), "radar_observation_checkpoint/v2"),
        (("instrument",), "us-msft"),
        (("instrument",), {}),
        (("instrument", "instrument_id"), "bad id"),
        (("instrument", "instrument_id"), None),
        (("instrument", "extra"), 1),
        (("observed_completed_session",), "2026-02-30"),
        (("observed_completed_session",), "20260923"),
        (("observed_completed_session",), "2026-09-22"),
        (("observed_at",), "2026-09-24T01:00:00"),
        (("observed_at",), "invalid"),
        (("observed_at",), None),
        (("normalized_market_content_identity",), "bad"),
        (("content_scope",), None),
        (("content_scope", "schema_version"), "v2"),
        (("content_scope", "history_start"), "2026-09-24"),
        (("content_scope", "history_end"), "invalid"),
        (("content_scope", "extra"), 1),
    ],
)
def test_malformed_persisted_state(path: tuple[str, ...], value: object) -> None:
    raw = checkpoint().to_dict()
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RadarObservationStateError):
        RadarObservationCheckpoint.from_dict(raw)


@pytest.mark.parametrize("value", [None, {}, [], "", {"instrument_id": "x"}])
def test_malformed_root_is_never_absence(value: object) -> None:
    with pytest.raises(RadarObservationStateError):
        RadarObservationCheckpoint.from_dict(value)


@pytest.mark.parametrize("field", ["schema_version", "history_start", "history_end"])
def test_missing_scope_field(field: str) -> None:
    raw = checkpoint().content_scope.to_dict()
    del raw[field]
    with pytest.raises(RadarObservationStateError):
        RadarMarketContentScope.from_dict(raw)


@pytest.mark.parametrize("status", list(RadarObservationLookupStatus))
@pytest.mark.parametrize("present", [True, False])
def test_lookup_invariants(status: RadarObservationLookupStatus, present: bool) -> None:
    value = checkpoint() if present else None
    if present == (status is RadarObservationLookupStatus.PRESENT):
        assert RadarObservationLookupResult(status, value).checkpoint == value
    else:
        with pytest.raises(RadarObservationStateError):
            RadarObservationLookupResult(status, value)


def test_baseline_distinction_and_runtime_lookup_types() -> None:
    absent = RadarObservationLookupResult(RadarObservationLookupStatus.ABSENT)
    unavailable = RadarObservationLookupResult(RadarObservationLookupStatus.UNAVAILABLE)
    assert absent != unavailable
    assert absent.checkpoint is unavailable.checkpoint is None
    with pytest.raises(RadarObservationStateError):
        RadarObservationLookupResult("ABSENT")
    with pytest.raises(RadarObservationStateError):
        RadarObservationLookupResult(RadarObservationLookupStatus.PRESENT, {})
    with pytest.raises(RadarObservationStateError):
        RadarObservationCheckpoint.from_dict(None)
