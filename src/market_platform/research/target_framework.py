"""Deterministic structural target construction."""

from __future__ import annotations

from market_platform.research.models import (
    PriceContext,
    StructuralTargetDirection,
    StructuralTargetLevel,
)


def build_structural_target_levels(
    price_context: PriceContext | None,
) -> tuple[StructuralTargetLevel, ...]:
    """Build ordered structural target facts from an existing price context."""
    if price_context is None:
        return ()
    if not isinstance(price_context, PriceContext):
        raise TypeError("price_context must be a PriceContext or None")

    targets: list[StructuralTargetLevel] = []
    if price_context.nearest_support is not None:
        targets.append(
            StructuralTargetLevel(
                price=price_context.nearest_support.upper,
                direction=StructuralTargetDirection.DOWNSIDE,
                distance=_require_context_distance(
                    price_context.distance_to_support,
                    "distance_to_support",
                ),
                distance_pct=_require_context_distance(
                    price_context.distance_to_support_pct,
                    "distance_to_support_pct",
                ),
                sources=price_context.nearest_support.sources,
            )
        )
    if price_context.nearest_resistance is not None:
        targets.append(
            StructuralTargetLevel(
                price=price_context.nearest_resistance.lower,
                direction=StructuralTargetDirection.UPSIDE,
                distance=_require_context_distance(
                    price_context.distance_to_resistance,
                    "distance_to_resistance",
                ),
                distance_pct=_require_context_distance(
                    price_context.distance_to_resistance_pct,
                    "distance_to_resistance_pct",
                ),
                sources=price_context.nearest_resistance.sources,
            )
        )
    return tuple(targets)


def _require_context_distance(value: float | None, field_name: str) -> float:
    if value is None:
        raise ValueError(f"{field_name} must be provided when its level exists")
    return value
