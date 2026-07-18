"""Pure validation for strategy evaluation boundary contracts."""

from __future__ import annotations

from collections.abc import Sequence

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState
from market_platform.strategy.models import StrategyEvaluation, StrategyRunResult
from market_platform.strategy.protocol import Strategy


def validate_strategy_inputs(
    state: MarketState,
    observation: MarketObservation,
) -> None:
    """Require an exact shared point-in-time identity and compatible provenance."""

    if not isinstance(state, MarketState):
        raise TypeError("state must be a MarketState")
    if not isinstance(observation, MarketObservation):
        raise TypeError("observation must be a MarketObservation")
    identity = observation.identity
    if state.symbol != identity.symbol:
        raise ValueError("state and observation symbols must match")
    if state.interval != identity.interval:
        raise ValueError("state and observation intervals must match")
    if state.as_of != identity.as_of:
        raise ValueError("state and observation as_of values must match")

    state_fingerprint = state.provenance.observation_fingerprint
    observation_fingerprint = observation.provenance.input_fingerprint
    if (
        state_fingerprint is not None
        and observation_fingerprint is not None
        and state_fingerprint != observation_fingerprint
    ):
        raise ValueError("state and observation fingerprints must match")


def validate_strategy_evaluation(
    evaluation: object,
    strategy: Strategy,
    state: MarketState,
    observation: MarketObservation,
) -> None:
    """Require an evaluation to match its strategy and point-in-time inputs."""

    if not isinstance(evaluation, StrategyEvaluation):
        raise TypeError("strategy must return a StrategyEvaluation")

    identity = observation.identity
    if evaluation.symbol != identity.symbol:
        raise ValueError("evaluation and observation symbols must match")
    if evaluation.interval != identity.interval:
        raise ValueError("evaluation and observation intervals must match")
    if evaluation.as_of != identity.as_of:
        raise ValueError("evaluation and observation as_of values must match")

    provenance = evaluation.provenance
    if provenance.strategy_id != strategy.strategy_id:
        raise ValueError("evaluation strategy_id must match strategy")
    if provenance.strategy_version != strategy.strategy_version:
        raise ValueError("evaluation strategy_version must match strategy")
    if provenance.state_model_id != state.provenance.model_id:
        raise ValueError("evaluation state_model_id must match state")
    if provenance.state_model_version != state.provenance.model_version:
        raise ValueError("evaluation state_model_version must match state")


def validate_strategy_run_result(
    result: object,
    strategies: Sequence[Strategy],
    state: MarketState,
    observation: MarketObservation,
) -> None:
    """Require a run result to match its strategies and point-in-time inputs."""

    if not isinstance(result, StrategyRunResult):
        raise TypeError("result must be a StrategyRunResult")

    identity = observation.identity
    if result.symbol != identity.symbol or result.symbol != state.symbol:
        raise ValueError("run result symbol must match inputs")
    if result.interval != identity.interval or result.interval != state.interval:
        raise ValueError("run result interval must match inputs")
    if result.as_of != identity.as_of or result.as_of != state.as_of:
        raise ValueError("run result as_of must match inputs")
    if result.observation_fingerprint != observation.provenance.input_fingerprint:
        raise ValueError("run result fingerprint must match observation")
    state_fingerprint = state.provenance.observation_fingerprint
    if (
        state_fingerprint is not None
        and result.observation_fingerprint != state_fingerprint
    ):
        raise ValueError("run result fingerprint must match state")
    if result.state_model_id != state.provenance.model_id:
        raise ValueError("run result state_model_id must match state")
    if result.state_model_version != state.provenance.model_version:
        raise ValueError("run result state_model_version must match state")
    if len(result.evaluations) != len(strategies):
        raise ValueError("run result evaluations must match strategies")

    for evaluation, strategy in zip(result.evaluations, strategies, strict=True):
        validate_strategy_evaluation(
            evaluation,
            strategy,
            state,
            observation,
        )
        evaluation_fingerprint = evaluation.provenance.observation_fingerprint
        if (
            evaluation_fingerprint is not None
            and evaluation_fingerprint != result.observation_fingerprint
        ):
            raise ValueError(
                "evaluation fingerprint must match run result"
            )
