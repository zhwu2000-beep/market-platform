"""ATR-based volatility utilities for price structure clustering."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

_REQUIRED_COLUMNS = ("high", "low", "close")


def calculate_atr(
    prices: pd.DataFrame,
    *,
    period: int,
) -> float | None:
    """Return the latest simple moving average ATR value.

    This uses simple moving average ATR as a deterministic normalization tool for
    price regions. It is not a trading signal.
    """

    normalized_period = _require_positive_int(period, "period")
    normalized = _normalize_price_frame(prices)
    if len(normalized) < normalized_period:
        return None

    true_ranges = _calculate_true_ranges(
        normalized["high"].tolist(),
        normalized["low"].tolist(),
        normalized["close"].tolist(),
    )
    return float(pd.Series(true_ranges).rolling(normalized_period).mean().iloc[-1])


def _calculate_true_ranges(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> list[float]:
    true_ranges: list[float] = []
    previous_close: float | None = None
    for high, low, close in zip(highs, lows, closes, strict=True):
        current_range = high - low
        if previous_close is not None:
            current_range = max(
                current_range,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(current_range)
        previous_close = close
    return true_ranges


def _normalize_price_frame(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")

    missing_columns = [
        column for column in _REQUIRED_COLUMNS if column not in prices.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Price frame is missing required columns: {missing}")

    normalized = prices.loc[:, list(_REQUIRED_COLUMNS)].copy()
    normalized["high"] = _normalize_numeric_column(normalized["high"], "high")
    normalized["low"] = _normalize_numeric_column(normalized["low"], "low")
    normalized["close"] = _normalize_numeric_column(normalized["close"], "close")

    return normalized.reset_index(drop=True)


def _normalize_numeric_column(series: pd.Series, column_name: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"Price frame contains invalid {column_name} values")
    if not numeric.map(math.isfinite).all():
        raise ValueError(f"Price frame contains non-finite {column_name} values")
    return numeric.astype(float)


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
    return value
