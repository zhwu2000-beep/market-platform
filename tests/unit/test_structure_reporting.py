from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from market_platform.structure.models import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureSnapshot,
    PriceStructureStatus,
    PriceZone,
    PriceZoneObservation,
)
from market_platform.structure.reporting import snapshot_to_dict


def _ok_snapshot(*, reversed_order: bool = False) -> PriceStructureSnapshot:
    first_at = datetime(2026, 1, 2, tzinfo=UTC)
    second_at = first_at + timedelta(days=1)
    first = PriceLevelCandidate(
        price=99.0,
        kind=PriceLevelKind.SWING_LOW,
        observed_at=first_at,
        source_method="method_b",
    )
    second = PriceLevelCandidate(
        price=101.0,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=second_at,
        source_method="method_a",
    )
    zone_candidates = (second, first) if reversed_order else (first, second)
    source_methods = (
        ("method_b", "method_a")
        if reversed_order
        else ("method_a", "method_b")
    )
    observed = ObservedPriceZone(
        zone=PriceZone(
            lower_bound=99.0,
            upper_bound=101.0,
            midpoint=100.0,
            candidates=zone_candidates,
            source_methods=source_methods,
        ),
        observation=PriceZoneObservation(
            touch_count=2,
            first_observed_at=first_at,
            last_observed_at=second_at,
        ),
    )
    return PriceStructureSnapshot(
        status=PriceStructureStatus.OK,
        as_of=datetime(2026, 1, 4, tzinfo=UTC),
        current_price=100.0,
        atr=2.5,
        candidates=(second, first),
        observed_zones=(observed,),
    )


def test_snapshot_to_dict_serializes_ok_snapshot() -> None:
    result = snapshot_to_dict(_ok_snapshot())

    assert result["status"] == "ok"
    assert result["as_of"] == "2026-01-04T00:00:00+00:00"
    assert result["current_price"] == 100.0
    assert result["atr"] == 2.5
    assert result["candidates"] == [
        {
            "price": 99.0,
            "kind": "swing_low",
            "observed_at": "2026-01-02T00:00:00+00:00",
            "source_method": "method_b",
        },
        {
            "price": 101.0,
            "kind": "swing_high",
            "observed_at": "2026-01-03T00:00:00+00:00",
            "source_method": "method_a",
        },
    ]
    assert result["observed_zones"] == [
        {
            "zone": {
                "lower_bound": 99.0,
                "upper_bound": 101.0,
                "midpoint": 100.0,
                "candidates": result["candidates"],
                "source_methods": ["method_a", "method_b"],
            },
            "observation": {
                "touch_count": 2,
                "first_observed_at": "2026-01-02T00:00:00+00:00",
                "last_observed_at": "2026-01-03T00:00:00+00:00",
            },
        }
    ]
    json.dumps(result)


def test_snapshot_to_dict_serializes_empty_observed_zones() -> None:
    snapshot = PriceStructureSnapshot(
        status=PriceStructureStatus.NO_PIVOTS,
        as_of=datetime(2026, 1, 4, tzinfo=UTC),
        current_price=100.0,
    )

    result = snapshot_to_dict(snapshot)

    assert result["candidates"] == []
    assert result["observed_zones"] == []
    json.dumps(result)


def test_snapshot_to_dict_has_stable_ordering() -> None:
    assert snapshot_to_dict(_ok_snapshot()) == snapshot_to_dict(
        _ok_snapshot(reversed_order=True)
    )


def test_snapshot_to_dict_does_not_mutate_snapshot() -> None:
    snapshot = _ok_snapshot(reversed_order=True)
    original_candidates = snapshot.candidates
    original_zone_candidates = snapshot.observed_zones[0].zone.candidates
    original_source_methods = snapshot.observed_zones[0].zone.source_methods

    snapshot_to_dict(snapshot)

    assert snapshot.candidates is original_candidates
    assert snapshot.observed_zones[0].zone.candidates is original_zone_candidates
    assert snapshot.observed_zones[0].zone.source_methods is original_source_methods
