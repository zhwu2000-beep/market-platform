from __future__ import annotations

import pandas as pd
import pytest

from market_platform.structure import calculate_atr


def _price_frame(
    *,
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> pd.DataFrame:
    count = len(highs)
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * count,
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1_000] * count,
        }
    )


def test_calculate_atr_uses_simple_moving_average_and_first_true_range() -> None:
    prices = _price_frame(
        highs=[10.0, 13.0, 12.0],
        lows=[8.0, 9.0, 10.0],
        closes=[9.0, 12.0, 11.0],
    )

    atr = calculate_atr(prices, period=3)

    assert atr == pytest.approx((2.0 + 4.0 + 2.0) / 3.0)


def test_calculate_atr_handles_gap_up_and_gap_down() -> None:
    prices = _price_frame(
        highs=[10.0, 15.0, 8.0, 12.0],
        lows=[8.0, 14.0, 5.0, 10.0],
        closes=[9.0, 14.5, 6.0, 11.0],
    )

    atr = calculate_atr(prices, period=4)

    # TR values: 2.0, 6.0, 9.5, 6.0 -> SMA = 5.875
    assert atr == pytest.approx(5.875)


def test_calculate_atr_period_one_returns_latest_true_range() -> None:
    prices = _price_frame(
        highs=[10.0, 15.0],
        lows=[8.0, 14.0],
        closes=[9.0, 14.5],
    )

    atr = calculate_atr(prices, period=1)

    assert atr == pytest.approx(6.0)


def test_calculate_atr_returns_none_when_period_is_not_available() -> None:
    prices = _price_frame(
        highs=[10.0, 13.0],
        lows=[8.0, 9.0],
        closes=[9.0, 12.0],
    )

    assert calculate_atr(prices, period=3) is None


@pytest.mark.parametrize("period", [0, -1])
def test_calculate_atr_rejects_invalid_period(period: int) -> None:
    prices = _price_frame(
        highs=[10.0, 13.0],
        lows=[8.0, 9.0],
        closes=[9.0, 12.0],
    )

    with pytest.raises(ValueError, match="period must be at least 1"):
        calculate_atr(prices, period=period)


@pytest.mark.parametrize(
    ("columns", "message"),
    [
        (("high", "close"), "missing required columns: low"),
        (("low", "close"), "missing required columns: high"),
        (("high", "low"), "missing required columns: close"),
    ],
)
def test_calculate_atr_rejects_missing_required_columns(
    columns: tuple[str, ...],
    message: str,
) -> None:
    prices = _price_frame(
        highs=[10.0, 13.0],
        lows=[8.0, 9.0],
        closes=[9.0, 12.0],
    ).loc[:, list(columns)]

    with pytest.raises(ValueError, match=message):
        calculate_atr(prices, period=1)


def test_calculate_atr_does_not_mutate_input_frame() -> None:
    prices = _price_frame(
        highs=[10.0, 15.0, 8.0, 12.0],
        lows=[8.0, 14.0, 5.0, 10.0],
        closes=[9.0, 14.5, 6.0, 11.0],
    )
    original = prices.copy(deep=True)

    calculate_atr(prices, period=4)

    pd.testing.assert_frame_equal(prices, original)


def test_calculate_atr_is_deterministic_for_same_input() -> None:
    prices = _price_frame(
        highs=[10.0, 15.0, 8.0, 12.0],
        lows=[8.0, 14.0, 5.0, 10.0],
        closes=[9.0, 14.5, 6.0, 11.0],
    )

    first = calculate_atr(prices, period=4)
    second = calculate_atr(prices, period=4)

    assert first == second
