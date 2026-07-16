"""Deterministic orchestration for price structure analysis."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from numbers import Real

import pandas as pd

from market_platform.structure.clustering import cluster_price_levels
from market_platform.structure.models import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceStructureConfig,
    PriceStructureSnapshot,
    PriceStructureStatus,
    PriceZone,
    PriceZoneObservation,
)
from market_platform.structure.pivots import (
    detect_swing_highs,
    detect_swing_lows,
    filter_confirmed_pivots,
)
from market_platform.structure.touches import observe_price_zone
from market_platform.structure.volatility import calculate_atr

PivotDetector = Callable[..., tuple[PriceLevelCandidate, ...]]
AtrCalculator = Callable[..., float | None]
ZoneClusterer = Callable[..., tuple[PriceZone, ...]]
ZoneObserver = Callable[[pd.DataFrame, PriceZone], PriceZoneObservation]

_REQUIRED_COLUMNS = ("timestamp", "high", "low", "close")


class PriceStructureService:
    """Compose pivot, volatility, clustering, and touch analysis components."""

    def __init__(
        self,
        *,
        swing_high_detector: PivotDetector = detect_swing_highs,
        swing_low_detector: PivotDetector = detect_swing_lows,
        atr_calculator: AtrCalculator = calculate_atr,
        zone_clusterer: ZoneClusterer = cluster_price_levels,
        zone_observer: ZoneObserver = observe_price_zone,
    ) -> None:
        self._swing_high_detector = swing_high_detector
        self._swing_low_detector = swing_low_detector
        self._atr_calculator = atr_calculator
        self._zone_clusterer = zone_clusterer
        self._zone_observer = zone_observer

    def analyze(
        self,
        prices: pd.DataFrame,
        *,
        config: PriceStructureConfig | None = None,
        current_price: float | None = None,
        as_of: datetime | None = None,
    ) -> PriceStructureSnapshot:
        """Return structure facts using no price data later than the cutoff."""

        normalized = _normalize_price_frame(prices)
        normalized_config = _normalize_config(config)
        explicit_current_price = _normalize_current_price(current_price)
        requested_as_of = _normalize_analysis_as_of(as_of)
        if requested_as_of is not None:
            normalized = _filter_price_frame_as_of(normalized, requested_as_of)

        if normalized.empty:
            return PriceStructureSnapshot(
                status=PriceStructureStatus.INSUFFICIENT_DATA,
                as_of=requested_as_of,
                current_price=explicit_current_price,
            )

        snapshot_as_of = _to_datetime(normalized.iloc[-1]["timestamp"])
        confirmation_cutoff = (
            requested_as_of if requested_as_of is not None else snapshot_as_of
        )
        resolved_current_price = (
            explicit_current_price
            if explicit_current_price is not None
            else _require_current_price(normalized.iloc[-1]["close"])
        )

        minimum_bars = max(
            2 * normalized_config.pivot_window + 1,
            normalized_config.atr_period,
        )
        if len(normalized) < minimum_bars:
            return PriceStructureSnapshot(
                status=PriceStructureStatus.INSUFFICIENT_DATA,
                as_of=snapshot_as_of,
                current_price=resolved_current_price,
            )

        candidates = filter_confirmed_pivots(
            _sort_candidates(
                (
                    *self._swing_high_detector(
                        normalized,
                        window=normalized_config.pivot_window,
                    ),
                    *self._swing_low_detector(
                        normalized,
                        window=normalized_config.pivot_window,
                    ),
                )
            ),
            confirmation_cutoff,
        )
        if not candidates:
            return PriceStructureSnapshot(
                status=PriceStructureStatus.NO_PIVOTS,
                as_of=snapshot_as_of,
                current_price=resolved_current_price,
            )

        raw_atr = self._atr_calculator(
            normalized,
            period=normalized_config.atr_period,
        )
        atr = _usable_atr(raw_atr)
        if atr is None:
            return PriceStructureSnapshot(
                status=PriceStructureStatus.VOLATILITY_UNAVAILABLE,
                as_of=snapshot_as_of,
                current_price=resolved_current_price,
                atr=_snapshot_atr(raw_atr),
                candidates=candidates,
            )

        zones = self._zone_clusterer(
            candidates,
            atr=atr,
            atr_multiplier=normalized_config.zone_atr_multiplier,
        )
        observed_zones = tuple(
            ObservedPriceZone(
                zone=zone,
                observation=self._zone_observer(normalized, zone),
            )
            for zone in zones
        )

        return PriceStructureSnapshot(
            status=PriceStructureStatus.OK,
            as_of=snapshot_as_of,
            current_price=resolved_current_price,
            atr=atr,
            candidates=candidates,
            observed_zones=observed_zones,
        )


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

    for column in ("high", "low", "close"):
        normalized[column] = _normalize_numeric_column(normalized[column], column)

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


def _normalize_config(config: PriceStructureConfig | None) -> PriceStructureConfig:
    if config is None:
        return PriceStructureConfig()
    if not isinstance(config, PriceStructureConfig):
        raise TypeError("config must be a PriceStructureConfig or None")
    return config


def _normalize_current_price(value: object) -> float | None:
    if value is None:
        return None
    return _require_current_price(value)


def _normalize_analysis_as_of(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("as_of must be a datetime or None")
    if value.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _filter_price_frame_as_of(
    prices: pd.DataFrame,
    as_of: datetime,
) -> pd.DataFrame:
    return prices.loc[prices["timestamp"] <= pd.Timestamp(as_of)].reset_index(drop=True)


def _require_current_price(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("current_price must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("current_price must be finite")
    if numeric <= 0.0:
        raise ValueError("current_price must be greater than 0")
    return numeric


def _sort_candidates(
    candidates: Sequence[PriceLevelCandidate],
) -> tuple[PriceLevelCandidate, ...]:
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.occurred_at.isoformat(),
                candidate.confirmed_at.isoformat(),
                candidate.kind.value,
                candidate.price,
                candidate.source_method,
            ),
        )
    )


def _usable_atr(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        return None
    return numeric


def _snapshot_atr(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        return None
    return numeric


def _to_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
