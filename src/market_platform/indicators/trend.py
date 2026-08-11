"""Generic provider-independent trend indicators."""

from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real


def calculate_ema(
    values: Sequence[Real],
    *,
    period: int,
) -> tuple[float | None, ...]:
    """Return an EMA seeded with the first period values' arithmetic mean."""

    normalized = _finite_real_sequence(values, "values")
    _positive_period(period, "period")
    if not normalized:
        return ()
    result: list[float | None] = [None] * len(normalized)
    if len(normalized) < period:
        return tuple(result)
    previous = _finite_float(sum(normalized[:period]) / period, "EMA")
    result[period - 1] = previous
    alpha = 2.0 / (period + 1)
    for index in range(period, len(normalized)):
        previous = _finite_float(
            normalized[index] * alpha + previous * (1.0 - alpha),
            "EMA",
        )
        result[index] = previous
    return tuple(result)


def _finite_real_sequence(values: object, name: str) -> tuple[float, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a non-text Sequence")
    normalized: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{name} elements must be real numbers")
        normalized.append(_finite_float(float(value), name))
    return tuple(normalized)


def _positive_period(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an exact int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _finite_float(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return 0.0 if value == 0.0 else value
