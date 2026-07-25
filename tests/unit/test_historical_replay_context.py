from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest

import market_platform.replay.service as replay_service
from market_platform.replay import (
    HistoricalReplayService,
    HistoricalReplaySpecification,
)
from market_platform.state import BaselineMarketStateModel, TrendRegime
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    create_strategy_collection,
)
from market_platform.structure import PriceStructureService

_START = datetime(2026, 1, 1, tzinfo=UTC)


def _prices(count: int = 80) -> pd.DataFrame:
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


def _specification(
    *,
    context_position: int,
    evaluation_start_position: int,
    evaluation_end_position: int,
) -> HistoricalReplaySpecification:
    return HistoricalReplaySpecification(
        symbol="MSFT",
        interval="1day",
        context_start=_START + timedelta(days=context_position),
        evaluation_start=_START + timedelta(days=evaluation_start_position),
        evaluation_end=_START + timedelta(days=evaluation_end_position),
    )


def _run_specification(
    prices: pd.DataFrame,
    specification: HistoricalReplaySpecification,
    *,
    service: HistoricalReplayService | None = None,
):
    replay = HistoricalReplayService() if service is None else service
    return replay.run_with_specification(
        prices,
        specification,
        strategies=create_strategy_collection([BaselineTrendRegimeStrategy()]),
        state_model=BaselineMarketStateModel(),
    )


def test_specification_retains_context_and_evaluates_only_inclusive_window() -> None:
    specification = _specification(
        context_position=0,
        evaluation_start_position=50,
        evaluation_end_position=52,
    )

    result = _run_specification(_prices(), specification)

    assert [step.as_of for step in result.steps] == [
        _START + timedelta(days=50),
        _START + timedelta(days=51),
        _START + timedelta(days=52),
    ]
    assert result.steps[0].state.trend_regime is not TrendRegime.UNAVAILABLE


def test_pre_evaluation_context_changes_first_step_analytical_facts() -> None:
    prices = _prices(53)
    with_context = _run_specification(
        prices,
        _specification(
            context_position=0,
            evaluation_start_position=50,
            evaluation_end_position=52,
        ),
    )
    without_context = _run_specification(
        prices,
        _specification(
            context_position=50,
            evaluation_start_position=50,
            evaluation_end_position=52,
        ),
    )

    assert with_context.steps[0].state.trend_regime is not TrendRegime.UNAVAILABLE
    assert without_context.steps[0].state.trend_regime is TrendRegime.UNAVAILABLE
    assert (
        with_context.steps[0].observation_fingerprint
        != without_context.steps[0].observation_fingerprint
    )


def test_context_bounds_are_applied_to_both_precomputations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal_inputs: list[pd.DataFrame] = []
    structure_inputs: list[pd.DataFrame] = []
    original_signal = replay_service.precompute_market_signal_snapshots
    original_structure = replay_service.precompute_price_structure_snapshots

    def record_signal(frame: pd.DataFrame):
        signal_inputs.append(frame.copy(deep=True))
        return original_signal(frame)

    def record_structure(frame: pd.DataFrame):
        structure_inputs.append(frame.copy(deep=True))
        return original_structure(frame)

    monkeypatch.setattr(
        replay_service,
        "precompute_market_signal_snapshots",
        record_signal,
    )
    monkeypatch.setattr(
        replay_service,
        "precompute_price_structure_snapshots",
        record_structure,
    )

    _run_specification(
        _prices(30),
        _specification(
            context_position=10,
            evaluation_start_position=20,
            evaluation_end_position=22,
        ),
    )

    for frame in (*signal_inputs, *structure_inputs):
        assert len(frame) == 13
        assert frame.iloc[0]["timestamp"] == pd.Timestamp(_START + timedelta(days=10))
        assert frame.iloc[-1]["timestamp"] == pd.Timestamp(_START + timedelta(days=22))


def test_requested_boundaries_need_not_have_exact_bars_or_pre_evaluation_rows() -> None:
    prices = _prices(5).iloc[[3, 4]].reset_index(drop=True)
    specification = HistoricalReplaySpecification(
        symbol="MSFT",
        interval="1day",
        context_start=_START + timedelta(hours=12),
        evaluation_start=_START + timedelta(days=2, hours=12),
        evaluation_end=_START + timedelta(days=4, hours=12),
    )

    result = _run_specification(prices, specification)

    assert [step.as_of for step in result.steps] == [
        _START + timedelta(days=3),
        _START + timedelta(days=4),
    ]


def test_specification_context_accepts_mixed_aware_offsets() -> None:
    prices = _prices(3)
    offset = timezone(timedelta(hours=5, minutes=30))
    prices["timestamp"] = prices["timestamp"].map(
        lambda value: value.to_pydatetime().astimezone(offset)
    )

    result = _run_specification(
        prices,
        _specification(
            context_position=0,
            evaluation_start_position=1,
            evaluation_end_position=2,
        ),
    )

    assert [step.as_of for step in result.steps] == [
        _START + timedelta(days=1),
        _START + timedelta(days=2),
    ]

def test_empty_raw_prices_preserve_canonical_input_error() -> None:
    with pytest.raises(ValueError, match="^prices must not be empty$"):
        _run_specification(
            _prices(0),
            _specification(
                context_position=0,
                evaluation_start_position=0,
                evaluation_end_position=1,
            ),
        )


def test_rows_before_context_use_established_range_error() -> None:
    with pytest.raises(
        ValueError,
        match="^no replay timestamps found in requested range$",
    ):
        _run_specification(
            _prices(5),
            _specification(
                context_position=10,
                evaluation_start_position=10,
                evaluation_end_position=11,
            ),
        )


def test_rows_after_evaluation_end_use_established_range_error() -> None:
    with pytest.raises(
        ValueError,
        match="^no replay timestamps found in requested range$",
    ):
        _run_specification(
            _prices(5),
            _specification(
                context_position=-5,
                evaluation_start_position=-2,
                evaluation_end_position=-1,
            ),
        )


def test_retained_context_without_evaluation_rows_uses_established_error() -> None:
    with pytest.raises(
        ValueError,
        match="^no replay timestamps found in requested range$",
    ):
        _run_specification(
            _prices(5),
            HistoricalReplaySpecification(
                symbol="MSFT",
                interval="1day",
                context_start=_START,
                evaluation_start=_START + timedelta(days=10),
                evaluation_end=_START + timedelta(days=11),
            ),
        )


def test_specification_rejects_symbol_mismatch() -> None:
    specification = HistoricalReplaySpecification(
        symbol="AAPL",
        interval="1day",
        context_start=_START,
        evaluation_start=_START,
        evaluation_end=_START + timedelta(days=2),
    )
    with pytest.raises(ValueError, match="matching symbol"):
        _run_specification(_prices(3), specification)


def test_future_rows_do_not_affect_specification_result() -> None:
    specification = _specification(
        context_position=0,
        evaluation_start_position=45,
        evaluation_end_position=49,
    )
    baseline = _run_specification(_prices(50), specification)
    future = _prices(70)
    future.loc[50:, "close"] = 10_000.0

    assert _run_specification(future, specification).to_dict() == baseline.to_dict()


def test_legacy_and_equivalent_specification_results_are_identical() -> None:
    prices = _prices(55)
    strategies = create_strategy_collection([BaselineTrendRegimeStrategy()])
    state_model = BaselineMarketStateModel()
    service = HistoricalReplayService()
    start = _START + timedelta(days=50)
    end = _START + timedelta(days=54)

    legacy = service.run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=state_model,
        start=start,
        end=end,
    )
    specified = service.run_with_specification(
        prices,
        HistoricalReplaySpecification(
            symbol="MSFT",
            interval="1day",
            context_start=_START,
            evaluation_start=start,
            evaluation_end=end,
        ),
        strategies=strategies,
        state_model=state_model,
    )

    assert specified.to_dict() == legacy.to_dict()
    assert _run_specification(prices, _specification(
        context_position=0,
        evaluation_start_position=50,
        evaluation_end_position=54,
    )).to_dict() == specified.to_dict()


class _RecordingCustomStructureService:
    def __init__(self) -> None:
        self.frames: list[pd.DataFrame] = []
        self._delegate = PriceStructureService()

    def _uses_default_components(self) -> bool:
        return False

    def analyze(self, prices: pd.DataFrame, *, as_of: datetime):
        isolated = prices.copy(deep=True)
        self.frames.append(isolated)
        prices.loc[prices.index[0], "close"] = 99_999.0
        return self._delegate.analyze(isolated, as_of=as_of)


def test_custom_structure_service_receives_isolated_context_prefixes() -> None:
    custom = _RecordingCustomStructureService()
    service = HistoricalReplayService(
        price_structure_service=custom,  # type: ignore[arg-type]
    )
    result = _run_specification(
        _prices(20),
        _specification(
            context_position=5,
            evaluation_start_position=10,
            evaluation_end_position=12,
        ),
        service=service,
    )

    assert result.step_count == 3
    assert [len(frame) for frame in custom.frames] == [6, 7, 8]
    assert all(
        frame.iloc[0]["timestamp"] == pd.Timestamp(_START + timedelta(days=5))
        for frame in custom.frames
    )
    assert [frame.iloc[-1]["timestamp"] for frame in custom.frames] == [
        pd.Timestamp(_START + timedelta(days=10)),
        pd.Timestamp(_START + timedelta(days=11)),
        pd.Timestamp(_START + timedelta(days=12)),
    ]
    assert all(frame.iloc[0]["close"] == 102.5 for frame in custom.frames)