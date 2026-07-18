"""Pure construction helpers for strategy evaluations."""

from __future__ import annotations

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState
from market_platform.strategy.instance import (
    StrategyInstance,
    get_strategy_provenance,
)
from market_platform.strategy.models import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyProvenance,
)
from market_platform.strategy.validation import validate_strategy_inputs


def build_strategy_evaluation(
    *,
    strategy: StrategyInstance,
    state: MarketState,
    observation: MarketObservation,
    status: StrategyEvaluationStatus,
    rationale: str,
    evidence: tuple[StrategyEvidence, ...] = (),
    required_inputs: tuple[str, ...] = (),
    missing_inputs: tuple[str, ...] = (),
) -> StrategyEvaluation:
    """Build a strategy evaluation bound to one observation/state pair."""

    validate_strategy_inputs(state, observation)
    _validate_evidence(evidence, state)

    base_provenance = get_strategy_provenance(strategy)
    provenance = StrategyProvenance(
        strategy_id=base_provenance.strategy_id,
        strategy_version=base_provenance.strategy_version,
        parameters=base_provenance.parameters,
        observation_fingerprint=observation.provenance.input_fingerprint,
        state_model_id=state.provenance.model_id,
        state_model_version=state.provenance.model_version,
        configuration_fingerprint=base_provenance.configuration_fingerprint,
    )

    return StrategyEvaluation(
        symbol=state.symbol,
        interval=state.interval,
        as_of=state.as_of,
        provenance=provenance,
        status=status,
        rationale=rationale,
        required_inputs=required_inputs,
        missing_inputs=missing_inputs,
        evidence=evidence,
    )


def _validate_evidence(
    evidence: tuple[StrategyEvidence, ...],
    state: MarketState,
) -> None:
    if not isinstance(evidence, tuple):
        raise TypeError("evidence must be a tuple")
    for item in evidence:
        if not isinstance(item, StrategyEvidence):
            raise TypeError("evidence elements must be StrategyEvidence instances")
        if item.observed_at is not None and item.observed_at > state.as_of:
            raise ValueError("evidence observed_at must not be later than state.as_of")


__all__ = ["build_strategy_evaluation"]
