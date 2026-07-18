from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from market_platform.observation import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
)
from market_platform.state import (
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
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyProvenance,
    StrategyRunner,
    StrategyRunnerError,
    StrategyRunResult,
)

_AS_OF = datetime(2026, 7, 17, tzinfo=UTC)
_FINGERPRINT = "sha256:observation"


def _observation() -> MarketObservation:
    return MarketObservation(
        identity=ObservationIdentity(
            symbol="MSFT",
            interval="1day",
            as_of=_AS_OF,
            window_start=datetime(2026, 4, 1, tzinfo=UTC),
            window_end=_AS_OF,
        ),
        provenance=ObservationProvenance(
            provider="test-provider",
            methodology="test-observation",
            methodology_version="v1",
            parameters={},
            input_fingerprint=_FINGERPRINT,
        ),
    )


def _state(**overrides: object) -> MarketState:
    values: dict[str, object] = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF,
        "provenance": StateModelProvenance(
            model_id="baseline-market-state",
            model_version="v1",
            parameters={},
            observation_fingerprint=_FINGERPRINT,
        ),
        "directional_regime": DirectionalRegime.UP,
        "trend_regime": TrendRegime.UP,
        "momentum_regime": MomentumRegime.POSITIVE,
        "volatility_regime": VolatilityRegime.NORMAL,
        "structure_state": StructureState.AVAILABLE,
        "quality": StateQuality.COMPLETE,
    }
    values.update(overrides)
    return MarketState(**values)  # type: ignore[arg-type]


def _evaluation(
    strategy_id: str,
    *,
    status: StrategyEvaluationStatus = StrategyEvaluationStatus.APPLICABLE,
    **overrides: object,
) -> StrategyEvaluation:
    provenance = overrides.pop(
        "provenance",
        StrategyProvenance(
            strategy_id=strategy_id,
            strategy_version="v1",
            parameters={},
            observation_fingerprint=_FINGERPRINT,
            state_model_id="baseline-market-state",
            state_model_version="v1",
        ),
    )
    values: dict[str, object] = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF,
        "provenance": provenance,
        "status": status,
        "rationale": f"{strategy_id} evaluation",
        "required_inputs": (),
        "missing_inputs": (),
    }
    if status is StrategyEvaluationStatus.INSUFFICIENT_DATA:
        values["required_inputs"] = ("trend_regime",)
        values["missing_inputs"] = ("trend_regime",)
    values.update(overrides)
    return StrategyEvaluation(**values)  # type: ignore[arg-type]


@dataclass(slots=True)
class FakeStrategy:
    strategy_id: str
    result_factory: Callable[[], object]
    calls: int = 0
    strategy_version: str = "v1"

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        self.calls += 1
        return self.result_factory()  # type: ignore[return-value]


def _strategy(
    strategy_id: str,
    *,
    status: StrategyEvaluationStatus = StrategyEvaluationStatus.APPLICABLE,
) -> FakeStrategy:
    return FakeStrategy(
        strategy_id,
        lambda: _evaluation(strategy_id, status=status),
    )


def test_single_strategy_success() -> None:
    strategy = _strategy("trend")

    results = StrategyRunner().evaluate(
        [strategy], observation=_observation(), state=_state()
    )

    assert isinstance(results, StrategyRunResult)
    assert results.evaluations == (_evaluation("trend"),)
    assert strategy.calls == 1


def test_multiple_strategies_preserve_input_order() -> None:
    strategies = [_strategy("trend"), _strategy("breakout"), _strategy("mean")]

    results = StrategyRunner().evaluate(
        strategies, observation=_observation(), state=_state()
    )

    assert tuple(
        item.provenance.strategy_id for item in results.evaluations
    ) == (
        "trend",
        "breakout",
        "mean",
    )


def test_empty_strategy_list_returns_empty_tuple() -> None:
    results = StrategyRunner().evaluate(
        [], observation=_observation(), state=_state()
    )

    assert results.evaluations == ()
    assert results.symbol == "MSFT"
    assert results.interval == "1day"
    assert results.as_of == _AS_OF
    assert results.observation_fingerprint == _FINGERPRINT
    assert results.state_model_id == "baseline-market-state"
    assert results.state_model_version == "v1"


def test_input_mismatch_is_rejected_before_any_strategy_executes() -> None:
    strategies = [_strategy("trend"), _strategy("breakout")]

    with pytest.raises(ValueError, match="symbols must match"):
        StrategyRunner().evaluate(
            strategies,
            observation=_observation(),
            state=_state(symbol="AAPL"),
        )

    assert [strategy.calls for strategy in strategies] == [0, 0]


def test_strategy_exception_is_wrapped_with_original_cause() -> None:
    failure = LookupError("strategy failed")

    def raise_failure() -> object:
        raise failure

    strategy = FakeStrategy("broken", raise_failure)

    with pytest.raises(
        StrategyRunnerError, match=r"broken@v1 evaluation failed"
    ) as caught:
        StrategyRunner().evaluate(
            [strategy], observation=_observation(), state=_state()
        )

    assert caught.value.__cause__ is failure


def test_strategy_failure_returns_no_partial_result() -> None:
    def raise_failure() -> object:
        raise LookupError("strategy failed")

    strategies = [
        _strategy("first"),
        FakeStrategy("broken", raise_failure),
        _strategy("never-called"),
    ]

    with pytest.raises(StrategyRunnerError):
        StrategyRunner().evaluate(
            strategies, observation=_observation(), state=_state()
        )

    assert [strategy.calls for strategy in strategies] == [1, 1, 0]


def test_invalid_return_type_is_wrapped() -> None:
    strategy = FakeStrategy("invalid", lambda: object())

    with pytest.raises(StrategyRunnerError) as caught:
        StrategyRunner().evaluate(
            [strategy], observation=_observation(), state=_state()
        )

    assert isinstance(caught.value.__cause__, TypeError)
    assert str(caught.value.__cause__) == "strategy must return a StrategyEvaluation"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"symbol": "AAPL"}, "symbols must match"),
        ({"interval": "1hour"}, "intervals must match"),
        ({"as_of": _AS_OF - timedelta(seconds=1)}, "as_of values must match"),
    ],
)
def test_invalid_evaluation_identity_is_wrapped(
    override: dict[str, object],
    message: str,
) -> None:
    strategy = FakeStrategy("trend", lambda: _evaluation("trend", **override))

    with pytest.raises(StrategyRunnerError) as caught:
        StrategyRunner().evaluate(
            [strategy], observation=_observation(), state=_state()
        )

    assert isinstance(caught.value.__cause__, ValueError)
    assert message in str(caught.value.__cause__)


@pytest.mark.parametrize(
    ("provenance_override", "message"),
    [
        ({"strategy_id": "other"}, "strategy_id must match"),
        ({"strategy_version": "v2"}, "strategy_version must match"),
        ({"state_model_id": "other-state"}, "state_model_id must match"),
        ({"state_model_version": "v2"}, "state_model_version must match"),
    ],
)
def test_invalid_evaluation_provenance_is_wrapped(
    provenance_override: dict[str, object],
    message: str,
) -> None:
    provenance_values: dict[str, object] = {
        "strategy_id": "trend",
        "strategy_version": "v1",
        "parameters": {},
        "observation_fingerprint": _FINGERPRINT,
        "state_model_id": "baseline-market-state",
        "state_model_version": "v1",
    }
    provenance_values.update(provenance_override)
    provenance = StrategyProvenance(**provenance_values)  # type: ignore[arg-type]
    strategy = FakeStrategy(
        "trend", lambda: _evaluation("trend", provenance=provenance)
    )

    with pytest.raises(StrategyRunnerError) as caught:
        StrategyRunner().evaluate(
            [strategy], observation=_observation(), state=_state()
        )

    assert isinstance(caught.value.__cause__, ValueError)
    assert message in str(caught.value.__cause__)


def test_insufficient_data_is_collected_normally() -> None:
    strategy = _strategy(
        "trend", status=StrategyEvaluationStatus.INSUFFICIENT_DATA
    )

    results = StrategyRunner().evaluate(
        [strategy], observation=_observation(), state=_state()
    )

    evaluation = results.evaluations[0]
    assert evaluation.status is StrategyEvaluationStatus.INSUFFICIENT_DATA
    assert evaluation.missing_inputs == ("trend_regime",)


def test_runner_does_not_modify_inputs() -> None:
    strategy = _strategy("trend")
    observation = _observation()
    state = _state()
    observation_before = observation.to_dict()
    state_before = state.to_dict()

    StrategyRunner().evaluate(
        [strategy], observation=observation, state=state
    )

    assert observation.to_dict() == observation_before
    assert state.to_dict() == state_before
