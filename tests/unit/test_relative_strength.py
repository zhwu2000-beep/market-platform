from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest

from market_platform.signals import (
    align_asset_and_benchmark_prices,
    calculate_relative_strength,
)


def _price_frame(
    *,
    symbol: str,
    timestamps: list[datetime],
    closes: list[float],
) -> pd.DataFrame:
    values = list(closes)
    return pd.DataFrame(
        {
            "symbol": [symbol] * len(values),
            "timestamp": list(timestamps),
            "open": values,
            "high": [value + 1.0 for value in values],
            "low": [value - 1.0 for value in values],
            "close": values,
            "volume": [1_000_000 + index for index in range(len(values))],
            "provider": ["twelvedata"] * len(values),
        }
    )


def _daily_timestamps(start: datetime, count: int) -> list[datetime]:
    return [start + timedelta(days=index) for index in range(count)]


def test_align_asset_and_benchmark_prices_normalizes_utc_and_sorts_stably() -> None:
    asset = _price_frame(
        symbol=" msft ",
        timestamps=[
            datetime(2026, 1, 3, 8, tzinfo=timezone(timedelta(hours=8))),
            datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8))),
            datetime(2026, 1, 2, 8, tzinfo=timezone(timedelta(hours=8))),
        ],
        closes=[103.0, 101.0, 102.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=[
            datetime(2026, 1, 2, 0, tzinfo=UTC),
            datetime(2026, 1, 3, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 0, tzinfo=UTC),
        ],
        closes=[202.0, 203.0, 201.0],
    )

    asset_aligned, benchmark_aligned = align_asset_and_benchmark_prices(
        asset,
        benchmark,
    )

    assert list(asset_aligned.columns) == ["symbol", "timestamp", "close"]
    assert list(benchmark_aligned.columns) == ["symbol", "timestamp", "close"]
    assert list(asset_aligned["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
        pd.Timestamp("2026-01-03T00:00:00Z"),
    ]
    assert list(benchmark_aligned["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
        pd.Timestamp("2026-01-03T00:00:00Z"),
    ]
    assert len(asset_aligned) == len(benchmark_aligned)
    assert asset_aligned["timestamp"].reset_index(drop=True).equals(
        benchmark_aligned["timestamp"].reset_index(drop=True)
    )
    assert asset_aligned["timestamp"].dt.tz is not None
    assert benchmark_aligned["timestamp"].dt.tz is not None
    assert list(asset_aligned["symbol"]) == ["msft", "msft", "msft"]
    assert list(benchmark_aligned["symbol"]) == ["SPY", "SPY", "SPY"]


def test_align_asset_and_benchmark_prices_does_not_mutate_sources() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 3),
        closes=[100.0, 101.0, 102.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 3),
        closes=[200.0, 201.0, 202.0],
    )
    asset_original = asset.copy(deep=True)
    benchmark_original = benchmark.copy(deep=True)

    align_asset_and_benchmark_prices(asset, benchmark)

    pd.testing.assert_frame_equal(asset, asset_original)
    pd.testing.assert_frame_equal(benchmark, benchmark_original)


def test_align_asset_and_benchmark_prices_keeps_partial_overlap_aligned() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 4),
        closes=[100.0, 101.0, 102.0, 103.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 3, tzinfo=UTC), 4),
        closes=[200.0, 201.0, 202.0, 203.0],
    )

    asset_aligned, benchmark_aligned = align_asset_and_benchmark_prices(
        asset,
        benchmark,
    )

    assert len(asset_aligned) == len(benchmark_aligned) == 2
    assert asset_aligned["timestamp"].reset_index(drop=True).equals(
        benchmark_aligned["timestamp"].reset_index(drop=True)
    )
    assert list(asset_aligned["timestamp"]) == [
        pd.Timestamp("2026-01-03T00:00:00Z"),
        pd.Timestamp("2026-01-04T00:00:00Z"),
    ]
    assert list(benchmark_aligned["timestamp"]) == [
        pd.Timestamp("2026-01-03T00:00:00Z"),
        pd.Timestamp("2026-01-04T00:00:00Z"),
    ]


def test_align_asset_and_benchmark_prices_rejects_no_overlap() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 3, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )

    with pytest.raises(ValueError, match="do not share any timestamps"):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_align_asset_and_benchmark_prices_rejects_empty_asset_frame() -> None:
    asset = pd.DataFrame(columns=["symbol", "timestamp", "close"])
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )

    with pytest.raises(ValueError, match="Asset price frame must not be empty"):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_align_asset_and_benchmark_prices_rejects_empty_benchmark_frame() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = pd.DataFrame(columns=["symbol", "timestamp", "close"])

    with pytest.raises(ValueError, match="Benchmark price frame must not be empty"):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_duplicate_asset_timestamps_are_rejected() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=[
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ],
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )

    with pytest.raises(
        ValueError,
        match="Asset price frame must not contain duplicate timestamps",
    ):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_duplicate_benchmark_timestamps_are_rejected() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=[
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ],
        closes=[200.0, 201.0],
    )

    with pytest.raises(
        ValueError,
        match="Benchmark price frame must not contain duplicate timestamps",
    ):
        align_asset_and_benchmark_prices(asset, benchmark)


@pytest.mark.parametrize("window", [0, -1, 1.5])
def test_calculate_relative_strength_rejects_invalid_window(window: object) -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 25),
        closes=[100.0 + index for index in range(25)],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 25),
        closes=[200.0 + index for index in range(25)],
    )

    with pytest.raises(ValueError, match="positive integer"):
        calculate_relative_strength(asset, benchmark, window=window)  # type: ignore[arg-type]


def test_calculate_relative_strength_matches_exact_formula() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 25),
        closes=[100.0 + index for index in range(25)],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 25),
        closes=[200.0 + 2.0 * index for index in range(25)],
    )

    signal = calculate_relative_strength(asset, benchmark)

    expected = (
        (asset["close"].iloc[-1] / asset["close"].iloc[-21])
        / (benchmark["close"].iloc[-1] / benchmark["close"].iloc[-21])
        - 1.0
    )
    assert signal.value == pytest.approx(expected)
    assert signal.symbol == "MSFT"
    assert signal.name == "relative_strength"
    assert signal.timestamp == pd.Timestamp("2026-01-25T00:00:00Z").to_pydatetime()
    assert signal.parameters == {
        "window": 20,
        "benchmark_symbol": "SPY",
        "alignment": "timestamp_intersection",
        "return_type": "total_return_ratio",
    }


def test_calculate_relative_strength_returns_none_for_insufficient_history() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 10),
        closes=[100.0 + index for index in range(10)],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 10),
        closes=[200.0 + index for index in range(10)],
    )

    signal = calculate_relative_strength(asset, benchmark)

    assert signal.value is None
    assert signal.symbol == "MSFT"
    assert signal.name == "relative_strength"
    assert signal.timestamp == pd.Timestamp("2026-01-10T00:00:00Z").to_pydatetime()
    assert signal.parameters == {
        "window": 20,
        "benchmark_symbol": "SPY",
        "alignment": "timestamp_intersection",
        "return_type": "total_return_ratio",
    }


@pytest.mark.parametrize(
    ("asset_columns", "benchmark_columns", "message"),
    [
        (
            ("symbol", "close"),
            ("symbol", "timestamp", "close"),
            "Asset price frame is missing required columns",
        ),
        (
            ("symbol", "timestamp", "close"),
            ("symbol", "close"),
            "Benchmark price frame is missing required columns",
        ),
    ],
)
def test_calculate_relative_strength_rejects_missing_required_columns(
    asset_columns: tuple[str, ...],
    benchmark_columns: tuple[str, ...],
    message: str,
) -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    ).loc[:, list(asset_columns)]
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    ).loc[:, list(benchmark_columns)]

    with pytest.raises(ValueError, match=message):
        align_asset_and_benchmark_prices(asset, benchmark)


@pytest.mark.parametrize("column", ["symbol", "timestamp", "close"])
def test_calculate_relative_strength_rejects_missing_values(column: str) -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )
    asset.loc[0, column] = None

    if column == "timestamp":
        expected_message = "Asset price frame must not contain missing timestamps"
    else:
        expected_message = (
            f"Asset price frame must not contain missing {column} values"
        )

    with pytest.raises(ValueError, match=expected_message):
        align_asset_and_benchmark_prices(asset, benchmark)


@pytest.mark.parametrize("column", ["symbol", "timestamp", "close"])
def test_calculate_relative_strength_rejects_blank_or_invalid_values(
    column: str,
) -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )

    if column == "symbol":
        asset.loc[0, column] = "   "
        expected = "Asset price frame must not contain empty symbol values"
    elif column == "timestamp":
        asset["timestamp"] = asset["timestamp"].astype(object)
        asset.loc[0, column] = "not-a-timestamp"
        expected = None
    else:
        asset.loc[0, column] = float("inf")
        expected = "Asset price frame must not contain non-finite close values"

    if expected is None:
        with pytest.raises(ValueError):
            align_asset_and_benchmark_prices(asset, benchmark)
    else:
        with pytest.raises(ValueError, match=expected):
            align_asset_and_benchmark_prices(asset, benchmark)


def test_calculate_relative_strength_rejects_multiple_symbols_in_either_input() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )
    asset.loc[0, "symbol"] = "AAPL"

    with pytest.raises(ValueError, match="exactly one unique symbol"):
        align_asset_and_benchmark_prices(asset, benchmark)

    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark.loc[0, "symbol"] = "QQQ"

    with pytest.raises(ValueError, match="exactly one unique symbol"):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_calculate_relative_strength_rejects_same_asset_and_benchmark_symbol() -> None:
    asset = _price_frame(
        symbol="msft",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )

    with pytest.raises(ValueError, match="must use different symbols"):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_calculate_relative_strength_rejects_invalid_timestamps() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )
    asset["timestamp"] = asset["timestamp"].astype(object)
    asset.loc[0, "timestamp"] = "not-a-timestamp"

    with pytest.raises(ValueError):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_calculate_relative_strength_rejects_missing_close_values() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )
    asset.loc[0, "close"] = None

    with pytest.raises(ValueError, match="missing close values"):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_calculate_relative_strength_rejects_non_finite_close_values() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[100.0, 101.0],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 2),
        closes=[200.0, 201.0],
    )
    asset.loc[0, "close"] = float("inf")

    with pytest.raises(ValueError, match="non-finite close values"):
        align_asset_and_benchmark_prices(asset, benchmark)


def test_calculate_relative_strength_rejects_zero_denominator() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 21),
        closes=[100.0 + index for index in range(21)],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 21),
        closes=[200.0 + index for index in range(20)] + [0.0],
    )

    with pytest.raises(ValueError, match="Denominator must be non-zero"):
        calculate_relative_strength(asset, benchmark, window=20)


def test_calculate_relative_strength_parameters_are_stable() -> None:
    asset = _price_frame(
        symbol="MSFT",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 21),
        closes=[100.0 + index for index in range(21)],
    )
    benchmark = _price_frame(
        symbol="SPY",
        timestamps=_daily_timestamps(datetime(2026, 1, 1, tzinfo=UTC), 21),
        closes=[200.0 + index for index in range(21)],
    )

    signal = calculate_relative_strength(asset, benchmark, window=20)

    assert signal.parameters == {
        "window": 20,
        "benchmark_symbol": "SPY",
        "alignment": "timestamp_intersection",
        "return_type": "total_return_ratio",
    }
    assert signal.timestamp.tzinfo is not None
