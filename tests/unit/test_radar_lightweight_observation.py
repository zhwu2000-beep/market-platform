"""Pure observation contracts; no provider or persistence."""

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import Mock, call

import pandas as pd
import pytest

from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.models import PRICE_COLUMNS
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar import lightweight_observation as subject
from market_platform.radar.current_content import RadarCompletedDailyHistory
from market_platform.radar.ema_relation import EMA8_EMA20_RELATION_KEY, RadarEmaRelation
from market_platform.radar.lightweight_observation import RadarLightweightObservation
from market_platform.radar.observation import RadarMarketContentScope


def observation():
    session = date(2026, 9, 23)
    return RadarLightweightObservation(
        CanonicalInstrumentId("test"),
        subject.EMA8_EMA20_OBSERVATION_DEFINITION_ID,
        subject.EMA8_EMA20_CALCULATION_REVISION,
        subject.EMA8_EMA20_OBSERVATION_SCHEMA,
        session,
        "sha256:" + "a" * 64,
        RadarMarketContentScope(date(2025, 10, 1), session),
        RadarEmaRelation.ABOVE,
        datetime(2026, 9, 24, tzinfo=UTC),
    )


def test_identity_and_enum_compatibility():
    assert (
        subject.EMA8_EMA20_OBSERVATION_DEFINITION_ID
        == "ema8_ema20_relation_observation"
    )
    assert subject.EMA8_EMA20_CALCULATION_REVISION == "1"
    assert subject.EMA8_EMA20_OBSERVATION_SCHEMA == "radar_ema8_ema20_observation/v1"
    assert EMA8_EMA20_RELATION_KEY.gate_id == "ema8_ema20_relation"
    assert EMA8_EMA20_RELATION_KEY.behavioral_revision == "1"
    assert EMA8_EMA20_RELATION_KEY.configuration_schema == "ema8_ema20_relation/v1"
    assert RadarEmaRelation is subject.RadarEmaRelation
    assert tuple(RadarEmaRelation) == (
        RadarEmaRelation.ABOVE,
        RadarEmaRelation.EQUAL,
        RadarEmaRelation.BELOW,
    )


def test_frozen_slots_and_field_boundary():
    value = observation()
    assert not hasattr(value, "__dict__")
    assert {f.name for f in fields(value)} == {
        "instrument",
        "definition_id",
        "calculation_revision",
        "observation_schema",
        "completed_session",
        "normalized_market_content_identity",
        "content_scope",
        "relation",
        "as_of",
    }
    with pytest.raises(FrozenInstanceError):
        value.relation = RadarEmaRelation.BELOW


@pytest.mark.parametrize(
    "field,value",
    [
        ("instrument", "test"),
        ("definition_id", 1),
        ("calculation_revision", True),
        ("observation_schema", None),
        ("completed_session", datetime(2026, 9, 23)),
        ("content_scope", {}),
        ("relation", "ABOVE"),
        ("as_of", "2026-09-24"),
        ("normalized_market_content_identity", 1),
    ],
)
def test_strict_types(field, value):
    with pytest.raises(TypeError):
        replace(observation(), **{field: value})


@pytest.mark.parametrize(
    "field", ["definition_id", "calculation_revision", "observation_schema"]
)
@pytest.mark.parametrize("value", ["", " ", "bad identity", "x" * 129, "é", "x\n"])
def test_bounded_identity(field, value):
    with pytest.raises(ValueError):
        replace(observation(), **{field: value})


@pytest.mark.parametrize(
    "identity",
    ["sha256:" + "A" * 64, "a" * 64, "sha256:" + "a" * 63, "sha256:" + "g" * 64],
)
def test_content_identity(identity):
    with pytest.raises(ValueError):
        replace(observation(), normalized_market_content_identity=identity)


def test_scope_correspondence_and_naive_time():
    with pytest.raises(ValueError):
        replace(observation(), completed_session=date(2026, 9, 22))
    with pytest.raises(ValueError):
        replace(observation(), as_of=datetime(2026, 9, 24))


def test_utc_detaches_datetime_subclass():
    class CallerDatetime(datetime):
        pass

    supplied = CallerDatetime(2026, 9, 24, 8, tzinfo=timezone(timedelta(hours=8)))
    value = replace(observation(), as_of=supplied)
    assert type(value.as_of) is datetime
    assert value.as_of.tzinfo is UTC
    assert value.as_of == datetime(2026, 9, 24, tzinfo=UTC)
    assert value.as_of is not supplied


def test_passive_roundtrip_and_detachment():
    value = observation()
    raw = value.to_dict()
    assert json.dumps(raw) == json.dumps(value.to_dict())
    assert RadarLightweightObservation.from_dict(json.loads(json.dumps(raw))) == value
    raw["instrument"]["instrument_id"] = "other"
    raw["content_scope"]["history_start"] = "2000-01-01"
    assert value == observation()


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra", True),
        ("completed_session", "20260923"),
        ("relation", "UNKNOWN"),
        ("as_of", None),
        ("instrument", {"instrument_id": "bad/path"}),
        (
            "content_scope",
            {
                "schema_version": "future",
                "history_start": "2025-10-01",
                "history_end": "2026-09-23",
            },
        ),
    ],
)
def test_bad_decode(field, value):
    raw = observation().to_dict()
    raw[field] = value
    with pytest.raises((ValueError, TypeError)):
        RadarLightweightObservation.from_dict(raw)


@pytest.mark.parametrize(
    "relation,closes",
    [
        (RadarEmaRelation.ABOVE, tuple(100 + i for i in range(250))),
        (RadarEmaRelation.EQUAL, (128,) * 250),
        (RadarEmaRelation.BELOW, tuple(350 - i for i in range(250))),
    ],
)
def test_calculator_and_current_producer(monkeypatch, relation, closes):
    # Deliberately no calendar claim: structural history alone does not prove it.
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        ("TEST", start + timedelta(days=i), close, close, close, close, 100, "fixture")
        for i, close in enumerate(closes)
    ]
    series = HistoricalPriceSeries(pd.DataFrame(rows, columns=PRICE_COLUMNS))
    end = rows[-1][1].date()
    history = RadarCompletedDailyHistory(
        CanonicalInstrumentId("test"),
        end,
        RadarMarketContentScope(start.date(), end),
        series,
    )
    calculator = Mock(wraps=subject.calculate_ema)
    monkeypatch.setattr(subject, "calculate_ema", calculator)
    result = subject.observe_ema8_ema20(history, as_of=observation().as_of)
    assert result.relation is relation
    assert calculator.call_args_list == [
        call(closes, period=8),
        call(closes, period=20),
    ]
    assert calculator.call_args_list[0].args[0] is calculator.call_args_list[1].args[0]
    assert result.definition_id == subject.EMA8_EMA20_OBSERVATION_DEFINITION_ID
    assert result.calculation_revision == subject.EMA8_EMA20_CALCULATION_REVISION
    assert result.observation_schema == subject.EMA8_EMA20_OBSERVATION_SCHEMA
    assert result.normalized_market_content_identity == series.content_fingerprint
    assert tuple(series.full_prefix().iter_rows()) == tuple(rows)


@pytest.mark.parametrize(
    "latest,expected",
    [
        (1.0000000000000002, RadarEmaRelation.ABOVE),
        (1.0, RadarEmaRelation.EQUAL),
        (0.9999999999999999, RadarEmaRelation.BELOW),
    ],
)
def test_exact_latest_comparison(monkeypatch, latest, expected):
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        ("TEST", start + timedelta(days=i), 1, 1, 1, 1, 1, "fixture")
        for i in range(250)
    ]
    series = HistoricalPriceSeries(pd.DataFrame(rows, columns=PRICE_COLUMNS))
    end = rows[-1][1].date()
    history = RadarCompletedDailyHistory(
        CanonicalInstrumentId("test"),
        end,
        RadarMarketContentScope(start.date(), end),
        series,
    )
    monkeypatch.setattr(
        subject,
        "calculate_ema",
        lambda values, *, period: (latest if period == 8 else 1.0,),
    )
    assert subject.calculate_ema8_ema20_relation(history) is expected
