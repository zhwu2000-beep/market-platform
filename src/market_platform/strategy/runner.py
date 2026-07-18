"""Synchronous orchestration boundary for strategy evaluations."""

from __future__ import annotations

from collections.abc import Sequence

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState
from market_platform.strategy.models import StrategyEvaluation, StrategyRunResult
from market_platform.strategy.protocol import Strategy
from market_platform.strategy.validation import (
    validate_strategy_evaluation,
    validate_strategy_inputs,
    validate_strategy_run_result,
)


class StrategyRunnerError(RuntimeError):
    """Raised when a strategy invocation or its returned contract fails."""


class StrategyRunner:
    """Evaluate strategies synchronously in input order without retained state."""

    def evaluate(
        self,
        strategies: Sequence[Strategy],
        *,
        observation: MarketObservation,
        state: MarketState,
    ) -> StrategyRunResult:
        """Validate inputs, invoke strategies, and collect valid evaluations."""

        validate_strategy_inputs(state, observation)
        evaluations: list[StrategyEvaluation] = []
        for strategy in strategies:
            try:
                evaluation = strategy.evaluate(state, observation)
                validate_strategy_evaluation(
                    evaluation, strategy, state, observation
                )
            except Exception as exc:
                raise StrategyRunnerError(
                    f"strategy {_strategy_label(strategy)} evaluation failed"
                ) from exc
            evaluations.append(evaluation)
        try:
            result = StrategyRunResult(
                symbol=state.symbol,
                interval=state.interval,
                as_of=state.as_of,
                observation_fingerprint=(
                    observation.provenance.input_fingerprint
                ),
                state_model_id=state.provenance.model_id,
                state_model_version=state.provenance.model_version,
                evaluations=tuple(evaluations),
            )
            validate_strategy_run_result(
                result,
                strategies,
                state,
                observation,
            )
        except Exception as exc:
            raise StrategyRunnerError(
                "strategy run result validation failed"
            ) from exc
        return result


def _strategy_label(strategy: object) -> str:
    try:
        strategy_id = strategy.strategy_id  # type: ignore[attr-defined]
        strategy_version = strategy.strategy_version  # type: ignore[attr-defined]
    except Exception:
        return type(strategy).__name__
    return f"{strategy_id}@{strategy_version}"


__all__ = ["StrategyRunner", "StrategyRunnerError"]
