from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from market_platform.data import HistoricalPricePrefix, HistoricalPriceSeries

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _prices(count: int = 4) -> pd.DataFrame:
    closes = [100.0 + index for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": [" msft "] * count,
            "timestamp": [_START + timedelta(days=index) for index in range(count)],
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": [" test-provider "] * count,
        }
    )


def test_historical_series_requires_complete_nonempty_frame() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        HistoricalPriceSeries(_prices(0))
    with pytest.raises(ValueError, match="missing required columns: volume"):
        HistoricalPriceSeries(_prices().drop(columns="volume"))


def test_historical_series_requires_single_matching_identity() -> None:
    multiple_symbols = _prices()
    multiple_symbols.loc[1, "symbol"] = "AAPL"
    with pytest.raises(ValueError, match="exactly one symbol"):
        HistoricalPriceSeries(multiple_symbols)
    with pytest.raises(ValueError, match="exactly one matching symbol"):
        HistoricalPriceSeries(_prices(), symbol="AAPL")

    multiple_providers = _prices()
    multiple_providers.loc[1, "provider"] = "other"
    with pytest.raises(ValueError, match="exactly one provider"):
        HistoricalPriceSeries(multiple_providers)
    with pytest.raises(ValueError, match="exactly one matching provider"):
        HistoricalPriceSeries(_prices(), provider="other")


def test_historical_series_rejects_naive_and_converts_aware_timestamps_to_utc() -> None:
    naive = _prices()
    naive["timestamp"] = naive["timestamp"].astype(object)
    naive.loc[0, "timestamp"] = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        HistoricalPriceSeries(naive)

    offset = timezone(timedelta(hours=8))
    prices = _prices(2)
    prices["timestamp"] = [
        datetime(2026, 1, 1, 8, tzinfo=offset),
        datetime(2026, 1, 2, 8, tzinfo=offset),
    ]
    series = HistoricalPriceSeries(prices)

    assert series.timestamp_at(0) == datetime(2026, 1, 1, tzinfo=UTC)
    assert series.as_of == datetime(2026, 1, 2, tzinfo=UTC)


def test_historical_series_stably_sorts_without_mutating_input() -> None:
    prices = _prices().iloc[[3, 0, 2, 1]].reset_index(drop=True)
    before = prices.copy(deep=True)

    series = HistoricalPriceSeries(prices)

    assert [row[1] for row in series.full_prefix().iter_rows()] == sorted(
        pd.Timestamp(value).to_pydatetime() for value in prices["timestamp"]
    )
    assert_frame_equal(prices, before)


def test_historical_series_rejects_duplicate_timestamps() -> None:
    prices = _prices()
    prices.loc[1, "timestamp"] = prices.loc[0, "timestamp"]

    with pytest.raises(ValueError, match="duplicate timestamps"):
        HistoricalPriceSeries(prices)


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_historical_series_rejects_nonfinite_ohlcv(
    column: str,
    value: float,
) -> None:
    prices = _prices()
    prices.loc[1, column] = value

    with pytest.raises(ValueError, match="invalid values|finite"):
        HistoricalPriceSeries(prices)


@pytest.mark.parametrize("column", ["open", "high", "low", "close"])
@pytest.mark.parametrize("value", [0.0, -1.0])
def test_historical_series_rejects_nonpositive_ohlc(
    column: str,
    value: float,
) -> None:
    prices = _prices()
    prices.loc[1, column] = value

    with pytest.raises(
        ValueError,
        match="OHLC prices must be positive|high must be greater",
    ):
        HistoricalPriceSeries(prices)


def test_historical_series_rejects_negative_volume_and_inverted_range() -> None:
    negative_volume = _prices()
    negative_volume.loc[1, "volume"] = -1.0
    with pytest.raises(ValueError, match="volume must not be negative"):
        HistoricalPriceSeries(negative_volume)

    inverted = _prices()
    inverted.loc[1, "high"] = inverted.loc[1, "low"] - 1.0
    with pytest.raises(ValueError, match="high must be greater"):
        HistoricalPriceSeries(inverted)


def test_historical_series_isolated_from_original_and_materialized_frames() -> None:
    prices = _prices()
    series = HistoricalPriceSeries(prices)
    expected = series.to_dataframe()

    prices.loc[0, "close"] = 9_999.0
    materialized = series.to_dataframe()
    materialized.loc[0, "close"] = 8_888.0

    assert_frame_equal(series.to_dataframe(), expected)
    assert series.full_prefix().latest_close == expected.iloc[-1]["close"]


def test_historical_prefix_has_inclusive_positional_semantics() -> None:
    series = HistoricalPriceSeries(_prices())
    prefix = series.prefix_at(1)

    assert isinstance(prefix, HistoricalPricePrefix)
    assert len(prefix) == 2
    assert prefix.position == 1
    assert prefix.symbol == "MSFT"
    assert prefix.provider == "test-provider"
    assert prefix.window_start == _START
    assert prefix.as_of == _START + timedelta(days=1)
    assert [row[1] for row in prefix.iter_rows()] == [
        _START,
        _START + timedelta(days=1),
    ]


@pytest.mark.parametrize("position", [-1, 4])
def test_historical_prefix_rejects_out_of_range_position(position: int) -> None:
    with pytest.raises(IndexError, match="existing historical row"):
        HistoricalPriceSeries(_prices()).prefix_at(position)


def test_historical_prefix_rejects_non_integer_position() -> None:
    with pytest.raises(TypeError, match="position must be an integer"):
        HistoricalPriceSeries(_prices()).prefix_at(True)


def test_historical_prefix_identity_is_immutable() -> None:
    prefix = HistoricalPriceSeries(_prices()).prefix_at(1)

    with pytest.raises(AttributeError):
        prefix._position = 3  # type: ignore[misc]


def test_historical_prefix_materialization_cannot_mutate_owner_or_other_prefixes(
) -> None:
    series = HistoricalPriceSeries(_prices())
    early = series.prefix_at(1)
    later = series.prefix_at(3)
    early_rows = tuple(early.iter_rows())
    later_rows = tuple(later.iter_rows())

    materialized = early.to_dataframe()
    materialized.loc[0, "close"] = 7_777.0
    materialized.loc[1, "timestamp"] = _START + timedelta(days=100)

    assert tuple(early.iter_rows()) == early_rows
    assert tuple(later.iter_rows()) == later_rows
    assert len(early_rows) == 2
    assert len(later_rows) == 4
