"""Baseline trend-regime strategy implementation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState, MomentumRegime, TrendRegime
from market_platform.strategy.configuration import StrategyConfiguration
from market_platform.strategy.evaluation import build_strategy_evaluation
from market_platform.strategy.models import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
)
from market_platform.strategy.validation import validate_strategy_inputs


def _default_configuration() -> StrategyConfiguration:
    return StrategyConfiguration(
        strategy_id="baseline_trend_regime",
        strategy_version="1.0.0",
        parameters={
            "required_trend_regimes": [
                TrendRegime.UP.value,
                TrendRegime.STRONG_UP.value,
            ],
            "required_momentum_regimes": [
                MomentumRegime.POSITIVE.value,
                MomentumRegime.STRONG_POSITIVE.value,
            ],
        },
    )


@dataclass(frozen=True, slots=True)
class BaselineTrendRegimeStrategy:
    """Evaluate whether trend and momentum regimes satisfy baseline conditions."""

    configuration: StrategyConfiguration = field(
        default_factory=_default_configuration
    )

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, StrategyConfiguration):
            raise TypeError("configuration must be a StrategyConfiguration")
        if self.configuration.strategy_id != "baseline_trend_regime":
            raise ValueError("configuration strategy_id must be baseline_trend_regime")
        if self.configuration.strategy_version != "1.0.0":
            raise ValueError("configuration strategy_version must be 1.0.0")
        _required_trend_regimes(self.configuration.parameters)
        _required_momentum_regimes(self.configuration.parameters)

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

        evidence = _evidence_from_state(state)
        missing_inputs = _missing_inputs(state)
        if missing_inputs:
            status = StrategyEvaluationStatus.INSUFFICIENT_DATA
            rationale = "required trend or momentum regime is unavailable"
        elif (
            state.trend_regime
            in _required_trend_regimes(self.configuration.parameters)
            and state.momentum_regime
            in _required_momentum_regimes(self.configuration.parameters)
        ):
            status = StrategyEvaluationStatus.APPLICABLE
            rationale = "trend and momentum regimes are aligned"
        else:
            status = StrategyEvaluationStatus.NOT_APPLICABLE
            rationale = (
                "trend and momentum regimes are not aligned with required regimes"
            )

        return build_strategy_evaluation(
            strategy=self,
            state=state,
            observation=observation,
            status=status,
            rationale=rationale,
            evidence=evidence,
            required_inputs=("trend_regime", "momentum_regime"),
            missing_inputs=missing_inputs,
        )


def _required_trend_regimes(
    parameters: Mapping[str, object],
) -> frozenset[TrendRegime]:
    return frozenset(
        TrendRegime(item)
        for item in _required_text_items(parameters, "required_trend_regimes")
    )


def _required_momentum_regimes(
    parameters: Mapping[str, object],
) -> frozenset[MomentumRegime]:
    return frozenset(
        MomentumRegime(item)
        for item in _required_text_items(parameters, "required_momentum_regimes")
    )


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


def _missing_inputs(state: MarketState) -> tuple[str, ...]:
    missing: list[str] = []
    if state.trend_regime is TrendRegime.UNAVAILABLE:
        missing.append("trend_regime")
    if state.momentum_regime is MomentumRegime.UNAVAILABLE:
        missing.append("momentum_regime")
    return tuple(missing)


def _evidence_from_state(state: MarketState) -> tuple[StrategyEvidence, ...]:
    return (
        _state_evidence(
            field="trend_regime",
            observed_value=state.trend_regime.value,
            observed_at=state.as_of,
        ),
        _state_evidence(
            field="momentum_regime",
            observed_value=state.momentum_regime.value,
            observed_at=state.as_of,
        ),
    )


def _state_evidence(
    *,
    field: str,
    observed_value: str,
    observed_at: object,
) -> StrategyEvidence:
    return StrategyEvidence(
        source=StrategyEvidenceSource.MARKET_STATE,
        field=field,
        observed_value=observed_value,
        rationale=f"{field} read from MarketState",
        observed_at=observed_at,  # type: ignore[arg-type]
    )


__all__ = ["BaselineTrendRegimeStrategy"]
