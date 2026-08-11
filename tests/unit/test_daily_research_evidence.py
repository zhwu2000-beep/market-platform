from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.research.daily_evidence import (
    DAILY_RESEARCH_EVIDENCE_SCHEMA,
    CompletedDailyPriceSeries,
    DailyAnalysisSessionScope,
    DailyResearchEvidence,
    PriceAdjustmentPolicy,
    ResearchTimeframe,
    prepare_completed_daily_price_series,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

NY = ZoneInfo("America/New_York")
INSTRUMENT = TradingInstrumentIdentity(symbol="AAPL", venue="NASDAQ")


def make_prices(
    labels: list[str],
    *,
    hour: int = 0,
    provider: str = "fixture",
) -> HistoricalPriceSeries:
    rows = []
    for index, label in enumerate(labels):
        close = 100.0 + index
        rows.append(
            {
                "symbol": "AAPL",
                "timestamp": datetime.fromisoformat(label).replace(
                    hour=hour, tzinfo=UTC
                ),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0 + index,
                "provider": provider,
            }
        )
    return HistoricalPriceSeries(pd.DataFrame(rows))


def prepare(
    prices: HistoricalPriceSeries,
    analysis_as_of: datetime = datetime(2026, 1, 3, 12, tzinfo=UTC),
    **overrides: object,
) -> CompletedDailyPriceSeries:
    arguments: dict[str, object] = {
        "prices": prices,
        "instrument": INSTRUMENT,
        "timeframe": ResearchTimeframe.DAILY,
        "session_scope": DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE,
        "market_timezone": "America/New_York",
        "adjustment_policy": PriceAdjustmentPolicy.ADJUSTED,
        "analysis_as_of": analysis_as_of,
    }
    arguments.update(overrides)
    return prepare_completed_daily_price_series(**arguments)  # type: ignore[arg-type]


def test_daily_evidence_enum_inventories_are_exact() -> None:
    assert list(ResearchTimeframe) == [ResearchTimeframe.DAILY]
    assert ResearchTimeframe.DAILY.value == "1d"
    assert list(DailyAnalysisSessionScope) == [
        DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE
    ]
    assert DailyAnalysisSessionScope.PROVIDER_DAILY_AGGREGATE.value == (
        "provider_daily_aggregate"
    )
    assert [(value.name, value.value) for value in PriceAdjustmentPolicy] == [
        ("ADJUSTED", "adjusted"),
        ("PROVIDER_DEFAULT", "provider_default"),
    ]


def test_completed_daily_cutoff_projection_and_fingerprint() -> None:
    source = make_prices(["2026-01-01", "2026-01-02", "2026-01-03"])
    completed = prepare(source)
    evidence = completed.evidence
    assert len(completed) == 2
    assert [row[1].date().isoformat() for row in completed.iter_rows()] == [
        "2026-01-01",
        "2026-01-02",
    ]
    assert [field.name for field in fields(DailyResearchEvidence)] == [
        "instrument",
        "timeframe",
        "session_scope",
        "market_timezone",
        "adjustment_policy",
        "analysis_as_of",
        "cutoff_session_date",
        "first_used_session_date",
        "latest_completed_bar_session_date",
        "bar_count",
        "excluded_current_session_row_count",
        "calendar_lag_days",
        "provider",
        "dataset_content_fingerprint",
        "schema_version",
        "fingerprint",
    ]
    assert list(evidence.to_dict()) == [
        "schema_version",
        "instrument",
        "timeframe",
        "session_scope",
        "market_timezone",
        "adjustment_policy",
        "analysis_as_of",
        "cutoff_session_date",
        "first_used_session_date",
        "latest_completed_bar_session_date",
        "bar_count",
        "excluded_current_session_row_count",
        "calendar_lag_days",
        "provider",
        "dataset_content_fingerprint",
        "fingerprint",
    ]
    assert evidence.schema_version == DAILY_RESEARCH_EVIDENCE_SCHEMA
    assert evidence.fingerprint == canonical_fingerprint(
        evidence._fingerprint_payload()
    )
    assert evidence.excluded_current_session_row_count == 1
    assert evidence.calendar_lag_days == 1
    admitted = HistoricalPriceSeries(source.to_dataframe().iloc[:2])
    assert evidence.dataset_content_fingerprint == admitted.content_fingerprint


def test_analysis_as_of_is_canonicalized_to_utc() -> None:
    source = make_prices(["2026-01-01"])
    supplied = datetime(2026, 1, 2, 20, tzinfo=timezone(timedelta(hours=8)))
    evidence = prepare(source, supplied).evidence
    assert evidence.analysis_as_of.tzinfo is UTC
    assert evidence.analysis_as_of == supplied.astimezone(UTC)


def test_same_local_date_stays_excluded_until_local_midnight() -> None:
    source = make_prices(["2026-01-01", "2026-01-02"])
    after_close = datetime(2026, 1, 2, 17, 0, tzinfo=NY)
    assert len(prepare(source, after_close)) == 1
    after_midnight = datetime(2026, 1, 3, 0, 1, tzinfo=NY)
    assert len(prepare(source, after_midnight)) == 2


def test_weekend_neutral_cutoff_uses_calendar_dates_only() -> None:
    source = make_prices(["2026-01-02"])
    completed = prepare(source, datetime(2026, 1, 4, 12, tzinfo=NY))
    assert len(completed) == 1
    assert completed.evidence.calendar_lag_days == 2


@pytest.mark.parametrize("hour", [1, 12, 23])
def test_daily_timestamp_must_be_exact_midnight_utc(hour: int) -> None:
    with pytest.raises(ValueError, match="midnight UTC"):
        prepare(make_prices(["2026-01-01"], hour=hour))


def test_future_label_and_empty_admitted_evidence_are_rejected() -> None:
    with pytest.raises(ValueError, match="future"):
        prepare(make_prices(["2026-01-04"]))
    with pytest.raises(ValueError, match="at least one"):
        prepare(
            make_prices(["2026-01-03"]),
            datetime(2026, 1, 3, 12, tzinfo=UTC),
        )


def test_symbol_timezone_and_public_argument_validation() -> None:
    with pytest.raises(ValueError, match="symbol"):
        prepare(
            make_prices(["2026-01-01"]),
            instrument=TradingInstrumentIdentity("MSFT", "NASDAQ"),
        )
    with pytest.raises(ValueError, match="market_timezone"):
        prepare(make_prices(["2026-01-01"]), market_timezone="UTC")
    with pytest.raises(TypeError):
        prepare(
            make_prices(["2026-01-01"]),
            timeframe="1d",
        )
    with pytest.raises(TypeError):
        prepare(
            make_prices(["2026-01-01"]),
            analysis_as_of="2026-01-03",
        )


def test_duplicate_timestamp_is_rejected_during_defensive_reconstruction() -> None:
    source = make_prices(["2026-01-01", "2026-01-02"])
    frame = source.to_dataframe()
    source._frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        prepare(source)


def test_source_and_materialized_frames_are_isolated() -> None:
    source = make_prices(["2026-01-01", "2026-01-02"])
    completed = prepare(source)
    original_rows = tuple(completed.iter_rows())
    source._frame.loc[0, "close"] = 9999.0
    assert tuple(completed.iter_rows()) == original_rows
    frame = completed.to_dataframe()
    frame.loc[0, "close"] = -1.0
    assert tuple(completed.iter_rows()) == original_rows
    assert not hasattr(completed, "to_dict")
    assert not hasattr(completed, "prices")


def test_factory_owned_construction_and_retained_corruption() -> None:
    with pytest.raises(TypeError):
        DailyResearchEvidence()
    with pytest.raises(TypeError):
        CompletedDailyPriceSeries()
    evidence = prepare(make_prices(["2026-01-01"])).evidence
    object.__setattr__(evidence, "bar_count", 0)
    with pytest.raises(ValueError):
        evidence.to_dict()


def test_noncanonical_retained_datetime_is_rejected_even_if_refingerprinted() -> None:
    evidence = prepare(make_prices(["2026-01-01"])).evidence
    object.__setattr__(
        evidence,
        "analysis_as_of",
        evidence.analysis_as_of.astimezone(timezone(timedelta(hours=8))),
    )
    object.__setattr__(
        evidence, "fingerprint", canonical_fingerprint(evidence._fingerprint_payload())
    )
    with pytest.raises(ValueError, match="canonical UTC"):
        evidence.to_dict()


def test_coherent_self_contained_evidence_rewrite_remains_valid() -> None:
    evidence = prepare(make_prices(["2026-01-01"])).evidence
    object.__setattr__(evidence, "provider", "rewritten")
    object.__setattr__(
        evidence, "fingerprint", canonical_fingerprint(evidence._fingerprint_payload())
    )
    assert evidence.to_dict()["provider"] == "rewritten"


def test_carrier_revalidates_row_evidence_correspondence() -> None:
    completed = prepare(make_prices(["2026-01-01", "2026-01-02"]))
    object.__setattr__(
        completed.evidence, "dataset_content_fingerprint", "sha256:" + "0" * 64
    )
    with pytest.raises(ValueError):
        tuple(completed.iter_rows())

class StrSubclass(str):
    pass


@pytest.mark.parametrize("surface", ["evidence", "carrier"])
def test_deleted_evidence_fingerprint_is_always_value_error(surface: str) -> None:
    completed = prepare(make_prices(["2026-01-01"]))
    evidence = completed.evidence
    object.__delattr__(evidence, "fingerprint")
    with pytest.raises(ValueError, match="missing retained field fingerprint"):
        if surface == "evidence":
            evidence.to_dict()
        else:
            len(completed)


@pytest.mark.parametrize(
    ("label", "analysis_as_of"),
    [
        ("2026-01-01", datetime(2026, 1, 3, 12, tzinfo=UTC)),
        ("2026-03-06", datetime(2026, 3, 8, 7, 30, tzinfo=UTC)),
        ("2026-10-30", datetime(2026, 11, 1, 6, 30, tzinfo=UTC)),
        ("2025-12-30", datetime(2026, 1, 1, 5, 1, tzinfo=UTC)),
    ],
)
def test_refingerprinted_cutoff_must_match_analysis_as_of(
    label: str, analysis_as_of: datetime
) -> None:
    evidence = prepare(make_prices([label]), analysis_as_of).evidence
    rewritten_cutoff = evidence.cutoff_session_date + timedelta(days=1)
    object.__setattr__(evidence, "cutoff_session_date", rewritten_cutoff)
    object.__setattr__(
        evidence,
        "calendar_lag_days",
        (rewritten_cutoff - evidence.latest_completed_bar_session_date).days,
    )
    object.__setattr__(
        evidence, "fingerprint", canonical_fingerprint(evidence._fingerprint_payload())
    )
    with pytest.raises(ValueError, match="cutoff"):
        evidence.to_dict()


@pytest.mark.parametrize("field_name", ["schema_version", "fingerprint"])
def test_evidence_rejects_str_subclass_schema_and_fingerprint(
    field_name: str,
) -> None:
    evidence = prepare(make_prices(["2026-01-01"])).evidence
    object.__setattr__(evidence, field_name, StrSubclass(getattr(evidence, field_name)))
    if field_name == "schema_version":
        object.__setattr__(
            evidence,
            "fingerprint",
            canonical_fingerprint(evidence._fingerprint_payload()),
        )
    with pytest.raises(ValueError):
        evidence.to_dict()
