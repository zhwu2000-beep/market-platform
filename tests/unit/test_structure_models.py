from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from market_platform.structure import (
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureConfig,
)


def test_price_structure_config_defaults_to_three() -> None:
    config = PriceStructureConfig()

    assert config.pivot_window == 3


def test_price_structure_config_accepts_custom_window() -> None:
    config = PriceStructureConfig(pivot_window=5)

    assert config.pivot_window == 5


@pytest.mark.parametrize("pivot_window", [0, -1])
def test_price_structure_config_rejects_non_positive_window(
    pivot_window: int,
) -> None:
    with pytest.raises(ValueError, match="pivot_window must be at least 1"):
        PriceStructureConfig(pivot_window=pivot_window)


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
