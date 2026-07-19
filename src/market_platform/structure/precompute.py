"""Internal point-in-time price-structure precompute helpers."""

from __future__ import annotations

import pandas as pd

from market_platform.structure.clustering import cluster_price_levels
from market_platform.structure.models import (
    PriceStructureConfig,
    PriceStructureSnapshot,
)
from market_platform.structure.pivots import (
    _detect_swing_highs_normalized,
    _detect_swing_lows_normalized,
)
from market_platform.structure.service import (
    _normalize_config,
    _normalize_price_frame,
    _require_current_price,
    _sort_candidates,
    _structure_snapshot_from_normalized,
    _to_datetime,
)
from market_platform.structure.touches import observe_price_zone
from market_platform.structure.volatility import _calculate_atr_series_normalized


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

    snapshots: list[PriceStructureSnapshot] = []
    for position in range(len(normalized)):
        prefix = normalized.iloc[: position + 1]
        as_of = _to_datetime(normalized.iloc[position]["timestamp"])
        current_price = _require_current_price(normalized.iloc[position]["close"])
        snapshots.append(
            _structure_snapshot_from_normalized(
                prefix,
                config=normalized_config,
                current_price=current_price,
                snapshot_as_of=as_of,
                confirmation_cutoff=as_of,
                candidates=candidates,
                raw_atr=atr_series[position],
                zone_clusterer=cluster_price_levels,
                zone_observer=observe_price_zone,
            )
        )
    return tuple(snapshots)