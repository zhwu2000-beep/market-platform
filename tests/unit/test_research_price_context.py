from __future__ import annotations

import pytest

from market_platform.research import PriceContext, PriceLevel, build_price_context


def _level(
    lower: float,
    upper: float,
    level_type: str,
    source: str,
) -> PriceLevel:
    return PriceLevel(
        lower=lower,
        upper=upper,
        level_type=level_type,
        sources=(source,),
    )


def test_build_price_context_selects_nearest_levels_and_calculates_distances() -> None:
    far_support = _level(80.0, 85.0, "support", "far_support")
    near_support = _level(90.0, 95.0, "support", "near_support")
    current_lower = _level(98.0, 100.0, "current_zone", "current_lower")
    current_upper = _level(100.0, 102.0, "current_zone", "current_upper")
    far_resistance = _level(115.0, 120.0, "resistance", "far_resistance")
    near_resistance = _level(105.0, 110.0, "resistance", "near_resistance")

    context = build_price_context(
        100.0,
        (
            far_support,
            current_upper,
            far_resistance,
            near_support,
            current_lower,
            near_resistance,
        ),
    )

    assert isinstance(context, PriceContext)
    assert context.current_price == 100.0
    assert context.nearest_support is near_support
    assert context.nearest_resistance is near_resistance
    assert context.containing_levels == (current_upper, current_lower)
    assert context.distance_to_support == pytest.approx(5.0)
    assert context.distance_to_support_pct == pytest.approx(0.05)
    assert context.distance_to_resistance == pytest.approx(5.0)
    assert context.distance_to_resistance_pct == pytest.approx(0.05)


def test_build_price_context_handles_missing_nearby_levels() -> None:
    context = build_price_context(
        100.0,
        (_level(100.0, 100.0, "reference", "reference"),),
    )

    assert context.nearest_support is None
    assert context.nearest_resistance is None
    assert context.containing_levels == ()
    assert context.distance_to_support is None
    assert context.distance_to_support_pct is None
    assert context.distance_to_resistance is None
    assert context.distance_to_resistance_pct is None


@pytest.mark.parametrize(
    "current_price",
    [True, 0.0, -1.0, float("nan"), float("inf"), "100"],
)
def test_build_price_context_rejects_invalid_current_price(
    current_price: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="current_price"):
        build_price_context(current_price, ())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "price_levels",
    ["levels", {"support": 95.0}, (_level(90.0, 95.0, "support", "support"), "bad")],
)
def test_build_price_context_rejects_invalid_level_containers(
    price_levels: object,
) -> None:
    with pytest.raises(TypeError, match="price_levels"):
        build_price_context(100.0, price_levels)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "level",
    [
        _level(101.0, 102.0, "support", "support"),
        _level(98.0, 99.0, "resistance", "resistance"),
        _level(90.0, 95.0, "current_zone", "current"),
    ],
)
def test_build_price_context_rejects_inconsistent_level_locations(
    level: PriceLevel,
) -> None:
    with pytest.raises(ValueError):
        build_price_context(100.0, (level,))
