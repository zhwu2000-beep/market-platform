from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from market_platform.structure import (
    PriceLevelKind,
    PriceStructureConfig,
    PriceStructureService,
    PriceStructureStatus,
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