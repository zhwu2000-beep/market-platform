from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import market_platform.replay.service as replay_service
import market_platform.signals.service as signal_service
from market_platform.replay import HistoricalReplayResult, HistoricalReplayService
from market_platform.state import (
    BaselineMarketStateModel,
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StateModelProvenance,
    StateQuality,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    BaselineVolatilityRegimeStrategy,
    StrategyEvaluationStatus,
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
    timestamps = [_START + timedelta(days=index) for index in range(count)]
    closes = [100.0 + index * 0.5 for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": ["MSFT"] * count,
            "timestamp": timestamps,
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": ["test-provider"] * count,
        }
    )


def _service_result(
    prices: pd.DataFrame | None = None,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    strategies=None,
) -> HistoricalReplayResult:
    return HistoricalReplayService().run(
        _prices() if prices is None else prices,
        symbol="MSFT",
        interval="1day",
        strategies=(
            create_strategy_collection([BaselineTrendRegimeStrategy()])
            if strategies is None
            else strategies
        ),
        state_model=BaselineMarketStateModel(),
        start=start,
        end=end,
    )


class BadStateModel:
    @property
    def model_id(self) -> str:
        return "expected-model"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def evaluate(self, observation) -> MarketState:
        return MarketState(
            symbol=observation.identity.symbol,
            interval=observation.identity.interval,
            as_of=observation.identity.as_of,
            provenance=StateModelProvenance(
                model_id="other-model",
                model_version="1.0.0",
                parameters={},
                observation_fingerprint=observation.provenance.input_fingerprint,
            ),
            directional_regime=DirectionalRegime.UP,
            trend_regime=TrendRegime.UP,
            momentum_regime=MomentumRegime.POSITIVE,
            volatility_regime=VolatilityRegime.NORMAL,
            structure_state=StructureState.AVAILABLE,
            quality=StateQuality.COMPLETE,
        )


def test_replay_runs_every_bar_in_inclusive_range() -> None:
    start = _START + timedelta(days=2)
    end = _START + timedelta(days=4)

    result = _service_result(start=start, end=end)

    assert result.step_count == 3
    assert [step.as_of for step in result.steps] == [
        _START + timedelta(days=2),
        _START + timedelta(days=3),
        _START + timedelta(days=4),
    ]
    assert result.start_as_of == start
    assert result.end_as_of == end


def test_replay_result_stores_strategy_identities_not_collection() -> None:
    result = _service_result(start=_START, end=_START)

    assert result.strategies[0].strategy_id == "baseline_trend_regime"
    assert result.strategies[0].configuration_fingerprint is not None
    assert not hasattr(result, "strategy_collection")
    assert not hasattr(result, "strategy_instances")


def test_warmup_is_preserved_as_insufficient_data_step() -> None:
    result = _service_result(start=_START, end=_START)

    evaluation = result.steps[0].strategy_result.evaluations[0]
    assert evaluation.status is StrategyEvaluationStatus.INSUFFICIENT_DATA
    assert evaluation.missing_inputs == ("trend_regime", "momentum_regime")


def test_empty_strategy_collection_produces_empty_strategy_results() -> None:
    result = _service_result(
        start=_START,
        end=_START,
        strategies=create_strategy_collection([]),
    )

    assert result.strategies == ()
    assert result.steps[0].strategy_result.evaluations == ()


def test_prefix_invariance_and_future_data_injection() -> None:
    prices = _prices(56)
    as_of = prices.iloc[-1]["timestamp"].to_pydatetime()
    prefix_result = _service_result(prices).steps[-1]
    future = pd.concat(
        [
            prices,
            pd.DataFrame(
                {
                    "symbol": ["MSFT"],
                    "timestamp": [as_of + timedelta(days=1)],
                    "open": [9999.0],
                    "high": [10000.0],
                    "low": [9998.0],
                    "close": [9999.0],
                    "volume": [1_000_000.0],
                    "provider": ["test-provider"],
                }
            ),
        ],
        ignore_index=True,
    )
    replayed = _service_result(future, start=as_of, end=as_of).steps[0]

    assert replayed.to_dict() == prefix_result.to_dict()


def test_unsorted_input_is_copied_and_sorted() -> None:
    prices = _prices(5).iloc[[4, 0, 2, 1, 3]].reset_index(drop=True)
    before = prices.copy(deep=True)

    result = _service_result(prices)

    assert [step.as_of for step in result.steps] == sorted(
        step.as_of for step in result.steps
    )
    assert_frame_equal(prices, before)


def test_invalid_price_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _service_result(_prices(0))

    multi_symbol = _prices(2)
    multi_symbol.loc[1, "symbol"] = "AAPL"
    with pytest.raises(ValueError, match="matching symbol"):
        _service_result(multi_symbol)

    multi_provider = _prices(2)
    multi_provider.loc[1, "provider"] = "other"
    with pytest.raises(ValueError, match="one provider"):
        _service_result(multi_provider)

    duplicate = _prices(2)
    duplicate.loc[1, "timestamp"] = duplicate.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        _service_result(duplicate)

    naive = _prices(2)
    naive["timestamp"] = naive["timestamp"].astype(object)
    naive.loc[0, "timestamp"] = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        _service_result(naive)


def test_start_end_must_be_aware_and_ordered() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _service_result(start=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="earlier than or equal"):
        _service_result(start=_START + timedelta(days=2), end=_START)
    with pytest.raises(ValueError, match="no replay timestamps"):
        _service_result(
            start=_START - timedelta(days=10),
            end=_START - timedelta(days=1),
        )


def test_state_model_identity_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="model_id must match"):
        HistoricalReplayService().run(
            _prices(2),
            symbol="MSFT",
            interval="1day",
            strategies=create_strategy_collection([]),
            state_model=BadStateModel(),
        )


def test_replay_package_has_no_forbidden_dependencies() -> None:
    roots = [
        Path("src/market_platform/replay"),
        Path("src/market_platform/observation/history.py"),
    ]
    forbidden = {
        "market_platform.research",
        "market_platform.cli",
        "market_platform.provider",
        "market_platform.portfolio",
        "market_platform.risk",
        "market_platform.execution",
    }
    imported: set[str] = set()
    for root in roots:
        paths = sorted(root.glob("*.py")) if root.is_dir() else [root]
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)

    violations = {
        module
        for module in imported
        for forbidden_module in forbidden
        if module == forbidden_module or module.startswith(f"{forbidden_module}.")
    }
    assert not violations

def _two_baseline_strategies():
    return create_strategy_collection(
        (BaselineTrendRegimeStrategy(), BaselineVolatilityRegimeStrategy())
    )


def _reference_public_structure_service() -> PriceStructureService:
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


@pytest.mark.parametrize("bar_count", [50, 100, 300])
def test_fast_structure_path_preserves_replay_result_dict(
    bar_count: int,
) -> None:
    prices = _prices(bar_count)
    strategies = _two_baseline_strategies()
    fast_result = HistoricalReplayService().run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
    )
    reference_result = HistoricalReplayService(
        price_structure_service=_reference_public_structure_service(),
    ).run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
    )

    assert fast_result.to_dict() == reference_result.to_dict()
    assert fast_result.to_dict() == HistoricalReplayService().run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
    ).to_dict()


def test_fast_structure_path_preserves_replay_future_data_invariance() -> None:
    prices = _prices(100)
    strategies = _two_baseline_strategies()
    as_of = prices.iloc[59]["timestamp"].to_pydatetime()
    historical = prices.iloc[:60].copy(deep=True)
    with_future = pd.concat(
        [
            historical,
            pd.DataFrame(
                {
                    "symbol": ["MSFT"],
                    "timestamp": [as_of + timedelta(days=1)],
                    "open": [9999.0],
                    "high": [10000.0],
                    "low": [9998.0],
                    "close": [9999.0],
                    "volume": [1_000_000.0],
                    "provider": ["test-provider"],
                }
            ),
        ],
        ignore_index=True,
    )

    historical_step = HistoricalReplayService().run(
        historical,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
        start=as_of,
        end=as_of,
    ).steps[0]
    future_step = HistoricalReplayService().run(
        with_future,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
        start=as_of,
        end=as_of,
    ).steps[0]

    assert future_step.to_dict() == historical_step.to_dict()


def _prefix_reference_signal_snapshots(
    prices: pd.DataFrame,
) -> tuple[signal_service.MarketSignalSnapshot, ...]:
    return tuple(
        signal_service.calculate_market_signals(prices.iloc[: position + 1])
        for position in range(len(prices))
    )


def test_signal_precompute_replay_preserves_prefix_reference_result_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = _prices(100)
    strategies = _two_baseline_strategies()
    optimized = HistoricalReplayService().run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
    )
    monkeypatch.setattr(
        replay_service,
        "precompute_market_signal_snapshots",
        _prefix_reference_signal_snapshots,
    )

    reference = HistoricalReplayService().run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
    )

    assert optimized.to_dict() == reference.to_dict()


def test_signal_precompute_replay_uses_full_frame_positions_for_start_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = _prices(120)
    start = _START + timedelta(days=100)
    end = _START + timedelta(days=102)
    full_result = HistoricalReplayService().run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=_two_baseline_strategies(),
        state_model=BaselineMarketStateModel(),
    )
    observed_lengths: list[int] = []
    real_precompute = replay_service.precompute_market_signal_snapshots

    def recording_precompute(
        frame: pd.DataFrame,
    ) -> tuple[signal_service.MarketSignalSnapshot, ...]:
        observed_lengths.append(len(frame))
        return real_precompute(frame)

    monkeypatch.setattr(
        replay_service,
        "precompute_market_signal_snapshots",
        recording_precompute,
    )

    result = HistoricalReplayService().run(
        prices,
        symbol="MSFT",
        interval="1day",
        strategies=_two_baseline_strategies(),
        state_model=BaselineMarketStateModel(),
        start=start,
        end=end,
    )
    assert observed_lengths == [120]
    assert result.to_dict()["steps"] == full_result.to_dict()["steps"][100:103]


def test_replay_calls_signal_precompute_once_and_not_public_prefix_calculator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    real_precompute = replay_service.precompute_market_signal_snapshots

    def counting_precompute(
        frame: pd.DataFrame,
    ) -> tuple[signal_service.MarketSignalSnapshot, ...]:
        nonlocal calls
        calls += 1
        return real_precompute(frame)

    def exploding_calculate(
        prices: pd.DataFrame,
    ) -> signal_service.MarketSignalSnapshot:
        raise AssertionError("calculate_market_signals must not run per replay step")

    monkeypatch.setattr(
        replay_service,
        "precompute_market_signal_snapshots",
        counting_precompute,
    )
    monkeypatch.setattr(signal_service, "calculate_market_signals", exploding_calculate)

    result = HistoricalReplayService().run(
        _prices(20),
        symbol="MSFT",
        interval="1day",
        strategies=_two_baseline_strategies(),
        state_model=BaselineMarketStateModel(),
    )

    assert calls == 1
    assert result.step_count == 20


def test_signal_precompute_replay_preserves_strategy_and_empty_collection_shapes(
) -> None:
    strategies = _two_baseline_strategies()
    result = HistoricalReplayService().run(
        _prices(30),
        symbol="MSFT",
        interval="1day",
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
    )
    empty = HistoricalReplayService().run(
        _prices(30),
        symbol="MSFT",
        interval="1day",
        strategies=create_strategy_collection([]),
        state_model=BaselineMarketStateModel(),
    )

    assert [strategy.strategy_id for strategy in result.strategies] == [
        strategy.strategy_id for strategy in strategies.strategies
    ]
    assert result.step_count == 30
    assert all(len(step.strategy_result.evaluations) == 2 for step in result.steps)
    assert empty.step_count == 30
    assert empty.strategies == ()
    assert all(step.strategy_result.evaluations == () for step in empty.steps)
