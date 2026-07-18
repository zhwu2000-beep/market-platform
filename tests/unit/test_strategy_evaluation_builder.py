"""Tests for the strategy evaluation construction boundary."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    StrategyConfiguration,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
    build_strategy_evaluation,
)

_AS_OF = datetime(2026, 7, 17, tzinfo=UTC)
_FINGERPRINT = "sha256:observation"


@dataclass(frozen=True, slots=True)
class FakeStrategyInstance:
    configuration: StrategyConfiguration

    @property
    def strategy_id(self) -> str:
        return self.configuration.strategy_id

    @property
    def strategy_version(self) -> str:
        return self.configuration.strategy_version


@dataclass(frozen=True, slots=True)
class MismatchedStrategyInstance:
    configuration: StrategyConfiguration

    @property
    def strategy_id(self) -> str:
        return "other"

    @property
    def strategy_version(self) -> str:
        return self.configuration.strategy_version


def _configuration() -> StrategyConfiguration:
    return StrategyConfiguration(
        strategy_id="trend",
        strategy_version="v1",
        parameters={"lookback": 20, "thresholds": [1.5, 2.0]},
    )


def _observation(**identity_overrides: object) -> MarketObservation:
    identity_values: dict[str, object] = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF,
        "window_start": datetime(2026, 4, 1, tzinfo=UTC),
        "window_end": _AS_OF,
    }
    identity_values.update(identity_overrides)
    return MarketObservation(
        identity=ObservationIdentity(**identity_values),  # type: ignore[arg-type]
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


def _strategy() -> FakeStrategyInstance:
    return FakeStrategyInstance(_configuration())


def _evidence(**overrides: object) -> StrategyEvidence:
    values: dict[str, object] = {
        "source": StrategyEvidenceSource.MARKET_STATE,
        "field": "trend_regime",
        "observed_value": "up",
        "rationale": "trend regime supports evaluation",
        "observed_at": _AS_OF,
    }
    values.update(overrides)
    return StrategyEvidence(**values)  # type: ignore[arg-type]


def test_builds_evaluation_for_fake_strategy_instance() -> None:
    evidence = (_evidence(),)

    evaluation = build_strategy_evaluation(
        strategy=_strategy(),
        state=_state(),
        observation=_observation(),
        status=StrategyEvaluationStatus.APPLICABLE,
        rationale="trend is applicable",
        evidence=evidence,
        required_inputs=("trend_regime",),
    )

    assert isinstance(evaluation, StrategyEvaluation)
    assert evaluation.symbol == "MSFT"
    assert evaluation.interval == "1day"
    assert evaluation.as_of == _AS_OF
    assert evaluation.status is StrategyEvaluationStatus.APPLICABLE
    assert evaluation.rationale == "trend is applicable"
    assert evaluation.evidence == evidence


def test_automatically_generates_complete_provenance() -> None:
    strategy = _strategy()

    evaluation = build_strategy_evaluation(
        strategy=strategy,
        state=_state(),
        observation=_observation(),
        status=StrategyEvaluationStatus.APPLICABLE,
        rationale="trend is applicable",
    )

    provenance = evaluation.provenance
    assert provenance.strategy_id == "trend"
    assert provenance.strategy_version == "v1"
    assert provenance.configuration_fingerprint == strategy.configuration.fingerprint
    assert provenance.observation_fingerprint == _FINGERPRINT
    assert provenance.state_model_id == "baseline-market-state"
    assert provenance.state_model_version == "v1"
    assert provenance.to_dict()["parameters"] == {
        "lookback": 20,
        "thresholds": [1.5, 2.0],
    }


def test_symbol_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="symbols must match"):
        build_strategy_evaluation(
            strategy=_strategy(),
            state=_state(symbol="AAPL"),
            observation=_observation(),
            status=StrategyEvaluationStatus.APPLICABLE,
            rationale="trend is applicable",
        )


def test_interval_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="intervals must match"):
        build_strategy_evaluation(
            strategy=_strategy(),
            state=_state(interval="1hour"),
            observation=_observation(),
            status=StrategyEvaluationStatus.APPLICABLE,
            rationale="trend is applicable",
        )


def test_as_of_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="as_of values must match"):
        build_strategy_evaluation(
            strategy=_strategy(),
            state=_state(as_of=_AS_OF - timedelta(seconds=1)),
            observation=_observation(),
            status=StrategyEvaluationStatus.APPLICABLE,
            rationale="trend is applicable",
        )


def test_invalid_strategy_identity_rejected() -> None:
    with pytest.raises(ValueError, match="strategy_id must come from configuration"):
        build_strategy_evaluation(
            strategy=MismatchedStrategyInstance(_configuration()),
            state=_state(),
            observation=_observation(),
            status=StrategyEvaluationStatus.APPLICABLE,
            rationale="trend is applicable",
        )


def test_future_evidence_timestamp_rejected() -> None:
    evidence = (_evidence(observed_at=_AS_OF + timedelta(seconds=1)),)

    with pytest.raises(ValueError, match="observed_at must not be later"):
        build_strategy_evaluation(
            strategy=_strategy(),
            state=_state(),
            observation=_observation(),
            status=StrategyEvaluationStatus.APPLICABLE,
            rationale="trend is applicable",
            evidence=evidence,
        )


def test_applicable_with_missing_inputs_rejected() -> None:
    with pytest.raises(ValueError, match="must not have missing_inputs"):
        build_strategy_evaluation(
            strategy=_strategy(),
            state=_state(),
            observation=_observation(),
            status=StrategyEvaluationStatus.APPLICABLE,
            rationale="trend is applicable",
            required_inputs=("trend_regime",),
            missing_inputs=("trend_regime",),
        )


def test_insufficient_data_without_missing_inputs_rejected() -> None:
    with pytest.raises(ValueError, match="must have missing_inputs"):
        build_strategy_evaluation(
            strategy=_strategy(),
            state=_state(),
            observation=_observation(),
            status=StrategyEvaluationStatus.INSUFFICIENT_DATA,
            rationale="trend data is unavailable",
            required_inputs=("trend_regime",),
        )


def test_builder_does_not_modify_inputs() -> None:
    strategy = _strategy()
    observation = _observation()
    state = _state()
    evidence = (_evidence(),)
    observation_before = observation.to_dict()
    state_before = state.to_dict()
    configuration_before = strategy.configuration.to_dict()
    evidence_before = tuple(item.to_dict() for item in evidence)

    build_strategy_evaluation(
        strategy=strategy,
        state=state,
        observation=observation,
        status=StrategyEvaluationStatus.APPLICABLE,
        rationale="trend is applicable",
        evidence=evidence,
    )

    assert observation.to_dict() == observation_before
    assert state.to_dict() == state_before
    assert strategy.configuration.to_dict() == configuration_before
    assert tuple(item.to_dict() for item in evidence) == evidence_before


def test_strategy_package_has_no_forbidden_dependencies() -> None:
    strategy_root = Path("src/market_platform/strategy")
    forbidden = {
        "market_platform.research",
        "market_platform.cli",
        "market_platform.provider",
        "market_platform.execution",
        "market_platform.portfolio",
        "market_platform.risk",
    }
    imported: set[str] = set()
    for path in strategy_root.glob("*.py"):
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
