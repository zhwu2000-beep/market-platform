from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from market_platform.structure import (
    PriceLevelKind,
    detect_swing_highs,
    detect_swing_lows,
)


def _price_frame(
    *,
    timestamps: list[datetime],
    highs: list[float],
    lows: list[float],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * len(timestamps),
            "timestamp": timestamps,
            "open": highs,
            "high": highs,
            "low": lows,
            "close": lows,
            "volume": [1_000] * len(timestamps),
        }
    )


def _timestamps(count: int) -> list[datetime]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [start + pd.Timedelta(days=index) for index in range(count)]


def test_detect_swing_highs_finds_single_strict_pivot() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )

    candidates = detect_swing_highs(prices, window=1)

    assert len(candidates) == 1
    assert candidates[0].kind is PriceLevelKind.SWING_HIGH
    assert candidates[0].price == 15.0
    assert candidates[0].occurred_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert candidates[0].confirmed_at == datetime(2026, 1, 4, tzinfo=UTC)
    assert candidates[0].observed_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert candidates[0].source_method == "swing_pivot"


def test_detect_swing_lows_finds_single_strict_pivot() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 6.0, 8.0, 9.0],
    )

    candidates = detect_swing_lows(prices, window=1)

    assert len(candidates) == 1
    assert candidates[0].kind is PriceLevelKind.SWING_LOW
    assert candidates[0].price == 6.0
    assert candidates[0].occurred_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert candidates[0].confirmed_at == datetime(2026, 1, 4, tzinfo=UTC)
    assert candidates[0].observed_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert candidates[0].source_method == "swing_pivot"


def test_detect_swing_pivots_are_stable_and_timestamp_ordered() -> None:
    prices = _price_frame(
        timestamps=_timestamps(7),
        highs=[10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0],
        lows=[9.0, 8.0, 7.0, 8.0, 6.0, 7.0, 8.0],
    )

    highs = detect_swing_highs(prices, window=1)
    lows = detect_swing_lows(prices, window=1)

    assert [candidate.observed_at for candidate in highs] == [
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2026, 1, 4, tzinfo=UTC),
        datetime(2026, 1, 6, tzinfo=UTC),
    ]
    assert [candidate.observed_at for candidate in lows] == [
        datetime(2026, 1, 3, tzinfo=UTC),
        datetime(2026, 1, 5, tzinfo=UTC),
    ]


def test_detect_swing_pivots_excludes_boundary_bars() -> None:
    prices = _price_frame(
        timestamps=_timestamps(7),
        highs=[10.0, 15.0, 12.0, 11.0, 12.0, 15.0, 10.0],
        lows=[9.0, 8.0, 9.0, 8.0, 9.0, 8.0, 9.0],
    )

    highs = detect_swing_highs(prices, window=2)
    lows = detect_swing_lows(prices, window=2)

    assert highs == ()
    assert lows == ()


def test_detect_swing_pivots_returns_empty_tuple_for_insufficient_data() -> None:
    prices = _price_frame(
        timestamps=_timestamps(4),
        highs=[10.0, 11.0, 12.0, 11.0],
        lows=[9.0, 8.0, 7.0, 8.0],
    )

    assert detect_swing_highs(prices, window=3) == ()
    assert detect_swing_lows(prices, window=3) == ()


def test_detect_swing_pivots_reject_equal_high_plateaus() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 12.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )

    assert detect_swing_highs(prices, window=1) == ()


def test_detect_swing_pivots_reject_equal_low_plateaus() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 11.0, 12.0, 11.0, 10.0],
        lows=[9.0, 8.0, 8.0, 9.0, 10.0],
    )

    assert detect_swing_lows(prices, window=1) == ()


def test_detect_swing_pivots_window_changes_results() -> None:
    prices = _price_frame(
        timestamps=_timestamps(7),
        highs=[1.0, 4.0, 5.0, 4.0, 6.0, 4.0, 1.0],
        lows=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    )

    window_one = detect_swing_highs(prices, window=1)
    window_two = detect_swing_highs(prices, window=2)

    assert len(window_one) == 2
    assert len(window_two) == 1
    assert window_one != window_two


def test_detect_swing_pivots_require_high_and_low_columns() -> None:
    prices = pd.DataFrame(
        {
            "symbol": ["MSFT"],
            "timestamp": [datetime(2026, 1, 1, tzinfo=UTC)],
            "high": [10.0],
        }
    )

    with pytest.raises(ValueError, match="missing required columns: low"):
        detect_swing_highs(prices, window=1)


def test_detect_swing_pivots_reject_invalid_window() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )

    with pytest.raises(ValueError, match="window must be at least 1"):
        detect_swing_highs(prices, window=0)
    with pytest.raises(ValueError, match="window must be at least 1"):
        detect_swing_lows(prices, window=-1)


def test_detect_swing_pivots_do_not_mutate_input_frame() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5)[::-1],
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )
    original = prices.copy(deep=True)

    detect_swing_highs(prices, window=1)
    detect_swing_lows(prices, window=1)

    pd.testing.assert_frame_equal(prices, original)


def test_detect_swing_pivots_are_deterministic_for_same_input() -> None:
    prices = _price_frame(
        timestamps=_timestamps(7),
        highs=[10.0, 12.0, 15.0, 11.0, 14.0, 10.0, 9.0],
        lows=[9.0, 8.0, 7.0, 8.0, 6.0, 7.0, 8.0],
    )

    first = detect_swing_highs(prices, window=1)
    second = detect_swing_highs(prices, window=1)

    assert first == second


def test_detect_swing_pivots_use_source_column_values() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 6.0, 8.0, 9.0],
    )

    high_candidates = detect_swing_highs(prices, window=1)
    low_candidates = detect_swing_lows(prices, window=1)

    assert high_candidates[0].price == prices.loc[2, "high"]
    assert low_candidates[0].price == prices.loc[2, "low"]
    assert high_candidates[0].observed_at == prices.loc[2, "timestamp"]
    assert low_candidates[0].observed_at == prices.loc[2, "timestamp"]


@pytest.mark.parametrize("column", ["high", "low"])
def test_detect_swing_pivots_reject_bool_prices(column: str) -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )
    prices[column] = prices[column].astype(object)
    prices.loc[0, column] = True

    with pytest.raises(TypeError, match=f"{column} must be numeric"):
        detect_swing_highs(prices, window=1)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("high", float("nan"), "invalid high values"),
        ("high", float("inf"), "non-finite high values"),
        ("high", float("-inf"), "non-finite high values"),
        ("low", float("nan"), "invalid low values"),
        ("low", float("inf"), "non-finite low values"),
        ("low", float("-inf"), "non-finite low values"),
    ],
)
def test_detect_swing_pivots_reject_non_finite_prices(
    column: str,
    value: float,
    message: str,
) -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )
    prices.loc[0, column] = value

    with pytest.raises(ValueError, match=message):
        detect_swing_highs(prices, window=1)


def test_detect_swing_pivots_reject_high_below_low() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 6.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )

    with pytest.raises(ValueError, match="high must be greater than or equal to low"):
        detect_swing_highs(prices, window=1)


def test_detect_swing_pivots_reject_duplicate_timestamps() -> None:
    timestamps = _timestamps(5)
    timestamps[2] = timestamps[1]
    prices = _price_frame(
        timestamps=timestamps,
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )

    with pytest.raises(ValueError, match="must not contain duplicate timestamps"):
        detect_swing_highs(prices, window=1)


def test_detect_swing_pivots_reject_invalid_timestamps() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 8.0, 9.0],
    )
    prices.loc[2, "timestamp"] = pd.NaT

    with pytest.raises(ValueError, match="invalid timestamp values"):
        detect_swing_highs(prices, window=1)


def test_detect_swing_pivots_allow_high_equal_to_low() -> None:
    prices = _price_frame(
        timestamps=_timestamps(5),
        highs=[10.0, 12.0, 15.0, 11.0, 10.0],
        lows=[9.0, 8.0, 15.0, 8.0, 9.0],
    )

    candidates = detect_swing_highs(prices, window=1)

    assert [candidate.price for candidate in candidates] == [15.0]
