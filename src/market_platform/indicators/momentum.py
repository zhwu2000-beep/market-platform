"""Generic provider-independent momentum indicators."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real
from typing import cast

from market_platform.indicators.trend import (
    _finite_float,
    _finite_real_sequence,
    _positive_period,
    calculate_ema,
)


@dataclass(frozen=True, slots=True)
class MacdSeries:
    """Aligned MACD line, signal, and histogram values."""

    macd: tuple[float | None, ...]
    signal: tuple[float | None, ...]
    histogram: tuple[float | None, ...]

    def __post_init__(self) -> None:
        lengths: set[int] = set()
        for name in ("macd", "signal", "histogram"):
            values = getattr(self, name)
            if type(values) is not tuple:
                raise TypeError(f"{name} must be an exact tuple")
            lengths.add(len(values))
            normalized: list[float | None] = []
            for value in values:
                if value is not None and type(value) is not float:
                    raise TypeError(f"{name} elements must be exact floats or None")
                normalized.append(
                    None if value is None else _finite_float(value, name)
                )
            object.__setattr__(self, name, tuple(normalized))
        if len(lengths) > 1:
            raise ValueError("MACD tuples must have equal lengths")


def calculate_macd(
    values: Sequence[Real],
    *,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> MacdSeries:
    """Return MACD using SMA-seeded exponential averages."""

    normalized = _finite_real_sequence(values, "values")
    _positive_period(fast_period, "fast_period")
    _positive_period(slow_period, "slow_period")
    _positive_period(signal_period, "signal_period")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")
    if not normalized:
        return MacdSeries((), (), ())
    fast = calculate_ema(cast(Sequence[Real], normalized), period=fast_period)
    slow = calculate_ema(cast(Sequence[Real], normalized), period=slow_period)
    macd: list[float | None] = [None] * len(normalized)
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow, strict=True)):
        if fast_value is not None and slow_value is not None:
            macd[index] = _finite_float(fast_value - slow_value, "MACD")
    signal: list[float | None] = [None] * len(normalized)
    histogram: list[float | None] = [None] * len(normalized)
    available = [
        (index, value) for index, value in enumerate(macd) if value is not None
    ]
    if len(available) >= signal_period:
        seed_index = available[signal_period - 1][0]
        previous = _finite_float(
            sum(value for _, value in available[:signal_period]) / signal_period,
            "MACD signal",
        )
        signal[seed_index] = previous
        macd_seed = macd[seed_index]
        assert macd_seed is not None
        histogram[seed_index] = _finite_float(
            macd_seed - previous,
            "MACD histogram",
        )
        alpha = 2.0 / (signal_period + 1)
        for index, current in available[signal_period:]:
            previous = _finite_float(
                current * alpha + previous * (1.0 - alpha),
                "MACD signal",
            )
            signal[index] = previous
            histogram[index] = _finite_float(current - previous, "MACD histogram")
    return MacdSeries(tuple(macd), tuple(signal), tuple(histogram))


def calculate_rsi(
    values: Sequence[Real],
    *,
    period: int,
) -> tuple[float | None, ...]:
    """Return Wilder RSI with its first value at close index period."""

    normalized = _finite_real_sequence(values, "values")
    _positive_period(period, "period")
    if not normalized:
        return ()
    result: list[float | None] = [None] * len(normalized)
    if len(normalized) <= period:
        return tuple(result)
    deltas = [
        _finite_float(current - previous, "RSI delta")
        for previous, current in zip(normalized, normalized[1:], strict=False)
    ]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    average_gain = _finite_float(sum(gains[:period]) / period, "RSI average gain")
    average_loss = _finite_float(sum(losses[:period]) / period, "RSI average loss")
    result[period] = _rsi_value(average_gain, average_loss)
    for delta_index in range(period, len(deltas)):
        average_gain = _finite_float(
            (average_gain * (period - 1) + gains[delta_index]) / period,
            "RSI average gain",
        )
        average_loss = _finite_float(
            (average_loss * (period - 1) + losses[delta_index]) / period,
            "RSI average loss",
        )
        result[delta_index + 1] = _rsi_value(average_gain, average_loss)
    return tuple(result)


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0.0:
        return 50.0 if average_gain == 0.0 else 100.0
    if average_gain == 0.0:
        return 0.0
    relative_strength = _finite_float(average_gain / average_loss, "RSI ratio")
    return _finite_float(100.0 - 100.0 / (1.0 + relative_strength), "RSI")
