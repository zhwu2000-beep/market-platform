from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

import market_platform.structure.touches as touches_module
from market_platform.structure import (
    PriceLevelCandidate,
    PriceLevelKind,
    PriceZone,
    observe_price_zone,
)


def _zone() -> PriceZone:
    candidate = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return PriceZone(
        lower_bound=99.0,
        upper_bound=101.0,
        midpoint=100.0,
        candidates=(candidate,),
        source_methods=("swing_pivot",),
    )


def _frame(*rows: tuple[datetime, float, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
        }
    )


def test_observe_price_zone_returns_zero_touches_for_empty_frame() -> None:
    observation = observe_price_zone(_frame(), _zone())

    assert observation.touch_count == 0
    assert observation.first_observed_at is None
    assert observation.last_observed_at is None


@pytest.mark.parametrize(
    ("high", "low"),
    [
        (100.0, 99.5),
        (99.0, 98.5),
        (101.5, 101.0),
    ],
)
def test_observe_price_zone_counts_single_intersection_as_one_touch(
    high: float,
    low: float,
) -> None:
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)
    observation = observe_price_zone(_frame((timestamp, high, low)), _zone())

    assert observation.touch_count == 1
    assert observation.first_observed_at == timestamp
    assert observation.last_observed_at == timestamp


@pytest.mark.parametrize(
    ("high", "low"),
    [
        (98.9, 98.0),
        (102.0, 101.1),
    ],
)
def test_observe_price_zone_ignores_candles_outside_zone(
    high: float,
    low: float,
) -> None:
    observation = observe_price_zone(
        _frame((datetime(2026, 1, 2, tzinfo=UTC), high, low)),
        _zone(),
    )

    assert observation.touch_count == 0
    assert observation.first_observed_at is None
    assert observation.last_observed_at is None



def test_observe_price_zone_counts_high_equals_low_inside_zone() -> None:
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)
    observation = observe_price_zone(
        _frame((timestamp, 100.0, 100.0)),
        _zone(),
    )

    assert observation.touch_count == 1
    assert observation.first_observed_at == timestamp
    assert observation.last_observed_at == timestamp


def test_observe_price_zone_ignores_high_equals_low_outside_zone() -> None:
    observation = observe_price_zone(
        _frame((datetime(2026, 1, 2, tzinfo=UTC), 98.0, 98.0)),
        _zone(),
    )

    assert observation.touch_count == 0
    assert observation.first_observed_at is None
    assert observation.last_observed_at is None


def test_observe_price_zone_counts_consecutive_inside_candles_once() -> None:
    start = datetime(2026, 1, 2, tzinfo=UTC)
    observation = observe_price_zone(
        _frame(
            (start, 100.0, 99.5),
            (start + timedelta(days=1), 100.5, 99.8),
            (start + timedelta(days=2), 100.2, 99.9),
        ),
        _zone(),
    )

    assert observation.touch_count == 1
    assert observation.first_observed_at == start
    assert observation.last_observed_at == start


def test_observe_price_zone_counts_reentries_as_new_touches() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    observation = observe_price_zone(
        _frame(
            (start, 98.5, 97.5),
            (start + timedelta(days=1), 100.0, 99.0),
            (start + timedelta(days=2), 98.0, 97.0),
            (start + timedelta(days=3), 100.2, 99.2),
            (start + timedelta(days=4), 100.8, 99.6),
        ),
        _zone(),
    )

    assert observation.touch_count == 2
    assert observation.first_observed_at == start + timedelta(days=1)
    assert observation.last_observed_at == start + timedelta(days=3)


def test_observe_price_zone_uses_first_candle_of_touch_for_last_time() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    observation = observe_price_zone(
        _frame(
            (start, 100.0, 99.5),
            (start + timedelta(days=1), 100.2, 99.7),
            (start + timedelta(days=2), 98.5, 97.5),
            (start + timedelta(days=3), 100.1, 99.1),
            (start + timedelta(days=4), 100.4, 99.4),
        ),
        _zone(),
    )

    assert observation.touch_count == 2
    assert observation.first_observed_at == start
    assert observation.last_observed_at == start + timedelta(days=3)


def test_observe_price_zone_handles_unsorted_input_deterministically() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    sorted_frame = _frame(
        (start, 98.5, 97.5),
        (start + timedelta(days=1), 100.0, 99.0),
        (start + timedelta(days=2), 98.0, 97.0),
        (start + timedelta(days=3), 100.2, 99.2),
    )
    unsorted_frame = sorted_frame.iloc[[2, 0, 3, 1]].reset_index(drop=True)

    sorted_observation = observe_price_zone(sorted_frame, _zone())
    unsorted_observation = observe_price_zone(unsorted_frame, _zone())

    assert unsorted_observation == sorted_observation


def test_observe_price_zone_does_not_mutate_input_frame_or_zone() -> None:
    prices = _frame(
        (datetime(2026, 1, 2, tzinfo=UTC), 100.0, 99.0),
        (datetime(2026, 1, 1, tzinfo=UTC), 98.5, 97.5),
    )
    original_prices = prices.copy(deep=True)
    zone = _zone()
    original_zone = zone

    observe_price_zone(prices, zone)

    pd.testing.assert_frame_equal(prices, original_prices)
    assert zone == original_zone


def test_observe_price_zone_is_deterministic_for_same_input() -> None:
    prices = _frame(
        (datetime(2026, 1, 1, tzinfo=UTC), 98.5, 97.5),
        (datetime(2026, 1, 2, tzinfo=UTC), 100.0, 99.0),
        (datetime(2026, 1, 3, tzinfo=UTC), 98.0, 97.0),
        (datetime(2026, 1, 4, tzinfo=UTC), 100.5, 99.5),
    )

    first = observe_price_zone(prices, _zone())
    second = observe_price_zone(prices, _zone())

    assert first == second


@pytest.mark.parametrize(
    ("columns", "message"),
    [
        (("high", "low"), "missing required columns: timestamp"),
        (("timestamp", "low"), "missing required columns: high"),
        (("timestamp", "high"), "missing required columns: low"),
    ],
)
def test_observe_price_zone_rejects_missing_columns(
    columns: tuple[str, ...],
    message: str,
) -> None:
    prices = _frame((datetime(2026, 1, 1, tzinfo=UTC), 100.0, 99.0)).loc[
        :, list(columns)
    ]

    with pytest.raises(ValueError, match=message):
        observe_price_zone(prices, _zone())


@pytest.mark.parametrize(
    ("prices", "message"),
    [
        (
            _frame(
                (datetime(2026, 1, 1, tzinfo=UTC), float("nan"), 99.0),
            ),
            "invalid high values",
        ),
        (
            _frame(
                (datetime(2026, 1, 1, tzinfo=UTC), 100.0, float("nan")),
            ),
            "invalid low values",
        ),
        (
            pd.DataFrame(
                {
                    "timestamp": [pd.NaT],
                    "high": [100.0],
                    "low": [99.0],
                }
            ),
            "invalid timestamp values",
        ),
    ],
)
def test_observe_price_zone_rejects_invalid_values(
    prices: pd.DataFrame,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        observe_price_zone(prices, _zone())


def test_observe_price_zone_rejects_duplicate_timestamps() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    prices = _frame(
        (timestamp, 100.0, 99.0),
        (timestamp, 98.0, 97.0),
    )

    with pytest.raises(ValueError, match="must not contain duplicate timestamps"):
        observe_price_zone(prices, _zone())




def test_observe_price_zone_rejects_high_below_low() -> None:
    prices = _frame((datetime(2026, 1, 1, tzinfo=UTC), 98.0, 99.0))

    with pytest.raises(ValueError, match="high must be greater than or equal to low"):
        observe_price_zone(prices, _zone())

def test_private_normalized_touch_path_matches_public_path() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    prices = _frame(
        (start, 98.5, 97.5),
        (start + timedelta(days=1), 99.0, 98.5),
        (start + timedelta(days=2), 101.0, 100.5),
        (start + timedelta(days=3), 102.0, 101.5),
        (start + timedelta(days=4), 100.5, 99.5),
    )
    zone = _zone()
    normalized = touches_module._normalize_price_frame(prices)

    assert touches_module._observe_price_zone_normalized(
        normalized,
        zone,
    ) == observe_price_zone(prices, zone)


@pytest.mark.parametrize(
    "zone",
    [
        _zone(),
        PriceZone(
            lower_bound=97.0,
            upper_bound=98.0,
            midpoint=97.5,
            candidates=(
                PriceLevelCandidate(
                    price=97.5,
                    kind=PriceLevelKind.SWING_LOW,
                    observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ),
            source_methods=("swing_pivot",),
        ),
        PriceZone(
            lower_bound=110.0,
            upper_bound=111.0,
            midpoint=110.5,
            candidates=(
                PriceLevelCandidate(
                    price=110.5,
                    kind=PriceLevelKind.SWING_HIGH,
                    observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ),
            source_methods=("swing_pivot",),
        ),
    ],
)
def test_private_normalized_touch_path_handles_multiple_touch_shapes(
    zone: PriceZone,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    prices = _frame(
        (start, 97.5, 96.5),
        (start + timedelta(days=1), 100.0, 99.0),
        (start + timedelta(days=2), 100.5, 99.5),
        (start + timedelta(days=3), 102.5, 101.5),
        (start + timedelta(days=4), 99.0, 98.0),
    )
    normalized = touches_module._normalize_price_frame(prices)

    assert touches_module._observe_price_zone_normalized(
        normalized,
        zone,
    ) == observe_price_zone(prices, zone)
