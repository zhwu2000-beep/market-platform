"""Baseline volatility-regime strategy implementation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState, VolatilityRegime
from market_platform.strategy.configuration import StrategyConfiguration
from market_platform.strategy.evaluation import build_strategy_evaluation
from market_platform.strategy.models import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
)
from market_platform.strategy.validation import validate_strategy_inputs

_STRATEGY_ID = "baseline_volatility_regime"
_STRATEGY_VERSION = "1.0.0"
_COMPATIBLE_VOLATILITY_REGIME_VALUES = (
    VolatilityRegime.LOW.value,
    VolatilityRegime.NORMAL.value,
)
_UNAVAILABLE_VOLATILITY_REGIME_VALUES = (VolatilityRegime.UNAVAILABLE.value,)
_INDETERMINATE_POLICY = "not_applicable"


def _default_configuration() -> StrategyConfiguration:
    return StrategyConfiguration(
        strategy_id=_STRATEGY_ID,
        strategy_version=_STRATEGY_VERSION,
        parameters={
            "compatible_volatility_regimes": _COMPATIBLE_VOLATILITY_REGIME_VALUES,
            "unavailable_volatility_regimes": _UNAVAILABLE_VOLATILITY_REGIME_VALUES,
            "indeterminate_policy": _INDETERMINATE_POLICY,
        },
    )


@dataclass(frozen=True, slots=True)
class BaselineVolatilityRegimeStrategy:
    """Evaluate whether volatility regime satisfies baseline conditions."""

    configuration: StrategyConfiguration = field(
        default_factory=_default_configuration
    )

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, StrategyConfiguration):
            raise TypeError("configuration must be a StrategyConfiguration")
        if self.configuration.strategy_id != _STRATEGY_ID:
            raise ValueError(f"configuration strategy_id must be {_STRATEGY_ID}")
        if self.configuration.strategy_version != _STRATEGY_VERSION:
            raise ValueError(
                f"configuration strategy_version must be {_STRATEGY_VERSION}"
            )

        compatible = _compatible_volatility_regimes(
            self.configuration.parameters
        )
        if compatible != frozenset(
            VolatilityRegime(value)
            for value in _COMPATIBLE_VOLATILITY_REGIME_VALUES
        ):
            raise ValueError(
                "compatible_volatility_regimes must match baseline rules"
            )

        unavailable = _unavailable_volatility_regimes(
            self.configuration.parameters
        )
        if unavailable != frozenset(
            VolatilityRegime(value)
            for value in _UNAVAILABLE_VOLATILITY_REGIME_VALUES
        ):
            raise ValueError(
                "unavailable_volatility_regimes must match baseline rules"
            )

        if _indeterminate_policy(self.configuration.parameters) != (
            _INDETERMINATE_POLICY
        ):
            raise ValueError("indeterminate_policy must be not_applicable")

    @property
    def strategy_id(self) -> str:
        """Return the configured strategy identity."""

        return self.configuration.strategy_id

    @property
    def strategy_version(self) -> str:
        """Return the configured strategy version."""

        return self.configuration.strategy_version

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        """Evaluate current market state against configured regime rules."""

        validate_strategy_inputs(state, observation)

        evidence = (_volatility_evidence_from_state(state),)
        compatible = _compatible_volatility_regimes(
            self.configuration.parameters
        )
        unavailable = _unavailable_volatility_regimes(
            self.configuration.parameters
        )
        indeterminate_policy = _indeterminate_policy(
            self.configuration.parameters
        )

        missing_inputs: tuple[str, ...] = ()
        if state.volatility_regime in unavailable:
            status = StrategyEvaluationStatus.INSUFFICIENT_DATA
            rationale = "required volatility regime is unavailable"
            missing_inputs = ("volatility_regime",)
        elif state.volatility_regime in compatible:
            status = StrategyEvaluationStatus.APPLICABLE
            rationale = (
                "volatility regime is compatible with the configured "
                "baseline conditions"
            )
        elif (
            state.volatility_regime is VolatilityRegime.INDETERMINATE
            and indeterminate_policy == _INDETERMINATE_POLICY
        ):
            status = StrategyEvaluationStatus.NOT_APPLICABLE
            rationale = (
                "indeterminate volatility is not applicable under the "
                "configured policy"
            )
        else:
            status = StrategyEvaluationStatus.NOT_APPLICABLE
            rationale = (
                "volatility regime is not compatible with the configured "
                "baseline conditions"
            )

        return build_strategy_evaluation(
            strategy=self,
            state=state,
            observation=observation,
            status=status,
            rationale=rationale,
            evidence=evidence,
            required_inputs=("volatility_regime",),
            missing_inputs=missing_inputs,
        )


def _compatible_volatility_regimes(
    parameters: Mapping[str, object],
) -> frozenset[VolatilityRegime]:
    return frozenset(
        VolatilityRegime(item)
        for item in _required_text_items(
            parameters,
            "compatible_volatility_regimes",
        )
    )


def _unavailable_volatility_regimes(
    parameters: Mapping[str, object],
) -> frozenset[VolatilityRegime]:
    return frozenset(
        VolatilityRegime(item)
        for item in _required_text_items(
            parameters,
            "unavailable_volatility_regimes",
        )
    )


def _indeterminate_policy(parameters: Mapping[str, object]) -> str:
    value = parameters.get("indeterminate_policy")
    if not isinstance(value, str):
        raise TypeError("indeterminate_policy must be a string")
    policy = value.strip()
    if not policy:
        raise ValueError("indeterminate_policy must not be empty")
    return policy


def _required_text_items(
    parameters: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = parameters.get(key)
    if not isinstance(value, tuple):
        raise TypeError(f"{key} must be a tuple")
    if not value:
        raise ValueError(f"{key} must not be empty")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{key} elements must be strings")
        items.append(item)
    return tuple(items)


def _volatility_evidence_from_state(state: MarketState) -> StrategyEvidence:
    return StrategyEvidence(
        source=StrategyEvidenceSource.MARKET_STATE,
        field="volatility_regime",
        observed_value=state.volatility_regime.value,
        rationale="volatility_regime read from MarketState",
        observed_at=state.as_of,
    )


__all__ = ["BaselineVolatilityRegimeStrategy"]
