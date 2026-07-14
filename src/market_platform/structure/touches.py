"""Independent price-zone touch observation utilities."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from numbers import Real

import pandas as pd

from market_platform.structure.models import PriceZone, PriceZoneObservation

_REQUIRED_COLUMNS = ("timestamp", "high", "low")


def observe_price_zone(
    prices: pd.DataFrame,
    zone: PriceZone,
) -> PriceZoneObservation:
    """Return independent touch statistics for a price zone.

    A touch occurs when a candle's high-low range intersects the zone.
    Repeated overlapping candles are counted as one independent touch until the
    price fully leaves the zone and then re-enters it.
    """

    normalized_zone = _require_price_zone(zone)
    normalized = _normalize_price_frame(prices)
    if normalized.empty:
        return PriceZoneObservation(0, None, None)

    touch_count = 0
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None
    inside_previous = False

    for row in normalized.itertuples(index=False):
        timestamp = _normalize_row_timestamp(row.timestamp)
        high = _normalize_row_number(row.high, "high")
        low = _normalize_row_number(row.low, "low")
        _validate_high_low_order(high=high, low=low)
        inside = _intersects_zone(high=high, low=low, zone=normalized_zone)
        if inside:
            if not inside_previous:
                touch_count += 1
                if first_observed_at is None:
                    first_observed_at = timestamp
                last_observed_at = timestamp
                inside_previous = True
        else:
            inside_previous = False

    return PriceZoneObservation(
        touch_count=touch_count,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
    )


def _require_price_zone(zone: object) -> PriceZone:
    if not isinstance(zone, PriceZone):
        raise TypeError("zone must be a PriceZone")
    return zone


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
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="coerce",
    )
    if normalized["timestamp"].isna().any():
        raise ValueError("Price frame contains invalid timestamp values")

    normalized["high"] = _normalize_numeric_column(normalized["high"], "high")
    normalized["low"] = _normalize_numeric_column(normalized["low"], "low")

    normalized = normalized.sort_values("timestamp", kind="stable", ignore_index=True)
    if normalized["timestamp"].duplicated().any():
        raise ValueError("Price frame must not contain duplicate timestamps")
    return normalized


def _normalize_numeric_column(series: pd.Series, column_name: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"Price frame contains invalid {column_name} values")
    if not numeric.map(math.isfinite).all():
        raise ValueError(f"Price frame contains non-finite {column_name} values")
    return numeric.astype(float)


def _normalize_row_timestamp(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return _to_datetime(value)
    if isinstance(value, datetime):
        return _to_datetime(value)
    raise TypeError("timestamp must be a datetime")


def _normalize_row_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    return numeric


def _validate_high_low_order(*, high: float, low: float) -> None:
    if high < low:
        raise ValueError("high must be greater than or equal to low")


def _intersects_zone(*, high: float, low: float, zone: PriceZone) -> bool:
    return low <= zone.upper_bound and high >= zone.lower_bound


def _to_datetime(value: datetime | pd.Timestamp) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
