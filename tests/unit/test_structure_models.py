from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from market_platform.structure import (
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureConfig,
    PriceZone,
)


def test_price_structure_config_defaults_to_stage_two_values() -> None:
    config = PriceStructureConfig()

    assert config.pivot_window == 3
    assert config.atr_period == 14
    assert config.zone_atr_multiplier == 0.25


def test_price_structure_config_accepts_custom_values() -> None:
    config = PriceStructureConfig(
        pivot_window=5,
        atr_period=21,
        zone_atr_multiplier=0.5,
    )

    assert config.pivot_window == 5
    assert config.atr_period == 21
    assert config.zone_atr_multiplier == 0.5


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("pivot_window", 0, "pivot_window must be at least 1"),
        ("pivot_window", -1, "pivot_window must be at least 1"),
        ("atr_period", 0, "atr_period must be at least 1"),
        ("atr_period", -1, "atr_period must be at least 1"),
        (
            "zone_atr_multiplier",
            0.0,
            "zone_atr_multiplier must be greater than 0",
        ),
        (
            "zone_atr_multiplier",
            -0.1,
            "zone_atr_multiplier must be greater than 0",
        ),
    ],
)
def test_price_structure_config_rejects_invalid_values(
    field_name: str,
    value: object,
    message: str,
) -> None:
    kwargs = {
        "pivot_window": 3,
        "atr_period": 14,
        "zone_atr_multiplier": 0.25,
    }
    kwargs[field_name] = value

    with pytest.raises((TypeError, ValueError), match=message):
        PriceStructureConfig(**kwargs)


def test_price_level_candidate_is_frozen_and_normalizes_timestamp() -> None:
    candidate = PriceLevelCandidate(
        price=123.45,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=8))),
    )

    assert candidate.price == 123.45
    assert candidate.observed_at == datetime(2026, 1, 1, 1, tzinfo=UTC)
    assert candidate.source_method == "swing_pivot"

    with pytest.raises(FrozenInstanceError):
        candidate.price = 99.0  # type: ignore[misc]


def test_price_level_candidate_rejects_invalid_kind() -> None:
    with pytest.raises(TypeError, match="kind must be a PriceLevelKind"):
        PriceLevelCandidate(
            price=123.45,
            kind="swing_high",  # type: ignore[arg-type]
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_price_zone_is_frozen_and_validates_invariants() -> None:
    candidate = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    zone = PriceZone(
        lower_bound=99.5,
        upper_bound=100.5,
        midpoint=100.0,
        candidates=(candidate,),
        source_methods=("swing_pivot",),
    )

    assert zone.lower_bound == 99.5
    assert zone.upper_bound == 100.5
    assert zone.midpoint == 100.0
    assert zone.candidates == (candidate,)
    assert zone.source_methods == ("swing_pivot",)

    with pytest.raises(FrozenInstanceError):
        zone.midpoint = 101.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "lower_bound": 100.0,
                "upper_bound": 99.0,
                "midpoint": 99.5,
                "candidates": (),
                "source_methods": (),
            },
            "lower_bound must be less than or equal to upper_bound",
        ),
        (
            {
                "lower_bound": 99.0,
                "upper_bound": 100.0,
                "midpoint": 100.5,
                "candidates": (),
                "source_methods": (),
            },
            r"midpoint must be within \[lower_bound, upper_bound\]",
        ),
        (
            {
                "lower_bound": 99.0,
                "upper_bound": 100.0,
                "midpoint": 99.5,
                "candidates": (),
                "source_methods": (),
            },
            "candidates must not be empty",
        ),
    ],
)
def test_price_zone_rejects_invalid_direct_construction(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        PriceZone(**kwargs)


def test_price_zone_rejects_candidates_outside_bounds() -> None:
    candidate = PriceLevelCandidate(
        price=101.0,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="candidates must stay within the zone bounds"):
        PriceZone(
            lower_bound=99.0,
            upper_bound=100.0,
            midpoint=99.5,
            candidates=(candidate,),
            source_methods=("swing_pivot",),
        )
