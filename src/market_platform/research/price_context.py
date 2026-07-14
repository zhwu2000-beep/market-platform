"""Deterministic price context derived from research price levels."""

from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real

from market_platform.research.models import PriceContext, PriceLevel


def build_price_context(
    current_price: float,
    price_levels: Sequence[PriceLevel],
) -> PriceContext:
    """Return current price location relative to nearby research levels."""

    normalized_price = _normalize_current_price(current_price)
    levels = _normalize_price_levels(price_levels)

    supports = tuple(level for level in levels if level.level_type == "support")
    for support in supports:
        if support.upper > normalized_price:
            raise ValueError("support levels must not be above current_price")

    resistances = tuple(
        level for level in levels if level.level_type == "resistance"
    )
    for resistance in resistances:
        if resistance.lower < normalized_price:
            raise ValueError("resistance levels must not be below current_price")

    containing_levels = tuple(
        level for level in levels if level.level_type == "current_zone"
    )
    for level in containing_levels:
        if not level.lower <= normalized_price <= level.upper:
            raise ValueError("current_zone levels must contain current_price")

    nearest_support = min(
        supports,
        key=lambda level: normalized_price - level.upper,
        default=None,
    )
    nearest_resistance = min(
        resistances,
        key=lambda level: level.lower - normalized_price,
        default=None,
    )

    distance_to_support = (
        normalized_price - nearest_support.upper
        if nearest_support is not None
        else None
    )
    distance_to_resistance = (
        nearest_resistance.lower - normalized_price
        if nearest_resistance is not None
        else None
    )

    return PriceContext(
        current_price=normalized_price,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        containing_levels=containing_levels,
        distance_to_support=distance_to_support,
        distance_to_support_pct=(
            distance_to_support / normalized_price
            if distance_to_support is not None
            else None
        ),
        distance_to_resistance=distance_to_resistance,
        distance_to_resistance_pct=(
            distance_to_resistance / normalized_price
            if distance_to_resistance is not None
            else None
        ),
    )


def _normalize_current_price(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("current_price must be numeric")
    current_price = float(value)
    if not math.isfinite(current_price):
        raise ValueError("current_price must be finite")
    if current_price <= 0.0:
        raise ValueError("current_price must be greater than 0")
    return current_price


def _normalize_price_levels(
    values: object,
) -> tuple[PriceLevel, ...]:
    if isinstance(values, tuple):
        levels = values
    elif isinstance(values, list):
        levels = tuple(values)
    else:
        raise TypeError("price_levels must be a tuple or list")
    for level in levels:
        if not isinstance(level, PriceLevel):
            raise TypeError("price_levels elements must be PriceLevel instances")
    return levels
