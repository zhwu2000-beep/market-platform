from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from market_platform.structure import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureConfig,
    PriceStructureService,
    PriceStructureSnapshot,
    PriceStructureStatus,
    PriceZone,
    PriceZoneObservation,
    detect_swing_highs,
    detect_swing_lows,
    filter_available_zones,
    filter_confirmed_pivots,
)


def _timestamps(count: int) -> list[datetime]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [start + timedelta(days=index) for index in range(count)]


def _price_frame(
    highs: list[float],
    lows: list[float],
    closes: list[float] | None = None,
) -> pd.DataFrame:
    resolved_closes = closes if closes is not None else [
        (high + low) / 2.0 for high, low in zip(highs, lows, strict=True)
    ]
    timestamps = _timestamps(len(highs))
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * len(highs),
            "timestamp": timestamps,
            "open": resolved_closes,
            "high": highs,
            "low": lows,
            "close": resolved_closes,
            "volume": [1_000] * len(highs),
        }
    )


def _all_pivots(
    prices: pd.DataFrame,
    *,
    window: int,
) -> tuple[PriceLevelCandidate, ...]:
    return (
        *detect_swing_highs(prices, window=window),
        *detect_swing_lows(prices, window=window),
    )


def test_pivot_records_occurrence_and_first_confirmation_time() -> None:
    prices = _price_frame(
        highs=[10.0, 11.0, 12.0, 13.0, 14.0, 20.0, 14.0, 13.0, 12.0, 11.0, 10.0],
        lows=[9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
    )

    pivot = detect_swing_highs(prices, window=5)[0]

    assert pivot.occurred_at == datetime(2026, 1, 6, tzinfo=UTC)
    assert pivot.confirmed_at == datetime(2026, 1, 11, tzinfo=UTC)
    assert pivot.observed_at == pivot.occurred_at


def test_legacy_observed_at_defaults_confirmation_to_occurrence() -> None:
    occurred_at = datetime(2026, 1, 10, tzinfo=UTC)

    pivot = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=occurred_at,
    )

    assert pivot.occurred_at == occurred_at
    assert pivot.confirmed_at == occurred_at
    with pytest.raises(FrozenInstanceError):
        pivot.confirmed_at = occurred_at + timedelta(days=1)  # type: ignore[misc]


def test_pivot_rejects_confirmation_before_occurrence() -> None:
    with pytest.raises(ValueError, match="confirmed_at must be later"):
        PriceLevelCandidate(
            price=100.0,
            kind=PriceLevelKind.SWING_HIGH,
            occurred_at=datetime(2026, 1, 10, tzinfo=UTC),
            confirmed_at=datetime(2026, 1, 9, tzinfo=UTC),
        )


def test_filter_confirmed_pivots_uses_inclusive_as_of() -> None:
    first = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        occurred_at=datetime(2026, 1, 5, tzinfo=UTC),
        confirmed_at=datetime(2026, 1, 7, tzinfo=UTC),
    )
    second = PriceLevelCandidate(
        price=90.0,
        kind=PriceLevelKind.SWING_LOW,
        occurred_at=datetime(2026, 1, 7, tzinfo=UTC),
        confirmed_at=datetime(2026, 1, 9, tzinfo=UTC),
    )

    assert filter_confirmed_pivots(
        (first, second),
        datetime(2026, 1, 7, tzinfo=UTC),
    ) == (first,)


def test_filtered_pivot_facts_are_invariant_to_future_input() -> None:
    historical = _price_frame(
        highs=[10.0, 13.0, 11.0, 15.0, 12.0, 14.0, 10.0],
        lows=[9.0, 8.0, 7.0, 9.0, 6.0, 8.0, 9.0],
    )
    with_future = _price_frame(
        highs=[10.0, 13.0, 11.0, 15.0, 12.0, 14.0, 10.0, 16.0, 11.0, 17.0],
        lows=[9.0, 8.0, 7.0, 9.0, 6.0, 8.0, 9.0, 7.0, 5.0, 8.0],
    )
    as_of = datetime(2026, 1, 7, tzinfo=UTC)

    historical_facts = filter_confirmed_pivots(
        _all_pivots(historical, window=1),
        as_of,
    )
    future_facts = filter_confirmed_pivots(
        _all_pivots(with_future, window=1),
        as_of,
    )

    assert future_facts == historical_facts


def test_structure_service_is_invariant_to_future_input_for_same_as_of() -> None:
    historical = _price_frame(
        highs=[10.0, 13.0, 11.0, 15.0, 12.0, 14.0, 10.0],
        lows=[9.0, 8.0, 7.0, 9.0, 6.0, 8.0, 9.0],
    )
    with_future = _price_frame(
        highs=[10.0, 13.0, 11.0, 15.0, 12.0, 14.0, 10.0, 16.0, 11.0, 17.0],
        lows=[9.0, 8.0, 7.0, 9.0, 6.0, 8.0, 9.0, 7.0, 5.0, 8.0],
    )
    as_of = datetime(2026, 1, 7, tzinfo=UTC)
    config = PriceStructureConfig(
        pivot_window=1,
        atr_period=1,
        zone_atr_multiplier=0.25,
    )
    service = PriceStructureService()

    historical_snapshot = service.analyze(historical, config=config)
    future_snapshot = service.analyze(with_future, config=config, as_of=as_of)

    assert future_snapshot == historical_snapshot


def test_zone_available_at_is_latest_candidate_confirmation() -> None:
    first = PriceLevelCandidate(
        price=99.0,
        kind=PriceLevelKind.SWING_LOW,
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        confirmed_at=datetime(2026, 1, 4, tzinfo=UTC),
    )
    second = PriceLevelCandidate(
        price=101.0,
        kind=PriceLevelKind.SWING_HIGH,
        occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        confirmed_at=datetime(2026, 1, 6, tzinfo=UTC),
    )

    zone = PriceZone(
        lower_bound=99.0,
        upper_bound=101.0,
        midpoint=100.0,
        candidates=(first, second),
        source_methods=("swing_pivot",),
    )

    assert zone.available_at == datetime(2026, 1, 6, tzinfo=UTC)


def test_filter_available_zones_excludes_future_zone() -> None:
    visible_pivot = PriceLevelCandidate(
        price=99.0,
        kind=PriceLevelKind.SWING_LOW,
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        confirmed_at=datetime(2026, 1, 4, tzinfo=UTC),
    )
    future_pivot = PriceLevelCandidate(
        price=101.0,
        kind=PriceLevelKind.SWING_HIGH,
        occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        confirmed_at=datetime(2026, 1, 8, tzinfo=UTC),
    )
    visible_zone = PriceZone(
        lower_bound=99.0,
        upper_bound=99.0,
        midpoint=99.0,
        candidates=(visible_pivot,),
        source_methods=("swing_pivot",),
    )
    future_zone = PriceZone(
        lower_bound=101.0,
        upper_bound=101.0,
        midpoint=101.0,
        candidates=(future_pivot,),
        source_methods=("swing_pivot",),
    )

    assert filter_available_zones(
        (visible_zone, future_zone),
        datetime(2026, 1, 6, tzinfo=UTC),
    ) == (visible_zone,)


def test_structure_snapshot_rejects_facts_not_visible_as_of() -> None:
    pivot = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        confirmed_at=datetime(2026, 1, 4, tzinfo=UTC),
    )
    zone = PriceZone(
        lower_bound=100.0,
        upper_bound=100.0,
        midpoint=100.0,
        candidates=(pivot,),
        source_methods=("swing_pivot",),
        available_at=datetime(2026, 1, 8, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="observed_zones must be available"):
        PriceStructureSnapshot(
            status=PriceStructureStatus.OK,
            as_of=datetime(2026, 1, 6, tzinfo=UTC),
            current_price=101.0,
            atr=1.0,
            candidates=(pivot,),
            observed_zones=(
                ObservedPriceZone(
                    zone=zone,
                    observation=PriceZoneObservation(0, None, None),
                ),
            ),
        )


@pytest.mark.parametrize(
    "filter_call",
    [
        lambda: filter_confirmed_pivots((), datetime(2026, 1, 1)),
        lambda: filter_available_zones((), datetime(2026, 1, 1)),
    ],
)
def test_point_in_time_filters_require_aware_as_of(filter_call: object) -> None:
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        filter_call()  # type: ignore[operator]
