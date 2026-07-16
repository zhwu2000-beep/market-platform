from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

import market_platform.observation as observation_package
import market_platform.state as state_package
import market_platform.strategy as strategy_package
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
    Strategy,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyProvenance,
    validate_strategy_inputs,
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


def _state() -> MarketState:
    return MarketState(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        provenance=StateModelProvenance(
            model_id="baseline-market-state",
            model_version="v1",
            parameters={},
            observation_fingerprint=_FINGERPRINT,
        ),
        directional_regime=DirectionalRegime.UP,
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.POSITIVE,
        volatility_regime=VolatilityRegime.NORMAL,
        structure_state=StructureState.AVAILABLE,
        quality=StateQuality.COMPLETE,
    )


@dataclass(frozen=True, slots=True)
class FakeStrategy:
    status: StrategyEvaluationStatus

    @property
    def strategy_id(self) -> str:
        return "fake-strategy"

    @property
    def strategy_version(self) -> str:
        return "v1"

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        validate_strategy_inputs(state, observation)
        required_inputs = ("directional_regime",)
        missing_inputs = (
            required_inputs
            if self.status is StrategyEvaluationStatus.INSUFFICIENT_DATA
            else ()
        )
        return StrategyEvaluation(
            symbol=state.symbol,
            interval=state.interval,
            as_of=state.as_of,
            provenance=StrategyProvenance(
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                parameters={"mode": "test"},
                observation_fingerprint=(
                    state.provenance.observation_fingerprint
                ),
                state_model_id=state.provenance.model_id,
                state_model_version=state.provenance.model_version,
            ),
            status=self.status,
            rationale=f"Fake evaluation status: {self.status.value}.",
            required_inputs=required_inputs,
            missing_inputs=missing_inputs,
        )


class MissingEvaluate:
    strategy_id = "missing-evaluate"
    strategy_version = "v1"


class MissingStrategyId:
    strategy_version = "v1"

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        raise NotImplementedError


class MissingStrategyVersion:
    strategy_id = "missing-version"

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        raise NotImplementedError


def test_fake_strategy_satisfies_runtime_checkable_protocol() -> None:
    strategy = FakeStrategy(StrategyEvaluationStatus.APPLICABLE)

    assert isinstance(strategy, Strategy)
    assert strategy.strategy_id == "fake-strategy"
    assert strategy.strategy_version == "v1"


@pytest.mark.parametrize(
    "candidate",
    [MissingEvaluate(), MissingStrategyId(), MissingStrategyVersion()],
)
def test_incomplete_objects_do_not_satisfy_strategy_protocol(candidate: object) -> None:
    assert not isinstance(candidate, Strategy)


def test_fake_strategy_is_deterministic_for_identical_inputs() -> None:
    strategy: Strategy = FakeStrategy(StrategyEvaluationStatus.APPLICABLE)
    state = _state()
    observation = _observation()

    assert strategy.evaluate(state, observation) == strategy.evaluate(
        state,
        observation,
    )


def test_fake_strategy_does_not_modify_inputs() -> None:
    strategy: Strategy = FakeStrategy(StrategyEvaluationStatus.APPLICABLE)
    state = _state()
    observation = _observation()
    state_before = state.to_dict()
    observation_before = observation.to_dict()

    strategy.evaluate(state, observation)

    assert state.to_dict() == state_before
    assert observation.to_dict() == observation_before


@pytest.mark.parametrize("status", list(StrategyEvaluationStatus))
def test_fake_strategy_can_return_every_evaluation_status(
    status: StrategyEvaluationStatus,
) -> None:
    evaluation = FakeStrategy(status).evaluate(_state(), _observation())

    assert evaluation.status is status
    assert bool(evaluation.missing_inputs) is (
        status is StrategyEvaluationStatus.INSUFFICIENT_DATA
    )


def _imported_modules(package_dir: Path) -> set[str]:
    imported: set[str] = set()
    for source_path in package_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
    return imported


def _package_dir(package: object) -> Path:
    package_file = getattr(package, "__file__", None)
    assert isinstance(package_file, str)
    return Path(package_file).parent


def test_strategy_package_has_no_forbidden_imports() -> None:
    forbidden = (
        "market_platform.research",
        "market_platform.cli",
        "market_platform.data",
        "market_platform.provider",
        "market_platform.broker",
        "market_platform.execution",
        "market_platform.portfolio",
        "market_platform.risk",
    )
    imported = _imported_modules(_package_dir(strategy_package))

    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported
        for prefix in forbidden
    )


@pytest.mark.parametrize("package", [observation_package, state_package])
def test_upstream_packages_do_not_import_strategy(package: object) -> None:
    imported = _imported_modules(_package_dir(package))

    assert not any(
        module == "market_platform.strategy"
        or module.startswith("market_platform.strategy.")
        for module in imported
    )
