from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, fields
from fractions import Fraction

import pytest

from market_platform import indicators
from market_platform.indicators import (
    MacdSeries,
    calculate_atr_percent,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_wilder_atr,
)

EXPECTED_EXPORTS = [
    "MacdSeries",
    "calculate_ema",
    "calculate_macd",
    "calculate_rsi",
    "calculate_wilder_atr",
    "calculate_atr_percent",
]


def test_indicator_public_api_and_macd_value_contract() -> None:
    assert indicators.__all__ == EXPECTED_EXPORTS
    assert [field.name for field in fields(MacdSeries)] == [
        "macd",
        "signal",
        "histogram",
    ]
    value = MacdSeries((1.0,), (None,), (None,))
    with pytest.raises(FrozenInstanceError):
        value.macd = ()  # type: ignore[misc]
    assert not hasattr(value, "__dict__")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"macd": [1.0], "signal": (None,), "histogram": (None,)},
        {"macd": (1,), "signal": (None,), "histogram": (None,)},
        {"macd": (math.nan,), "signal": (None,), "histogram": (None,)},
    ],
)
def test_macd_series_rejects_noncanonical_values(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        MacdSeries(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        MacdSeries((1.0,), (), ())


def test_ema_uses_sma_seed_and_exact_recurrence() -> None:
    assert calculate_ema([1, 2, 3, 4, 5], period=3) == (None, None, 2.0, 3.0, 4.0)
    assert calculate_ema([5, 5, 5, 5], period=2) == (None, 5.0, 5.0, 5.0)
    result = calculate_ema([1, 2, 3, 4], period=8)
    assert result == (None, None, None, None)
    assert calculate_ema([], period=3) == ()


def test_indicator_sequences_are_copied_and_real_subclasses_are_accepted() -> None:
    values = [Fraction(1), Fraction(2), Fraction(3)]
    result = calculate_ema(values, period=2)
    values[1] = Fraction(100)
    assert result == (None, 1.5, 2.5)
    assert all(value is None or type(value) is float for value in result)


@pytest.mark.parametrize("value", [True, False, math.nan, math.inf, -math.inf])
def test_ema_rejects_bool_and_nonfinite_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        calculate_ema([1.0, value], period=2)  # type: ignore[list-item]


@pytest.mark.parametrize("container", ["123", b"123", bytearray(b"123")])
def test_indicator_rejects_text_sequences(container: object) -> None:
    with pytest.raises(TypeError):
        calculate_ema(container, period=2)  # type: ignore[arg-type]


def test_indicator_rejects_generators() -> None:
    with pytest.raises(TypeError):
        calculate_ema((value for value in [1, 2]), period=2)  # type: ignore[arg-type]


class IntSubclass(int):
    pass


@pytest.mark.parametrize("period", [True, 0, -1, 1.0, IntSubclass(2)])
def test_indicator_period_validation(period: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        calculate_ema([1.0, 2.0], period=period)  # type: ignore[arg-type]


def test_macd_seed_positions_and_histogram() -> None:
    result = calculate_macd(
        [1, 2, 3, 4, 5, 6],
        fast_period=2,
        slow_period=3,
        signal_period=2,
    )
    assert result.macd == (None, None, 0.5, 0.5, 0.5, 0.5)
    assert result.signal == (None, None, None, 0.5, 0.5, 0.5)
    assert result.histogram == (None, None, None, 0.0, 0.0, 0.0)
    default = calculate_macd(
        tuple(float(value) for value in range(40)),
        fast_period=12,
        slow_period=26,
        signal_period=9,
    )
    assert default.macd[24] is None and default.macd[25] is not None
    assert default.signal[32] is None and default.signal[33] is not None


def test_macd_empty_and_invalid_period_relationship() -> None:
    assert calculate_macd(
        [], fast_period=2, slow_period=3, signal_period=2
    ) == MacdSeries((), (), ())
    with pytest.raises(ValueError):
        calculate_macd([1, 2], fast_period=3, slow_period=3, signal_period=2)


def test_wilder_rsi_reference_and_edges() -> None:
    result = calculate_rsi([1, 2, 3, 2, 4], period=2)
    assert result[:4] == (None, None, 100.0, 50.0)
    assert result[4] == pytest.approx(83.33333333333333)
    assert calculate_rsi([3, 2, 1], period=2)[-1] == 0.0
    assert calculate_rsi([1, 1, 1], period=2)[-1] == 50.0
    assert calculate_rsi([1, 2, 3], period=2)[-1] == 100.0
    assert calculate_rsi([1, 2], period=2) == (None, None)
    assert calculate_rsi([], period=2) == ()


def test_wilder_atr_uses_gap_true_range_seed_and_recurrence() -> None:
    result = calculate_wilder_atr(
        [10, 12, 13, 12],
        [8, 9, 11, 10],
        [9, 11, 12, 11],
        period=3,
    )
    assert result[:2] == (None, None)
    assert result[2] == pytest.approx(7.0 / 3.0)
    assert result[3] == pytest.approx(20.0 / 9.0)
    assert calculate_wilder_atr([], [], [], period=3) == ()


@pytest.mark.parametrize(
    ("highs", "lows", "closes"),
    [
        ([1], [], [1]),
        ([1], [2], [1]),
        ([0], [0], [0]),
        ([math.inf], [1], [1]),
    ],
)
def test_wilder_atr_rejects_invalid_ohlc(
    highs: list[float], lows: list[float], closes: list[float]
) -> None:
    with pytest.raises(ValueError):
        calculate_wilder_atr(highs, lows, closes, period=1)


def test_atr_percent_formula_none_propagation_and_negative_zero() -> None:
    assert calculate_atr_percent([None, 2], [10, 20]) == (None, 10.0)
    assert calculate_atr_percent([-0.0], [10]) == (0.0,)


@pytest.mark.parametrize(
    ("atr", "close", "error"),
    [
        ([1], [0], ValueError),
        ([1], [-1], ValueError),
        ([-1], [10], ValueError),
        ([math.nan], [10], ValueError),
        ([True], [10], TypeError),
    ],
)
def test_atr_percent_validation(
    atr: list[object], close: list[object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        calculate_atr_percent(atr, close)  # type: ignore[arg-type]


def test_atr_percent_requires_equal_lengths_and_sequences() -> None:
    with pytest.raises(ValueError):
        calculate_atr_percent([1], [1, 2])
    with pytest.raises(TypeError):
        calculate_atr_percent((value for value in [1]), [1])  # type: ignore[arg-type]


def test_macd_series_normalizes_direct_negative_zero_values() -> None:
    value = MacdSeries((-0.0,), (-0.0,), (-0.0,))
    for values in (value.macd, value.signal, value.histogram):
        for item in values:
            if item is not None:
                assert math.copysign(1.0, item) == 1.0


def test_macd_nonconstant_signal_reference_values() -> None:
    result = calculate_macd(
        [1, 2, 4, 8, 16, 32],
        fast_period=2,
        slow_period=3,
        signal_period=2,
    )
    assert result.macd[:2] == (None, None)
    assert result.macd[2:] == pytest.approx(
        (5.0 / 6.0, 11.0 / 9.0, 239.0 / 108.0, 2791.0 / 648.0)
    )
    assert result.signal[:3] == (None, None, None)
    assert result.signal[3:] == pytest.approx(
        (37.0 / 36.0, 589.0 / 324.0, 845.0 / 243.0)
    )
    assert result.histogram[:3] == (None, None, None)
    assert result.histogram[3:] == pytest.approx(
        (7.0 / 36.0, 32.0 / 81.0, 1613.0 / 1944.0)
    )
