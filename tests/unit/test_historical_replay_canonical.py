from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from market_platform.data import HistoricalPricePrefix
from market_platform.replay import HistoricalReplayService
from market_platform.state import BaselineMarketStateModel
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    create_strategy_collection,
)
from market_platform.structure import (
    PriceStructureService,
    calculate_atr,
    detect_swing_highs,
    detect_swing_lows,
    observe_price_zone,
)

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _prices(count: int = 60) -> pd.DataFrame:
    closes = [100.0 + index * 0.5 for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * count,
            "timestamp": [_START + timedelta(days=index) for index in range(count)],
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": ["test-provider"] * count,
        }
    )


def _run(
    prices: pd.DataFrame,
    *,
    service: PriceStructureService | None = None,
):
    return HistoricalReplayService(price_structure_service=service).run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=create_strategy_collection([BaselineTrendRegimeStrategy()]),
        state_model=BaselineMarketStateModel(),
    )


def _custom_reference_service() -> PriceStructureService:
    return PriceStructureService(
        swing_high_detector=lambda prices, *, window: detect_swing_highs(
            prices,
            window=window,
        ),
        swing_low_detector=lambda prices, *, window: detect_swing_lows(
            prices,
            window=window,
        ),
        atr_calculator=lambda prices, *, period: calculate_atr(
            prices,
            period=period,
        ),
        zone_observer=lambda prices, zone: observe_price_zone(prices, zone),
    )


def test_implicit_explicit_and_reference_structure_services_are_equivalent() -> None:
    prices = _prices()

    implicit = _run(prices)
    explicit = _run(prices, service=PriceStructureService())
    reference = _run(prices, service=_custom_reference_service())

    assert explicit.to_dict() == implicit.to_dict()
    assert reference.to_dict() == implicit.to_dict()


def test_default_replay_does_not_materialize_per_step_prefix_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    original = HistoricalPricePrefix.to_dataframe

    def recording_materialization(prefix: HistoricalPricePrefix) -> pd.DataFrame:
        calls.append(len(prefix))
        return original(prefix)

    monkeypatch.setattr(
        HistoricalPricePrefix,
        "to_dataframe",
        recording_materialization,
    )

    implicit = _run(_prices(20))
    explicit = _run(_prices(20), service=PriceStructureService())

    assert implicit.step_count == explicit.step_count == 20
    assert calls == []


def test_custom_structure_materialization_is_isolated_and_counted_per_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lengths: list[int] = []
    original = HistoricalPricePrefix.to_dataframe

    def recording_materialization(prefix: HistoricalPricePrefix) -> pd.DataFrame:
        materialized = original(prefix)
        lengths.append(len(materialized))
        materialized.loc[0, "close"] = 50_000.0
        return materialized

    monkeypatch.setattr(
        HistoricalPricePrefix,
        "to_dataframe",
        recording_materialization,
    )

    result = _run(_prices(12), service=_custom_reference_service())

    assert result.step_count == 12
    assert lengths == list(range(1, 13))
