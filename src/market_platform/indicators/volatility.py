"""Generic provider-independent volatility indicators."""

from __future__ import annotations

from collections.abc import Sequence
from numbers import Real

from market_platform.indicators.trend import (
    _finite_float,
    _finite_real_sequence,
    _positive_period,
)


def calculate_wilder_atr(
    highs: Sequence[Real],
    lows: Sequence[Real],
    closes: Sequence[Real],
    *,
    period: int,
) -> tuple[float | None, ...]:
    """Return Wilder average true range for aligned OHLC sequences."""

    normalized_highs = _finite_real_sequence(highs, "highs")
    normalized_lows = _finite_real_sequence(lows, "lows")
    normalized_closes = _finite_real_sequence(closes, "closes")
    _positive_period(period, "period")
    if not (len(normalized_highs) == len(normalized_lows) == len(normalized_closes)):
        raise ValueError("highs, lows, and closes must have equal lengths")
    if not normalized_highs:
        return ()
    true_ranges: list[float] = []
    for index, (high, low, close) in enumerate(
        zip(normalized_highs, normalized_lows, normalized_closes, strict=True)
    ):
        if high <= 0.0 or low <= 0.0 or close <= 0.0:
            raise ValueError("OHLC values must be positive")
        if high < low:
            raise ValueError("high must be greater than or equal to low")
        if index == 0:
            true_range = high - low
        else:
            previous_close = normalized_closes[index - 1]
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(_finite_float(true_range, "true range"))
    result: list[float | None] = [None] * len(true_ranges)
    if len(true_ranges) < period:
        return tuple(result)
    previous = _finite_float(sum(true_ranges[:period]) / period, "Wilder ATR")
    result[period - 1] = previous
    for index in range(period, len(true_ranges)):
        previous = _finite_float(
            (previous * (period - 1) + true_ranges[index]) / period,
            "Wilder ATR",
        )
        result[index] = previous
    return tuple(result)


def calculate_atr_percent(
    atr_values: Sequence[Real | None],
    closes: Sequence[Real],
) -> tuple[float | None, ...]:
    """Return aligned ATR values as percentages of closing price."""

    if not isinstance(atr_values, Sequence) or isinstance(
        atr_values, (str, bytes, bytearray)
    ):
        raise TypeError("atr_values must be a non-text Sequence")
    normalized_closes = _finite_real_sequence(closes, "closes")
    if len(atr_values) != len(normalized_closes):
        raise ValueError("atr_values and closes must have equal lengths")
    result: list[float | None] = []
    for atr, close in zip(atr_values, normalized_closes, strict=True):
        if close <= 0.0:
            raise ValueError("closes must be positive")
        if atr is None:
            result.append(None)
            continue
        if isinstance(atr, bool) or not isinstance(atr, Real):
            raise TypeError("atr_values elements must be real numbers or None")
        numeric_atr = _finite_float(float(atr), "atr_values")
        if numeric_atr < 0.0:
            raise ValueError("atr_values must not be negative")
        result.append(_finite_float(100.0 * numeric_atr / close, "ATR percent"))
    return tuple(result)
