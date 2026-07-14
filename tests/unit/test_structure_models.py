from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from market_platform.structure import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureConfig,
    PriceStructureSnapshot,
    PriceStructureStatus,
    PriceZone,
    PriceZoneObservation,
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


def test_price_zone_observation_defaults_to_zero_touches_and_is_frozen() -> None:
    observation = PriceZoneObservation(0, None, None)

    assert observation.touch_count == 0
    assert observation.first_observed_at is None
    assert observation.last_observed_at is None

    with pytest.raises(FrozenInstanceError):
        observation.touch_count = 1  # type: ignore[misc]


def test_price_zone_observation_normalizes_aware_datetimes_to_utc() -> None:
    observation = PriceZoneObservation(
        2,
        datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=8))),
        datetime(2026, 1, 2, 9, tzinfo=timezone(timedelta(hours=8))),
    )

    assert observation.touch_count == 2
    assert observation.first_observed_at == datetime(2026, 1, 1, 1, tzinfo=UTC)
    assert observation.last_observed_at == datetime(2026, 1, 2, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"touch_count": -1, "first_observed_at": None, "last_observed_at": None},
            "touch_count must not be negative",
        ),
        (
            {"touch_count": True, "first_observed_at": None, "last_observed_at": None},
            "touch_count must be an integer",
        ),
        (
            {
                "touch_count": 0,
                "first_observed_at": datetime(2026, 1, 1, tzinfo=UTC),
                "last_observed_at": None,
            },
            "must be None when touch_count is 0",
        ),
        (
            {
                "touch_count": 1,
                "first_observed_at": None,
                "last_observed_at": datetime(2026, 1, 1, tzinfo=UTC),
            },
            "must be provided when touch_count is greater than 0",
        ),
        (
            {
                "touch_count": 1,
                "first_observed_at": datetime(2026, 1, 2, tzinfo=UTC),
                "last_observed_at": datetime(2026, 1, 1, tzinfo=UTC),
            },
            "first_observed_at must be earlier than or equal to last_observed_at",
        ),
        (
            {
                "touch_count": 1,
                "first_observed_at": datetime(2026, 1, 1),
                "last_observed_at": datetime(2026, 1, 1, tzinfo=UTC),
            },
            "first_observed_at must be timezone-aware",
        ),
    ],
)
def test_price_zone_observation_rejects_invalid_combinations(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        PriceZoneObservation(**kwargs)


def _observed_zone(
    lower_bound: float,
    upper_bound: float,
    *,
    observed_at: datetime,
) -> ObservedPriceZone:
    midpoint = (lower_bound + upper_bound) / 2.0
    candidate = PriceLevelCandidate(
        price=midpoint,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=observed_at,
    )
    zone = PriceZone(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        midpoint=midpoint,
        candidates=(candidate,),
        source_methods=("swing_pivot",),
    )
    return ObservedPriceZone(
        zone=zone,
        observation=PriceZoneObservation(0, None, None),
    )


def _ok_snapshot(
    *,
    current_price: float,
    observed_zones: tuple[ObservedPriceZone, ...],
) -> PriceStructureSnapshot:
    return PriceStructureSnapshot(
        status=PriceStructureStatus.OK,
        as_of=datetime(2026, 1, 10, tzinfo=UTC),
        current_price=current_price,
        atr=2.0,
        candidates=tuple(
            candidate
            for observed in observed_zones
            for candidate in observed.zone.candidates
        ),
        observed_zones=observed_zones,
    )


def test_price_structure_status_values_are_stable() -> None:
    assert [status.value for status in PriceStructureStatus] == [
        "ok",
        "insufficient_data",
        "no_pivots",
        "volatility_unavailable",
    ]


def test_observed_price_zone_is_frozen() -> None:
    observed = _observed_zone(
        99.0,
        101.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(FrozenInstanceError):
        observed.zone = observed.zone  # type: ignore[misc]


def test_snapshot_normalizes_as_of_to_utc() -> None:
    snapshot = PriceStructureSnapshot(
        status=PriceStructureStatus.INSUFFICIENT_DATA,
        as_of=datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=8))),
    )

    assert snapshot.as_of == datetime(2026, 1, 1, 1, tzinfo=UTC)


def test_snapshot_sorts_candidates_and_observed_zones_deterministically() -> None:
    earlier = _observed_zone(
        90.0,
        92.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    later = _observed_zone(
        110.0,
        112.0,
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    snapshot = _ok_snapshot(
        current_price=100.0,
        observed_zones=(later, earlier),
    )

    assert [candidate.observed_at for candidate in snapshot.candidates] == [
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
    ]
    assert [observed.zone.midpoint for observed in snapshot.observed_zones] == [
        91.0,
        111.0,
    ]


def test_snapshot_classifies_and_orders_zones_by_price_distance() -> None:
    observed_zones = (
        _observed_zone(
            115.0,
            120.0,
            observed_at=datetime(2026, 1, 5, tzinfo=UTC),
        ),
        _observed_zone(
            80.0,
            85.0,
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _observed_zone(
            99.0,
            101.0,
            observed_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        _observed_zone(
            90.0,
            95.0,
            observed_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        _observed_zone(
            105.0,
            110.0,
            observed_at=datetime(2026, 1, 4, tzinfo=UTC),
        ),
    )

    snapshot = _ok_snapshot(
        current_price=100.0,
        observed_zones=observed_zones,
    )

    assert [zone.zone.midpoint for zone in snapshot.lower_zones] == [92.5, 82.5]
    assert [zone.zone.midpoint for zone in snapshot.containing_zones] == [100.0]
    assert [zone.zone.midpoint for zone in snapshot.upper_zones] == [107.5, 117.5]
    assert snapshot.nearest_lower_zone is snapshot.lower_zones[0]
    assert snapshot.nearest_upper_zone is snapshot.upper_zones[0]


@pytest.mark.parametrize(
    ("current_price", "containing_index"),
    [
        (99.0, 0),
        (101.0, 0),
    ],
)
def test_snapshot_treats_zone_boundaries_as_containing(
    current_price: float,
    containing_index: int,
) -> None:
    observed = _observed_zone(
        99.0,
        101.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    snapshot = _ok_snapshot(
        current_price=current_price,
        observed_zones=(observed,),
    )

    assert snapshot.containing_zones[containing_index] is observed
    assert snapshot.lower_zones == ()
    assert snapshot.upper_zones == ()


def test_snapshot_returns_none_when_no_nearest_zone_exists() -> None:
    observed = _observed_zone(
        99.0,
        101.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    snapshot = _ok_snapshot(current_price=100.0, observed_zones=(observed,))

    assert snapshot.nearest_lower_zone is None
    assert snapshot.nearest_upper_zone is None


@pytest.mark.parametrize(
    "current_price",
    [True, 0.0, -1.0, float("nan"), float("inf"), "100"],
)
def test_snapshot_rejects_invalid_current_price(current_price: object) -> None:
    with pytest.raises((TypeError, ValueError), match="current_price"):
        PriceStructureSnapshot(
            status=PriceStructureStatus.INSUFFICIENT_DATA,
            current_price=current_price,  # type: ignore[arg-type]
        )


def test_insufficient_data_snapshot_requires_empty_results_and_no_atr() -> None:
    snapshot = PriceStructureSnapshot(
        status=PriceStructureStatus.INSUFFICIENT_DATA,
    )

    assert snapshot.as_of is None
    assert snapshot.current_price is None
    assert snapshot.atr is None
    assert snapshot.candidates == ()
    assert snapshot.observed_zones == ()


def test_no_pivots_snapshot_requires_diagnostics_and_empty_results() -> None:
    as_of = datetime(2026, 1, 10, tzinfo=UTC)
    snapshot = PriceStructureSnapshot(
        status=PriceStructureStatus.NO_PIVOTS,
        as_of=as_of,
        current_price=100.0,
    )

    assert snapshot.as_of == as_of
    assert snapshot.current_price == 100.0
    assert snapshot.atr is None
    assert snapshot.candidates == ()
    assert snapshot.observed_zones == ()


@pytest.mark.parametrize("atr", [None, 0.0])
def test_volatility_unavailable_snapshot_accepts_only_none_or_zero_atr(
    atr: float | None,
) -> None:
    observed = _observed_zone(
        99.0,
        101.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    snapshot = PriceStructureSnapshot(
        status=PriceStructureStatus.VOLATILITY_UNAVAILABLE,
        as_of=datetime(2026, 1, 10, tzinfo=UTC),
        current_price=100.0,
        atr=atr,
        candidates=observed.zone.candidates,
    )

    assert snapshot.atr == atr
    assert snapshot.candidates == observed.zone.candidates
    assert snapshot.observed_zones == ()


def test_status_specific_snapshot_invariants_reject_invalid_fields() -> None:
    observed = _observed_zone(
        99.0,
        101.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    candidate = observed.zone.candidates[0]
    as_of = datetime(2026, 1, 10, tzinfo=UTC)
    invalid_snapshots = [
        (
            {"status": PriceStructureStatus.INSUFFICIENT_DATA, "atr": 1.0},
            "atr must be None when status is INSUFFICIENT_DATA",
        ),
        (
            {
                "status": PriceStructureStatus.INSUFFICIENT_DATA,
                "candidates": (candidate,),
            },
            "candidates must be empty when status is INSUFFICIENT_DATA",
        ),
        (
            {
                "status": PriceStructureStatus.INSUFFICIENT_DATA,
                "observed_zones": (observed,),
            },
            "observed_zones must be empty when status is INSUFFICIENT_DATA",
        ),
        (
            {"status": PriceStructureStatus.NO_PIVOTS},
            "as_of must be provided when status is NO_PIVOTS",
        ),
        (
            {"status": PriceStructureStatus.NO_PIVOTS, "as_of": as_of},
            "current_price must be provided when status is NO_PIVOTS",
        ),
        (
            {
                "status": PriceStructureStatus.NO_PIVOTS,
                "as_of": as_of,
                "current_price": 100.0,
                "atr": 1.0,
            },
            "atr must be None when status is NO_PIVOTS",
        ),
        (
            {
                "status": PriceStructureStatus.NO_PIVOTS,
                "as_of": as_of,
                "current_price": 100.0,
                "candidates": (candidate,),
            },
            "candidates must be empty when status is NO_PIVOTS",
        ),
        (
            {
                "status": PriceStructureStatus.NO_PIVOTS,
                "as_of": as_of,
                "current_price": 100.0,
                "observed_zones": (observed,),
            },
            "observed_zones must be empty when status is NO_PIVOTS",
        ),
        (
            {
                "status": PriceStructureStatus.VOLATILITY_UNAVAILABLE,
                "candidates": (candidate,),
            },
            "as_of must be provided when status is VOLATILITY_UNAVAILABLE",
        ),
        (
            {
                "status": PriceStructureStatus.VOLATILITY_UNAVAILABLE,
                "as_of": as_of,
                "candidates": (candidate,),
            },
            "current_price must be provided when status is VOLATILITY_UNAVAILABLE",
        ),
        (
            {
                "status": PriceStructureStatus.VOLATILITY_UNAVAILABLE,
                "as_of": as_of,
                "current_price": 100.0,
            },
            "candidates must not be empty when volatility is unavailable",
        ),
        (
            {
                "status": PriceStructureStatus.VOLATILITY_UNAVAILABLE,
                "as_of": as_of,
                "current_price": 100.0,
                "candidates": (candidate,),
                "observed_zones": (observed,),
            },
            "observed_zones must be empty when status is VOLATILITY_UNAVAILABLE",
        ),
        (
            {
                "status": PriceStructureStatus.VOLATILITY_UNAVAILABLE,
                "as_of": as_of,
                "current_price": 100.0,
                "atr": 1.0,
                "candidates": (candidate,),
            },
            "atr must be None or 0 when status is VOLATILITY_UNAVAILABLE",
        ),
    ]

    for kwargs, message in invalid_snapshots:
        with pytest.raises(ValueError, match=message):
            PriceStructureSnapshot(**kwargs)


def test_ok_snapshot_rejects_missing_candidate() -> None:
    first = _observed_zone(
        90.0,
        92.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = _observed_zone(
        110.0,
        112.0,
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="must match snapshot candidates exactly"):
        PriceStructureSnapshot(
            status=PriceStructureStatus.OK,
            as_of=datetime(2026, 1, 10, tzinfo=UTC),
            current_price=100.0,
            atr=2.0,
            candidates=first.zone.candidates,
            observed_zones=(first, second),
        )


def test_ok_snapshot_rejects_duplicate_candidate() -> None:
    observed = _observed_zone(
        99.0,
        101.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    candidate = observed.zone.candidates[0]

    with pytest.raises(ValueError, match="each candidate must appear exactly once"):
        PriceStructureSnapshot(
            status=PriceStructureStatus.OK,
            as_of=datetime(2026, 1, 10, tzinfo=UTC),
            current_price=100.0,
            atr=2.0,
            candidates=(candidate, candidate),
            observed_zones=(observed,),
        )


def test_ok_snapshot_rejects_extra_candidate() -> None:
    first = _observed_zone(
        90.0,
        92.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = _observed_zone(
        110.0,
        112.0,
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="must match snapshot candidates exactly"):
        PriceStructureSnapshot(
            status=PriceStructureStatus.OK,
            as_of=datetime(2026, 1, 10, tzinfo=UTC),
            current_price=100.0,
            atr=2.0,
            candidates=(
                first.zone.candidates[0],
                second.zone.candidates[0],
            ),
            observed_zones=(first,),
        )


def test_price_structure_snapshot_is_frozen() -> None:
    observed = _observed_zone(
        99.0,
        101.0,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    snapshot = _ok_snapshot(current_price=100.0, observed_zones=(observed,))

    with pytest.raises(FrozenInstanceError):
        snapshot.current_price = 101.0  # type: ignore[misc]
