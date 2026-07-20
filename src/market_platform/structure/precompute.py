"""Internal point-in-time price-structure precompute helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
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
    _detect_swing_highs_normalized,
    _detect_swing_lows_normalized,
    filter_confirmed_pivots,
)
from market_platform.structure.service import (
    _normalize_config,
    _normalize_price_frame,
    _require_current_price,
    _snapshot_atr,
    _sort_candidates,
    _to_datetime,
    _usable_atr,
)
from market_platform.structure.volatility import _calculate_atr_series_normalized

_TouchKey = tuple[float, float]


@dataclass(frozen=True, slots=True)
class _TouchObservationSeries:
    counts: np.ndarray[Any, np.dtype[np.int64]]
    last_entry_indices: np.ndarray[Any, np.dtype[np.int64]]
    first_entry_index: int | None
    array_bytes: int

    def observation_at(
        self,
        timestamps: tuple[datetime, ...],
        position: int,
    ) -> PriceZoneObservation:
        if position < 0 or position >= len(self.counts):
            raise IndexError("position out of range")
        touch_count = int(self.counts[position])
        if touch_count == 0:
            return PriceZoneObservation(0, None, None)
        if self.first_entry_index is None:
            raise ValueError("touch series has count without first entry")
        last_entry_index = int(self.last_entry_indices[position])
        return PriceZoneObservation(
            touch_count=touch_count,
            first_observed_at=timestamps[self.first_entry_index],
            last_observed_at=timestamps[last_entry_index],
        )


def precompute_price_structure_snapshots(
    prices: pd.DataFrame,
    *,
    config: PriceStructureConfig | None = None,
) -> tuple[PriceStructureSnapshot, ...]:
    """Return default point-in-time structure snapshots for each full-frame row."""

    normalized = _normalize_price_frame(prices)
    if normalized.empty:
        return ()

    normalized_config = _normalize_config(config)
    candidates = _sort_candidates(
        (
            *_detect_swing_highs_normalized(
                normalized,
                window=normalized_config.pivot_window,
            ),
            *_detect_swing_lows_normalized(
                normalized,
                window=normalized_config.pivot_window,
            ),
        )
    )
    atr_series = _calculate_atr_series_normalized(
        normalized,
        period=normalized_config.atr_period,
    )
    timestamps = tuple(_to_datetime(value) for value in normalized["timestamp"])
    touch_states: dict[_TouchKey, _TouchObservationSeries] = {}

    snapshots: list[PriceStructureSnapshot] = []
    for position in range(len(normalized)):
        prefix = normalized.iloc[: position + 1]
        as_of = timestamps[position]
        current_price = _require_current_price(normalized.iloc[position]["close"])
        snapshots.append(
            _structure_snapshot_from_normalized_with_touch_state(
                prefix,
                full_frame=normalized,
                timestamps=timestamps,
                position=position,
                touch_states=touch_states,
                config=normalized_config,
                current_price=current_price,
                snapshot_as_of=as_of,
                confirmation_cutoff=as_of,
                candidates=candidates,
                raw_atr=atr_series[position],
            )
        )
    return tuple(snapshots)


def _structure_snapshot_from_normalized_with_touch_state(
    prices: pd.DataFrame,
    *,
    full_frame: pd.DataFrame,
    timestamps: tuple[datetime, ...],
    position: int,
    touch_states: dict[_TouchKey, _TouchObservationSeries],
    config: PriceStructureConfig,
    current_price: float,
    snapshot_as_of: datetime,
    confirmation_cutoff: datetime,
    candidates: tuple[PriceLevelCandidate, ...],
    raw_atr: float | None,
) -> PriceStructureSnapshot:
    minimum_bars = max(
        2 * config.pivot_window + 1,
        config.atr_period,
    )
    if len(prices) < minimum_bars:
        return PriceStructureSnapshot(
            status=PriceStructureStatus.INSUFFICIENT_DATA,
            as_of=snapshot_as_of,
            current_price=current_price,
        )

    confirmed_candidates = filter_confirmed_pivots(candidates, confirmation_cutoff)
    if not confirmed_candidates:
        return PriceStructureSnapshot(
            status=PriceStructureStatus.NO_PIVOTS,
            as_of=snapshot_as_of,
            current_price=current_price,
        )

    atr = _usable_atr(raw_atr)
    if atr is None:
        return PriceStructureSnapshot(
            status=PriceStructureStatus.VOLATILITY_UNAVAILABLE,
            as_of=snapshot_as_of,
            current_price=current_price,
            atr=_snapshot_atr(raw_atr),
            candidates=confirmed_candidates,
        )

    zones = cluster_price_levels(
        confirmed_candidates,
        atr=atr,
        atr_multiplier=config.zone_atr_multiplier,
    )
    observed_zones = tuple(
        ObservedPriceZone(
            zone=zone,
            observation=_observe_zone_with_touch_state(
                full_frame,
                timestamps=timestamps,
                position=position,
                touch_states=touch_states,
                zone=zone,
            ),
        )
        for zone in zones
    )

    return PriceStructureSnapshot(
        status=PriceStructureStatus.OK,
        as_of=snapshot_as_of,
        current_price=current_price,
        atr=atr,
        candidates=confirmed_candidates,
        observed_zones=observed_zones,
    )


def _observe_zone_with_touch_state(
    prices: pd.DataFrame,
    *,
    timestamps: tuple[datetime, ...],
    position: int,
    touch_states: dict[_TouchKey, _TouchObservationSeries],
    zone: PriceZone,
) -> PriceZoneObservation:
    key = _touch_key(zone)
    series = touch_states.get(key)
    if series is None:
        series = _build_touch_observation_series(
            prices,
            lower_bound=key[0],
            upper_bound=key[1],
        )
        touch_states[key] = series
    return _touch_observation_at_position(series, timestamps, position)


def _touch_key(zone: PriceZone) -> _TouchKey:
    return (float(zone.lower_bound), float(zone.upper_bound))


def _build_touch_observation_series(
    prices: pd.DataFrame,
    *,
    lower_bound: float,
    upper_bound: float,
) -> _TouchObservationSeries:
    highs = prices["high"].to_numpy(dtype=float, copy=False)
    lows = prices["low"].to_numpy(dtype=float, copy=False)
    inside = (lows <= upper_bound) & (highs >= lower_bound)
    previous_inside = np.empty_like(inside)
    if len(inside) == 0:
        previous_inside = inside
    else:
        previous_inside[0] = False
        previous_inside[1:] = inside[:-1]
    entries = inside & ~previous_inside
    counts = np.cumsum(entries, dtype=np.int64)
    entry_indices = np.flatnonzero(entries)
    first_entry_index = int(entry_indices[0]) if len(entry_indices) else None
    last_entry_indices = np.maximum.accumulate(
        np.where(entries, np.arange(len(entries), dtype=np.int64), np.int64(-1))
    )
    counts.setflags(write=False)
    last_entry_indices.setflags(write=False)
    array_bytes = int(counts.nbytes + last_entry_indices.nbytes)
    return _TouchObservationSeries(
        counts=counts,
        last_entry_indices=last_entry_indices,
        first_entry_index=first_entry_index,
        array_bytes=array_bytes,
    )


def _touch_observation_at_position(
    series: _TouchObservationSeries,
    timestamps: tuple[datetime, ...],
    position: int,
) -> PriceZoneObservation:
    return series.observation_at(timestamps, position)
