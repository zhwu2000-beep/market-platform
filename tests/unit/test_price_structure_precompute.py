from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import market_platform.structure.precompute as precompute_module
import market_platform.structure.service as service_module
from market_platform.structure import (
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureConfig,
    PriceStructureService,
    PriceStructureStatus,
    PriceZone,
    observe_price_zone,
)
from market_platform.structure.precompute import precompute_price_structure_snapshots
from market_platform.structure.reporting import snapshot_to_dict

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _timestamps(count: int) -> list[datetime]:
    return [_START + timedelta(days=index) for index in range(count)]


def _oscillating_frame(count: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, timestamp in enumerate(_timestamps(count)):
        close = 100.0 + index * 0.05 + 3.0 * ((index % 8) - 4) / 4.0
        if index % 2 == 0:
            close += 1.25
        high = close + 1.0 + (index % 5) * 0.05
        low = close - 1.0 - (index % 7) * 0.04
        rows.append(
            {
                "timestamp": timestamp,
                "high": high,
                "low": low,
                "close": close,
            }
        )
    return pd.DataFrame(rows)


def _monotonic_frame(count: int) -> pd.DataFrame:
    closes = [100.0 + index for index in range(count)]
    return pd.DataFrame(
        {
            "timestamp": _timestamps(count),
            "high": [close + 0.5 for close in closes],
            "low": [close - 0.5 for close in closes],
            "close": closes,
        }
    )


def _controlled_pivot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": _timestamps(7),
            "high": [10.0, 12.0, 20.0, 12.0, 10.0, 25.0, 10.0],
            "low": [9.0, 8.0, 7.0, 8.0, 9.0, 6.0, 9.0],
            "close": [9.5, 10.0, 12.0, 10.0, 9.5, 11.0, 9.5],
        }
    )


def _reference_snapshots(
    prices: pd.DataFrame,
    *,
    config: PriceStructureConfig | None = None,
) -> tuple:
    service = PriceStructureService()
    return tuple(
        service.analyze(
            prices.iloc[: position + 1].copy(deep=True),
            config=config,
            as_of=prices.iloc[position]["timestamp"],
        )
        for position in range(len(prices))
    )


@pytest.mark.parametrize("bar_count", [50, 100, 300, 500])
def test_precompute_matches_prefix_reference_for_every_position(
    bar_count: int,
) -> None:
    prices = _oscillating_frame(bar_count)

    precomputed = precompute_price_structure_snapshots(prices)
    reference = _reference_snapshots(prices)

    assert len(precomputed) == bar_count
    assert precomputed == reference
    for optimized, expected in zip(precomputed, reference, strict=True):
        assert snapshot_to_dict(optimized) == snapshot_to_dict(expected)
        assert json.dumps(snapshot_to_dict(optimized), sort_keys=True) == json.dumps(
            snapshot_to_dict(expected),
            sort_keys=True,
        )


def test_precompute_status_boundaries_match_reference() -> None:
    config = PriceStructureConfig()
    required_bars = max(2 * config.pivot_window + 1, config.atr_period)
    prices = _oscillating_frame(required_bars + 5)
    monotonic = _monotonic_frame(required_bars + 1)

    snapshots = precompute_price_structure_snapshots(prices, config=config)
    reference = _reference_snapshots(prices, config=config)

    assert snapshots == reference
    assert snapshots[0].status is PriceStructureStatus.INSUFFICIENT_DATA
    assert snapshots[required_bars - 2].status is PriceStructureStatus.INSUFFICIENT_DATA
    assert snapshots[required_bars - 1].status is reference[required_bars - 1].status
    assert any(snapshot.status is PriceStructureStatus.OK for snapshot in snapshots)
    assert all(
        snapshot.status is PriceStructureStatus.NO_PIVOTS
        for snapshot in precompute_price_structure_snapshots(monotonic)[
            required_bars - 1 :
        ]
    )


def test_precompute_pivot_confirmation_boundaries_are_point_in_time() -> None:
    config = PriceStructureConfig(
        pivot_window=2,
        atr_period=1,
        zone_atr_multiplier=0.25,
    )
    snapshots = precompute_price_structure_snapshots(
        _controlled_pivot_frame(),
        config=config,
    )

    assert snapshots[3].status is PriceStructureStatus.INSUFFICIENT_DATA
    assert snapshots[4].status is PriceStructureStatus.OK
    high_candidates = [
        candidate
        for candidate in snapshots[4].candidates
        if candidate.kind is PriceLevelKind.SWING_HIGH
    ]
    assert len(high_candidates) == 1
    candidate = high_candidates[0]
    assert candidate.occurred_at == _START + timedelta(days=2)
    assert candidate.confirmed_at == _START + timedelta(days=4)
    assert all(
        all(
            item.occurred_at != _START + timedelta(days=5)
            for item in snapshot.candidates
        )
        for snapshot in snapshots
    )

def test_precompute_rejects_strict_plateau_as_pivot() -> None:
    config = PriceStructureConfig(
        pivot_window=1,
        atr_period=1,
        zone_atr_multiplier=0.25,
    )
    prices = pd.DataFrame(
        {
            "timestamp": _timestamps(5),
            "high": [10.0, 12.0, 12.0, 11.0, 10.0],
            "low": [9.0, 8.0, 7.0, 8.0, 9.0],
            "close": [9.5, 10.0, 10.0, 9.5, 9.0],
        }
    )

    assert all(
        all(
            candidate.kind is not PriceLevelKind.SWING_HIGH
            for candidate in snapshot.candidates
        )
        for snapshot in precompute_price_structure_snapshots(prices, config=config)
    )

def test_precompute_future_data_does_not_change_prior_snapshots() -> None:
    base = _oscillating_frame(80)
    future = pd.concat(
        [
            base,
            pd.DataFrame(
                {
                    "timestamp": [
                        _START + timedelta(days=80 + index)
                        for index in range(10)
                    ],
                    "high": [500.0 + index for index in range(10)],
                    "low": [490.0 - index for index in range(10)],
                    "close": [495.0 for _ in range(10)],
                }
            ),
        ],
        ignore_index=True,
    )

    historical = precompute_price_structure_snapshots(base)
    with_future = precompute_price_structure_snapshots(future)

    assert with_future[: len(base)] == historical
    for optimized, expected in zip(with_future[: len(base)], historical, strict=True):
        assert snapshot_to_dict(optimized) == snapshot_to_dict(expected)


def test_precompute_sorts_stably_and_does_not_mutate_input() -> None:
    sorted_prices = _oscillating_frame(40)
    unsorted = sorted_prices.iloc[[5, 0, 2, 1, 4, 3, *range(6, 40)]].reset_index(
        drop=True
    )
    before = unsorted.copy(deep=True)

    sorted_snapshots = precompute_price_structure_snapshots(sorted_prices)
    unsorted_snapshots = precompute_price_structure_snapshots(unsorted)

    assert unsorted_snapshots == sorted_snapshots
    assert_frame_equal(unsorted, before)


def test_precompute_rejects_duplicate_timestamps() -> None:
    prices = _oscillating_frame(20)
    prices.loc[1, "timestamp"] = prices.loc[0, "timestamp"]

    with pytest.raises(ValueError, match="must not contain duplicate timestamps"):
        precompute_price_structure_snapshots(prices)


def test_precompute_empty_frame_returns_empty_tuple() -> None:
    prices = pd.DataFrame(columns=["timestamp", "high", "low", "close"])

    assert precompute_price_structure_snapshots(prices) == ()


def test_structure_precompute_is_not_package_level_export() -> None:
    import market_platform.structure as structure_package

    assert "precompute_price_structure_snapshots" not in structure_package.__all__
    assert not hasattr(structure_package, "precompute_price_structure_snapshots")


def test_structure_precompute_module_does_not_import_replay() -> None:
    imported: set[str] = set()
    for path in sorted(Path("src/market_platform/structure").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

    assert "market_platform.replay" not in imported
    assert not any(module.startswith("market_platform.replay.") for module in imported)

def _single_candidate_zone(
    *,
    lower_bound: float = 99.0,
    upper_bound: float = 101.0,
    occurred_at: datetime = _START,
    confirmed_at: datetime | None = None,
    source_method: str = "swing_pivot",
) -> PriceZone:
    midpoint = (lower_bound + upper_bound) / 2.0
    candidate = PriceLevelCandidate(
        price=midpoint,
        kind=PriceLevelKind.SWING_HIGH,
        occurred_at=occurred_at,
        confirmed_at=confirmed_at,
        source_method=source_method,
    )
    return PriceZone(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        midpoint=midpoint,
        candidates=(candidate,),
        source_methods=(source_method,),
    )


def test_touch_observation_series_matches_public_prefix_observer() -> None:
    prices = pd.DataFrame(
        {
            "timestamp": _timestamps(8),
            "high": [98.0, 99.0, 100.5, 100.8, 98.5, 101.0, 101.2, 100.2],
            "low": [97.0, 98.0, 99.5, 99.8, 97.5, 100.0, 100.5, 99.7],
            "close": [97.5, 98.5, 100.0, 100.1, 98.0, 100.5, 100.7, 100.0],
        }
    )
    normalized = service_module._normalize_price_frame(prices)
    timestamps = tuple(
        service_module._to_datetime(value) for value in normalized["timestamp"]
    )
    zone = _single_candidate_zone()
    series = precompute_module._build_touch_observation_series(
        normalized,
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
    )

    for position in range(len(normalized)):
        optimized = precompute_module._touch_observation_at_position(
            series,
            timestamps,
            position,
        )
        expected = observe_price_zone(normalized.iloc[: position + 1], zone)
        assert optimized == expected
        assert optimized.touch_count == expected.touch_count
        assert optimized.first_observed_at == expected.first_observed_at
        assert optimized.last_observed_at == expected.last_observed_at


def test_touch_series_covers_boundary_and_consecutive_cases() -> None:
    prices = pd.DataFrame(
        {
            "timestamp": _timestamps(7),
            "high": [98.0, 99.0, 100.0, 102.0, 102.5, 101.0, 100.5],
            "low": [97.0, 98.0, 99.5, 98.0, 101.2, 100.0, 99.5],
            "close": [97.5, 98.5, 99.8, 100.0, 101.8, 100.5, 100.0],
        }
    )
    normalized = service_module._normalize_price_frame(prices)
    timestamps = tuple(
        service_module._to_datetime(value) for value in normalized["timestamp"]
    )
    zone = _single_candidate_zone()
    series = precompute_module._build_touch_observation_series(
        normalized,
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
    )

    observations = tuple(
        precompute_module._touch_observation_at_position(series, timestamps, position)
        for position in range(len(normalized))
    )

    assert [item.touch_count for item in observations] == [0, 1, 1, 1, 1, 2, 2]
    assert observations[0].first_observed_at is None
    assert observations[1].first_observed_at == _START + timedelta(days=1)
    assert observations[4].last_observed_at == _START + timedelta(days=1)
    assert observations[5].last_observed_at == _START + timedelta(days=5)


def test_precompute_late_zone_includes_historical_touches_before_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = pd.DataFrame(
        {
            "timestamp": _timestamps(6),
            "high": [100.5, 98.0, 100.2, 98.0, 98.0, 99.5],
            "low": [99.5, 97.0, 99.2, 97.0, 97.0, 98.5],
            "close": [100.0, 97.5, 99.8, 97.5, 97.5, 99.0],
        }
    )
    late_candidate = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        occurred_at=_START + timedelta(days=5),
        confirmed_at=_START + timedelta(days=5),
    )

    monkeypatch.setattr(
        precompute_module,
        "_detect_swing_highs_normalized",
        lambda prices, *, window: (late_candidate,),
    )
    monkeypatch.setattr(
        precompute_module,
        "_detect_swing_lows_normalized",
        lambda prices, *, window: (),
    )

    snapshots = precompute_price_structure_snapshots(
        prices,
        config=PriceStructureConfig(pivot_window=1, atr_period=1),
    )
    snapshot = snapshots[5]
    observed = snapshot.observed_zones[0]
    public = observe_price_zone(prices.iloc[:6], observed.zone)

    assert observed.zone.available_at == _START + timedelta(days=5)
    assert observed.observation == public
    assert observed.observation.touch_count == 2
    assert observed.observation.first_observed_at == _START
    assert observed.observation.last_observed_at == _START + timedelta(days=2)


def test_precompute_reuses_exact_touch_geometry_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = _oscillating_frame(100)
    builds: list[tuple[float, float]] = []
    lookups = 0
    real_build = precompute_module._build_touch_observation_series
    real_lookup = precompute_module._touch_observation_at_position

    def counting_build(frame: pd.DataFrame, *, lower_bound: float, upper_bound: float):
        builds.append((lower_bound, upper_bound))
        return real_build(
            frame,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

    def counting_lookup(series, timestamps, position):
        nonlocal lookups
        lookups += 1
        return real_lookup(series, timestamps, position)

    monkeypatch.setattr(
        precompute_module,
        "_build_touch_observation_series",
        counting_build,
    )
    monkeypatch.setattr(
        precompute_module,
        "_touch_observation_at_position",
        counting_lookup,
    )
    monkeypatch.setattr(
        service_module,
        "_observe_zone",
        lambda *args, **kwargs: pytest.fail("precompute should not scan prefixes"),
    )

    snapshots = precompute_price_structure_snapshots(prices)
    logical_observations = sum(len(snapshot.observed_zones) for snapshot in snapshots)
    exact_keys = {
        (observed.zone.lower_bound, observed.zone.upper_bound)
        for snapshot in snapshots
        for observed in snapshot.observed_zones
    }

    assert builds == list(dict.fromkeys(builds))
    assert set(builds) == exact_keys
    assert len(builds) == len(exact_keys)
    assert lookups == logical_observations
    assert len(builds) <= lookups


def test_touch_state_key_reuses_same_bounds_and_separates_near_bounds() -> None:
    prices = service_module._normalize_price_frame(_oscillating_frame(12))
    timestamps = tuple(
        service_module._to_datetime(value) for value in prices["timestamp"]
    )
    touch_states: dict[
        tuple[float, float], precompute_module._TouchObservationSeries
    ] = {}
    same_bounds = _single_candidate_zone(source_method="manual")
    same_bounds_later = PriceZone(
        lower_bound=99.0,
        upper_bound=101.0,
        midpoint=100.0,
        candidates=(
            PriceLevelCandidate(
                price=100.0,
                kind=PriceLevelKind.SWING_LOW,
                observed_at=_START + timedelta(days=1),
                source_method="other",
            ),
        ),
        source_methods=("other",),
    )
    near_lower = _single_candidate_zone(lower_bound=99.0 + 1e-12, upper_bound=101.0)
    near_upper = _single_candidate_zone(lower_bound=99.0, upper_bound=101.0 + 1e-12)

    first = precompute_module._observe_zone_with_touch_state(
        prices,
        timestamps=timestamps,
        position=5,
        touch_states=touch_states,
        zone=same_bounds,
    )
    second = precompute_module._observe_zone_with_touch_state(
        prices,
        timestamps=timestamps,
        position=7,
        touch_states=touch_states,
        zone=same_bounds_later,
    )
    precompute_module._observe_zone_with_touch_state(
        prices,
        timestamps=timestamps,
        position=7,
        touch_states=touch_states,
        zone=near_lower,
    )
    precompute_module._observe_zone_with_touch_state(
        prices,
        timestamps=timestamps,
        position=7,
        touch_states=touch_states,
        zone=near_upper,
    )

    assert len(touch_states) == 3
    assert first == observe_price_zone(prices.iloc[:6], same_bounds)
    assert second == observe_price_zone(prices.iloc[:8], same_bounds_later)

def test_touch_series_does_not_expose_future_first_touch() -> None:
    prices = pd.DataFrame(
        {
            "timestamp": _timestamps(6),
            "high": [100.0, 100.5, 101.0, 101.5, 110.0, 110.5],
            "low": [99.0, 99.5, 100.0, 100.5, 109.5, 109.8],
            "close": [99.5, 100.0, 100.5, 101.0, 109.8, 110.1],
        }
    )
    normalized = service_module._normalize_price_frame(prices)
    timestamps = tuple(
        service_module._to_datetime(value) for value in normalized["timestamp"]
    )
    zone = _single_candidate_zone(lower_bound=109.0, upper_bound=111.0)
    series = precompute_module._build_touch_observation_series(
        normalized,
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
    )

    for position in range(4):
        observation = precompute_module._touch_observation_at_position(
            series,
            timestamps,
            position,
        )
        assert observation.touch_count == 0
        assert observation.first_observed_at is None
        assert observation.last_observed_at is None

    first_touch = precompute_module._touch_observation_at_position(
        series,
        timestamps,
        4,
    )
    assert first_touch.touch_count == 1
    assert first_touch.first_observed_at == _START + timedelta(days=4)
    assert first_touch.last_observed_at == _START + timedelta(days=4)


def test_touch_series_rejects_invalid_lookup_position_and_keeps_arrays_read_only(
) -> None:
    prices = service_module._normalize_price_frame(_oscillating_frame(12))
    timestamps = tuple(
        service_module._to_datetime(value) for value in prices["timestamp"]
    )
    zone = _single_candidate_zone()
    series = precompute_module._build_touch_observation_series(
        prices,
        lower_bound=zone.lower_bound,
        upper_bound=zone.upper_bound,
    )

    assert series.counts.flags.writeable is False
    assert series.last_entry_indices.flags.writeable is False
    with pytest.raises(IndexError, match="position out of range"):
        precompute_module._touch_observation_at_position(series, timestamps, -1)
    with pytest.raises(IndexError, match="position out of range"):
        precompute_module._touch_observation_at_position(
            series,
            timestamps,
            len(prices),
        )


def test_precompute_touch_state_is_local_to_each_precompute_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = _oscillating_frame(60)
    builds: list[tuple[float, float]] = []
    real_build = precompute_module._build_touch_observation_series

    def counting_build(frame: pd.DataFrame, *, lower_bound: float, upper_bound: float):
        builds.append((lower_bound, upper_bound))
        return real_build(
            frame,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

    monkeypatch.setattr(
        precompute_module,
        "_build_touch_observation_series",
        counting_build,
    )

    first = precompute_price_structure_snapshots(prices)
    first_build_count = len(builds)
    second = precompute_price_structure_snapshots(prices)
    second_build_count = len(builds) - first_build_count

    assert first == second
    assert first_build_count > 0
    assert second_build_count == first_build_count
