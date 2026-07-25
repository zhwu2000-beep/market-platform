from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest

from market_platform.data import HistoricalPriceSeries
from market_platform.observation import (
    build_historical_market_observation,
    build_historical_market_observation_from_prefix,
)
from market_platform.signals import MarketSignalSnapshot, calculate_market_signals
from market_platform.structure import PriceStructureService

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _prices(count: int = 20) -> pd.DataFrame:
    closes = [100.0 + index * 0.5 for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * count,
            "timestamp": [_START + timedelta(days=index) for index in range(count)],
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": ["test-provider"] * count,
        }
    )


def _snapshots(series: HistoricalPriceSeries):
    frame = series.to_dataframe()
    return (
        calculate_market_signals(frame),
        PriceStructureService().analyze(frame, as_of=series.as_of),
    )


def test_raw_and_validated_prefix_observation_builders_are_exactly_equal() -> None:
    prices = _prices()
    series = HistoricalPriceSeries(
        prices,
        symbol="MSFT",
        provider="test-provider",
    )
    signal_snapshot, structure_snapshot = _snapshots(series)

    raw = build_historical_market_observation(
        prices,
        symbol="MSFT",
        interval="1day",
        as_of=series.as_of,
        provider="test-provider",
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )
    prefixed = build_historical_market_observation_from_prefix(
        series.full_prefix(),
        symbol="MSFT",
        interval="1day",
        as_of=series.as_of,
        provider="test-provider",
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )

    assert prefixed == raw
    assert prefixed.to_dict() == raw.to_dict()
    assert (
        prefixed.provenance.input_fingerprint
        == raw.provenance.input_fingerprint
    )


def test_later_evaluation_time_preserves_endpoint_and_builder_parity() -> None:
    prices = _prices()
    series = HistoricalPriceSeries(prices)
    prefix = series.full_prefix()
    evaluation_as_of = prefix.as_of + timedelta(hours=12)
    signal_snapshot, structure_snapshot = _snapshots(series)

    raw = build_historical_market_observation(
        prices,
        symbol="MSFT",
        interval="1day",
        as_of=evaluation_as_of,
        provider="test-provider",
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )
    prefixed = build_historical_market_observation_from_prefix(
        prefix,
        symbol="MSFT",
        interval="1day",
        as_of=evaluation_as_of,
        provider="test-provider",
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )

    assert prefixed.to_dict() == raw.to_dict()
    assert (
        prefixed.provenance.input_fingerprint
        == raw.provenance.input_fingerprint
    )
    payload = prefixed.to_dict()
    assert payload["identity"]["window_end"] == prefix.as_of.isoformat()
    assert payload["price_facts"]["observed_at"] == prefix.as_of.isoformat()
    assert payload["identity"]["as_of"] == evaluation_as_of.isoformat()


def test_evaluation_time_changes_fingerprint_without_changing_prefix() -> None:
    series = HistoricalPriceSeries(_prices())
    prefix = series.full_prefix()
    signal_snapshot, structure_snapshot = _snapshots(series)
    kwargs = {
        "symbol": "MSFT",
        "interval": "1day",
        "provider": "test-provider",
        "signal_snapshot": signal_snapshot,
        "structure_snapshot": structure_snapshot,
    }

    endpoint_observation = build_historical_market_observation_from_prefix(
        prefix,
        as_of=prefix.as_of,
        **kwargs,
    )
    later_observation = build_historical_market_observation_from_prefix(
        prefix,
        as_of=prefix.as_of + timedelta(hours=12),
        **kwargs,
    )

    assert (
        endpoint_observation.provenance.input_fingerprint
        != later_observation.provenance.input_fingerprint
    )


def test_unsorted_offset_input_normalizes_to_identical_observation() -> None:
    offset = timezone(timedelta(hours=8))
    canonical = _prices()
    offset_unsorted = canonical.copy(deep=True)
    offset_unsorted["timestamp"] = [
        value.astimezone(offset) for value in canonical["timestamp"]
    ]
    offset_unsorted = offset_unsorted.iloc[::-1].reset_index(drop=True)
    series = HistoricalPriceSeries(canonical)
    signal_snapshot, structure_snapshot = _snapshots(series)

    expected = build_historical_market_observation(
        canonical,
        symbol="MSFT",
        interval="1day",
        as_of=series.as_of,
        provider="test-provider",
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )
    actual = build_historical_market_observation(
        offset_unsorted,
        symbol="MSFT",
        interval="1day",
        as_of=series.as_of,
        provider="test-provider",
        signal_snapshot=signal_snapshot,
        structure_snapshot=structure_snapshot,
    )

    assert actual.to_dict() == expected.to_dict()
    assert (
        actual.provenance.input_fingerprint
        == expected.provenance.input_fingerprint
    )


def test_prefix_builder_rejects_earlier_as_of_and_mismatched_metadata() -> None:
    series = HistoricalPriceSeries(_prices())
    prefix = series.full_prefix()
    signal_snapshot, structure_snapshot = _snapshots(series)
    kwargs = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": prefix.as_of,
        "provider": "test-provider",
        "signal_snapshot": signal_snapshot,
        "structure_snapshot": structure_snapshot,
    }

    with pytest.raises(ValueError, match="earlier than historical prefix endpoint"):
        build_historical_market_observation_from_prefix(
            prefix,
            **{**kwargs, "as_of": prefix.as_of - timedelta(days=1)},
        )
    with pytest.raises(ValueError, match="prefix symbol"):
        build_historical_market_observation_from_prefix(
            prefix,
            **{**kwargs, "symbol": "AAPL"},
        )
    with pytest.raises(ValueError, match="prefix provider"):
        build_historical_market_observation_from_prefix(
            prefix,
            **{**kwargs, "provider": "other"},
        )


def test_prefix_builder_validates_snapshot_types_and_signal_symbol() -> None:
    series = HistoricalPriceSeries(_prices())
    prefix = series.full_prefix()
    signal_snapshot, structure_snapshot = _snapshots(series)
    kwargs = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": prefix.as_of,
        "provider": "test-provider",
        "signal_snapshot": signal_snapshot,
        "structure_snapshot": structure_snapshot,
    }

    with pytest.raises(TypeError, match="signal_snapshot"):
        build_historical_market_observation_from_prefix(
            prefix,
            **{**kwargs, "signal_snapshot": object()},
        )
    with pytest.raises(TypeError, match="structure_snapshot"):
        build_historical_market_observation_from_prefix(
            prefix,
            **{**kwargs, "structure_snapshot": object()},
        )

    mismatched_signal = replace(signal_snapshot, symbol="AAPL")
    assert isinstance(mismatched_signal, MarketSignalSnapshot)
    with pytest.raises(ValueError, match="signal_snapshot symbol"):
        build_historical_market_observation_from_prefix(
            prefix,
            **{**kwargs, "signal_snapshot": mismatched_signal},
        )
