from __future__ import annotations

import copy

import pytest

from market_platform.research import (
    PriceContext,
    PriceLevel,
    StructuralTargetDirection,
    build_structural_target_levels,
)


def _price_context(
    *,
    include_support: bool = True,
    include_resistance: bool = True,
    include_containing: bool = True,
) -> PriceContext:
    support = (
        PriceLevel(
            lower=90.0,
            upper=95.0,
            level_type="support",
            sources=("support_pivot", "support_cluster"),
        )
        if include_support
        else None
    )
    resistance = (
        PriceLevel(
            lower=107.0,
            upper=110.0,
            level_type="resistance",
            sources=("resistance_pivot",),
        )
        if include_resistance
        else None
    )
    containing = (
        (
            PriceLevel(
                lower=99.0,
                upper=101.0,
                level_type="current_zone",
                sources=("current_cluster",),
            ),
        )
        if include_containing
        else ()
    )
    return PriceContext(
        current_price=100.0,
        nearest_support=support,
        nearest_resistance=resistance,
        containing_levels=containing,
        distance_to_support=5.25 if support is not None else None,
        distance_to_support_pct=0.0525 if support is not None else None,
        distance_to_resistance=7.75 if resistance is not None else None,
        distance_to_resistance_pct=0.0775 if resistance is not None else None,
    )


def test_build_structural_target_levels_maps_downside_without_recalculation() -> None:
    context = _price_context(include_resistance=False)

    targets = build_structural_target_levels(context)

    assert len(targets) == 1
    assert targets[0].price == 95.0
    assert targets[0].direction is StructuralTargetDirection.DOWNSIDE
    assert targets[0].distance == 5.25
    assert targets[0].distance_pct == 0.0525
    assert targets[0].sources == ("support_pivot", "support_cluster")


def test_build_structural_target_levels_maps_upside_without_recalculation() -> None:
    context = _price_context(include_support=False)

    targets = build_structural_target_levels(context)

    assert len(targets) == 1
    assert targets[0].price == 107.0
    assert targets[0].direction is StructuralTargetDirection.UPSIDE
    assert targets[0].distance == 7.75
    assert targets[0].distance_pct == 0.0775
    assert targets[0].sources == ("resistance_pivot",)


def test_build_structural_target_levels_has_stable_downside_then_upside_order() -> None:
    targets = build_structural_target_levels(_price_context())

    assert tuple(target.direction for target in targets) == (
        StructuralTargetDirection.DOWNSIDE,
        StructuralTargetDirection.UPSIDE,
    )


def test_build_structural_target_levels_returns_empty_for_none() -> None:
    assert build_structural_target_levels(None) == ()


def test_containing_level_does_not_generate_structural_target() -> None:
    context = _price_context(include_support=False, include_resistance=False)

    assert context.containing_levels
    assert build_structural_target_levels(context) == ()


def test_build_structural_target_levels_does_not_modify_input() -> None:
    context = _price_context()
    original = copy.deepcopy(context)

    build_structural_target_levels(context)

    assert context == original


def test_build_structural_target_levels_is_deterministic() -> None:
    context = _price_context()

    assert build_structural_target_levels(context) == build_structural_target_levels(
        context
    )


@pytest.mark.parametrize(
    ("distance_field", "expected_message"),
    [
        ("distance_to_support", "distance_to_support must be provided"),
        ("distance_to_support_pct", "distance_to_support_pct must be provided"),
        ("distance_to_resistance", "distance_to_resistance must be provided"),
        ("distance_to_resistance_pct", "distance_to_resistance_pct must be provided"),
    ],
)
def test_build_structural_target_levels_fails_when_level_distance_is_missing(
    distance_field: str,
    expected_message: str,
) -> None:
    context = _price_context()
    object.__setattr__(context, distance_field, None)

    with pytest.raises(ValueError, match=expected_message):
        build_structural_target_levels(context)


def test_build_structural_target_levels_rejects_invalid_context_type() -> None:
    with pytest.raises(TypeError, match="price_context"):
        build_structural_target_levels("context")  # type: ignore[arg-type]
