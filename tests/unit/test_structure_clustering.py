from __future__ import annotations

from datetime import UTC, datetime

import pytest

from market_platform.structure import (
    PriceLevelCandidate,
    PriceLevelKind,
    PriceZone,
    cluster_price_levels,
    create_price_zone,
)


def _candidate(
    price: float,
    kind: PriceLevelKind,
    observed_at: datetime,
    source_method: str = "swing_pivot",
) -> PriceLevelCandidate:
    return PriceLevelCandidate(
        price=price,
        kind=kind,
        observed_at=observed_at,
        source_method=source_method,
    )


def test_cluster_price_levels_returns_empty_tuple_for_empty_input() -> None:
    assert cluster_price_levels([], atr=2.0, atr_multiplier=0.25) == ()


def test_create_price_zone_sorts_candidates_and_dedupes_source_methods() -> None:
    candidates = [
        _candidate(
            102.0,
            PriceLevelKind.SWING_LOW,
            datetime(2026, 1, 3, tzinfo=UTC),
            "manual",
        ),
        _candidate(
            100.0,
            PriceLevelKind.SWING_HIGH,
            datetime(2026, 1, 1, tzinfo=UTC),
            "swing_pivot",
        ),
        _candidate(
            101.0,
            PriceLevelKind.SWING_LOW,
            datetime(2026, 1, 2, tzinfo=UTC),
            "manual",
        ),
    ]

    zone = create_price_zone(candidates)

    assert zone.lower_bound == 100.0
    assert zone.upper_bound == 102.0
    assert zone.midpoint == 101.0
    assert [candidate.observed_at for candidate in zone.candidates] == [
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2026, 1, 3, tzinfo=UTC),
    ]
    assert zone.source_methods == ("swing_pivot", "manual")


def test_create_price_zone_is_deterministic_for_input_reordering() -> None:
    ordered = [
        _candidate(
            100.0,
            PriceLevelKind.SWING_HIGH,
            datetime(2026, 1, 1, tzinfo=UTC),
            "swing_pivot",
        ),
        _candidate(
            101.0,
            PriceLevelKind.SWING_LOW,
            datetime(2026, 1, 2, tzinfo=UTC),
            "manual",
        ),
        _candidate(
            102.0,
            PriceLevelKind.SWING_HIGH,
            datetime(2026, 1, 3, tzinfo=UTC),
            "manual",
        ),
    ]
    shuffled = [ordered[2], ordered[0], ordered[1]]

    assert create_price_zone(ordered) == create_price_zone(shuffled)


def test_cluster_price_levels_merges_within_tolerance_and_on_boundary() -> None:
    candidates = [
        _candidate(100.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.4, PriceLevelKind.SWING_LOW, datetime(2026, 1, 2, tzinfo=UTC)),
        _candidate(100.5, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 3, tzinfo=UTC)),
    ]

    zones = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)

    assert len(zones) == 1
    zone = zones[0]
    assert zone.lower_bound == 100.0
    assert zone.upper_bound == 100.5
    assert zone.midpoint == pytest.approx(100.25)
    assert zone.candidates == tuple(
        sorted(candidates, key=lambda item: item.observed_at)
    )


def test_cluster_price_levels_uses_single_linkage_chain_semantics() -> None:
    candidates = [
        _candidate(100.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.4, PriceLevelKind.SWING_LOW, datetime(2026, 1, 2, tzinfo=UTC)),
        _candidate(100.8, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 3, tzinfo=UTC)),
    ]

    zones = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)

    assert len(zones) == 1
    assert zones[0].lower_bound == 100.0
    assert zones[0].upper_bound == 100.8
    assert zones[0].midpoint == pytest.approx(100.4)


def test_cluster_price_levels_separates_candidates_outside_tolerance() -> None:
    candidates = [
        _candidate(100.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.4, PriceLevelKind.SWING_LOW, datetime(2026, 1, 2, tzinfo=UTC)),
        _candidate(101.2, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 3, tzinfo=UTC)),
    ]

    zones = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)

    assert len(zones) == 2
    assert [zone.midpoint for zone in zones] == [100.2, 101.2]


def test_cluster_price_levels_is_input_order_independent_and_stable() -> None:
    candidates = [
        _candidate(201.0, PriceLevelKind.SWING_LOW, datetime(2026, 1, 4, tzinfo=UTC)),
        _candidate(100.2, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.5, PriceLevelKind.SWING_LOW, datetime(2026, 1, 2, tzinfo=UTC)),
        _candidate(201.4, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 5, tzinfo=UTC)),
    ]

    zones = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)

    assert [zone.midpoint for zone in zones] == [100.35, 201.2]
    assert [candidate.price for candidate in zones[0].candidates] == [100.2, 100.5]
    assert [candidate.price for candidate in zones[1].candidates] == [201.0, 201.4]


def test_cluster_price_levels_keeps_different_kinds_in_same_zone() -> None:
    candidates = [
        _candidate(100.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.3, PriceLevelKind.SWING_LOW, datetime(2026, 1, 2, tzinfo=UTC)),
    ]

    zones = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)

    assert len(zones) == 1
    assert {candidate.kind for candidate in zones[0].candidates} == {
        PriceLevelKind.SWING_HIGH,
        PriceLevelKind.SWING_LOW,
    }


@pytest.mark.parametrize(
    ("atr", "multiplier", "message"),
    [
        (0.0, 0.5, "atr must be greater than 0"),
        (-1.0, 0.5, "atr must be greater than 0"),
        (1.0, 0.0, "atr_multiplier must be greater than 0"),
        (1.0, -0.1, "atr_multiplier must be greater than 0"),
    ],
)
def test_cluster_price_levels_rejects_invalid_atr_inputs(
    atr: float,
    multiplier: float,
    message: str,
) -> None:
    candidates = [
        _candidate(100.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
    ]

    with pytest.raises(ValueError, match=message):
        cluster_price_levels(candidates, atr=atr, atr_multiplier=multiplier)


def test_cluster_price_levels_does_not_mutate_input_sequence() -> None:
    candidates = [
        _candidate(100.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.4, PriceLevelKind.SWING_LOW, datetime(2026, 1, 2, tzinfo=UTC)),
        _candidate(101.5, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 3, tzinfo=UTC)),
    ]
    original = list(candidates)

    cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)

    assert candidates == original


def test_cluster_price_levels_preserves_all_candidates_without_duplication() -> None:
    candidates = [
        _candidate(100.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.2, PriceLevelKind.SWING_LOW, datetime(2026, 1, 2, tzinfo=UTC)),
        _candidate(101.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 3, tzinfo=UTC)),
        _candidate(103.0, PriceLevelKind.SWING_LOW, datetime(2026, 1, 4, tzinfo=UTC)),
    ]

    zones = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)
    flattened = [candidate for zone in zones for candidate in zone.candidates]

    assert len(flattened) == len(candidates)
    assert sorted(candidate.price for candidate in flattened) == sorted(
        candidate.price for candidate in candidates
    )


def test_cluster_price_levels_orders_zones_by_midpoint() -> None:
    candidates = [
        _candidate(202.0, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 4, tzinfo=UTC)),
        _candidate(100.0, PriceLevelKind.SWING_LOW, datetime(2026, 1, 1, tzinfo=UTC)),
        _candidate(100.4, PriceLevelKind.SWING_HIGH, datetime(2026, 1, 2, tzinfo=UTC)),
        _candidate(202.4, PriceLevelKind.SWING_LOW, datetime(2026, 1, 5, tzinfo=UTC)),
    ]

    zones = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)

    assert [zone.midpoint for zone in zones] == [100.2, 202.2]


def test_cluster_price_levels_uses_zone_bounds_midpoint_and_source_methods() -> None:
    candidates = [
        _candidate(
            100.0,
            PriceLevelKind.SWING_HIGH,
            datetime(2026, 1, 1, tzinfo=UTC),
            "swing_pivot",
        ),
        _candidate(
            100.3,
            PriceLevelKind.SWING_LOW,
            datetime(2026, 1, 2, tzinfo=UTC),
            "manual",
        ),
        _candidate(
            100.4,
            PriceLevelKind.SWING_LOW,
            datetime(2026, 1, 3, tzinfo=UTC),
            "manual",
        ),
    ]

    zone = cluster_price_levels(candidates, atr=1.0, atr_multiplier=0.5)[0]

    assert isinstance(zone, PriceZone)
    assert zone.lower_bound == 100.0
    assert zone.upper_bound == 100.4
    assert zone.midpoint == pytest.approx(100.2)
    assert zone.source_methods == ("swing_pivot", "manual")
