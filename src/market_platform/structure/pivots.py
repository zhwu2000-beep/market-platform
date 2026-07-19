"""Swing pivot detection utilities."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime

import pandas as pd

from market_platform.structure.models import (
    PriceLevelCandidate,
    PriceLevelKind,
)

_REQUIRED_COLUMNS = ("timestamp", "high", "low")
_SOURCE_METHOD = "swing_pivot"


def detect_swing_highs(
    prices: pd.DataFrame,
    *,
    window: int,
) -> tuple[PriceLevelCandidate, ...]:
    """Return strictly-defined swing high candidates in timestamp order."""

    normalized = _normalize_price_frame(prices)
    normalized_window = _require_positive_int(window, "window")
    if len(normalized) < 2 * normalized_window + 1:
        return ()
    return _detect_swing_candidates(
        normalized,
        window=normalized_window,
        kind=PriceLevelKind.SWING_HIGH,
    )


def detect_swing_lows(
    prices: pd.DataFrame,
    *,
    window: int,
) -> tuple[PriceLevelCandidate, ...]:
    """Return strictly-defined swing low candidates in timestamp order."""

    normalized = _normalize_price_frame(prices)
    normalized_window = _require_positive_int(window, "window")
    if len(normalized) < 2 * normalized_window + 1:
        return ()
    return _detect_swing_candidates(
        normalized,
        window=normalized_window,
        kind=PriceLevelKind.SWING_LOW,
    )


def _detect_swing_highs_normalized(
    prices: pd.DataFrame,
    *,
    window: int,
) -> tuple[PriceLevelCandidate, ...]:
    normalized_window = _require_positive_int(window, "window")
    if len(prices) < 2 * normalized_window + 1:
        return ()
    return _detect_swing_candidates(
        prices,
        window=normalized_window,
        kind=PriceLevelKind.SWING_HIGH,
    )


def _detect_swing_lows_normalized(
    prices: pd.DataFrame,
    *,
    window: int,
) -> tuple[PriceLevelCandidate, ...]:
    normalized_window = _require_positive_int(window, "window")
    if len(prices) < 2 * normalized_window + 1:
        return ()
    return _detect_swing_candidates(
        prices,
        window=normalized_window,
        kind=PriceLevelKind.SWING_LOW,
    )

def filter_confirmed_pivots(
    pivots: Sequence[PriceLevelCandidate],
    as_of: datetime,
) -> tuple[PriceLevelCandidate, ...]:
    """Return pivots that were confirmed no later than the requested time."""

    if isinstance(pivots, (str, bytes, bytearray, dict)):
        raise TypeError("pivots must be a sequence of PriceLevelCandidate")
    if not isinstance(pivots, Sequence):
        raise TypeError("pivots must be a sequence of PriceLevelCandidate")
    normalized_as_of = _normalize_as_of(as_of)
    confirmed: list[PriceLevelCandidate] = []
    for pivot in pivots:
        if not isinstance(pivot, PriceLevelCandidate):
            raise TypeError("pivots must contain PriceLevelCandidate instances")
        if pivot.confirmed_at <= normalized_as_of:
            confirmed.append(pivot)
    return tuple(confirmed)


def _detect_swing_candidates(
    frame: pd.DataFrame,
    *,
    window: int,
    kind: PriceLevelKind,
) -> tuple[PriceLevelCandidate, ...]:
    pivot_prices = frame["high"] if kind is PriceLevelKind.SWING_HIGH else frame["low"]
    candidates: list[PriceLevelCandidate] = []
    values = pivot_prices.to_list()
    timestamps = frame["timestamp"].to_list()

    for index in range(window, len(frame) - window):
        current = values[index]
        left = values[index - window : index]
        right = values[index + 1 : index + window + 1]
        if kind is PriceLevelKind.SWING_HIGH:
            if all(current > value for value in left) and all(
                current > value for value in right
            ):
                candidates.append(
                    PriceLevelCandidate(
                        price=current,
                        kind=kind,
                        occurred_at=_to_datetime(timestamps[index]),
                        confirmed_at=_to_datetime(timestamps[index + window]),
                        source_method=_SOURCE_METHOD,
                    )
                )
        else:
            if all(current < value for value in left) and all(
                current < value for value in right
            ):
                candidates.append(
                    PriceLevelCandidate(
                        price=current,
                        kind=kind,
                        occurred_at=_to_datetime(timestamps[index]),
                        confirmed_at=_to_datetime(timestamps[index + window]),
                        source_method=_SOURCE_METHOD,
                    )
                )

    return tuple(candidates)


def _normalize_price_frame(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")

    missing_columns = [
        column
        for column in _REQUIRED_COLUMNS
        if column not in prices.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Price frame is missing required columns: {missing}")

    normalized = prices.loc[:, list(_REQUIRED_COLUMNS)].copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="coerce",
    )
    if normalized["timestamp"].isna().any():
        raise ValueError("Price frame contains invalid timestamp values")

    normalized["high"] = _normalize_numeric_column(normalized["high"], "high")
    normalized["low"] = _normalize_numeric_column(normalized["low"], "low")

    if (normalized["high"] < normalized["low"]).any():
        raise ValueError("high must be greater than or equal to low")

    normalized = normalized.sort_values("timestamp", kind="stable", ignore_index=True)
    if normalized["timestamp"].duplicated().any():
        raise ValueError("Price frame must not contain duplicate timestamps")
    return normalized


def _normalize_numeric_column(series: pd.Series, column_name: str) -> pd.Series:
    if series.map(lambda value: isinstance(value, bool)).any():
        raise TypeError(f"{column_name} must be numeric")
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"Price frame contains invalid {column_name} values")
    if not numeric.map(math.isfinite).all():
        raise ValueError(f"Price frame contains non-finite {column_name} values")
    return numeric.astype(float)


def _to_datetime(value: datetime | pd.Timestamp) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_as_of(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("as_of must be a datetime")
    if value.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
    return value
