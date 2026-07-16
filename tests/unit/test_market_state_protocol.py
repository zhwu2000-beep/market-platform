from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import market_platform.state as state_package
from market_platform.observation import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
)
from market_platform.state import (
    DirectionalRegime,
    MarketState,
    MarketStateModel,
    MomentumRegime,
    StateModelProvenance,
    StateQuality,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)

_AS_OF = datetime(2026, 7, 16, tzinfo=UTC)


class FakeMarketStateModel:
    @property
    def model_id(self) -> str:
        return "fake-state-model"

    @property
    def model_version(self) -> str:
        return "v1"

    def evaluate(self, observation: MarketObservation) -> MarketState:
        return MarketState(
            symbol=observation.identity.symbol,
            interval=observation.identity.interval,
            as_of=observation.identity.as_of,
            provenance=StateModelProvenance(
                model_id=self.model_id,
                model_version=self.model_version,
                parameters={},
                observation_fingerprint=(
                    observation.provenance.input_fingerprint
                ),
            ),
            directional_regime=DirectionalRegime.UNAVAILABLE,
            trend_regime=TrendRegime.UNAVAILABLE,
            momentum_regime=MomentumRegime.UNAVAILABLE,
            volatility_regime=VolatilityRegime.UNAVAILABLE,
            structure_state=StructureState.UNAVAILABLE,
            quality=StateQuality.UNAVAILABLE,
            missing_inputs=("signal_facts", "structure_facts"),
        )


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
            input_fingerprint="sha256:observation",
        ),
    )


def test_fake_model_satisfies_runtime_checkable_protocol() -> None:
    model = FakeMarketStateModel()

    assert isinstance(model, MarketStateModel)
    assert model.model_id == "fake-state-model"
    assert model.model_version == "v1"


def test_protocol_evaluate_accepts_observation_and_returns_state() -> None:
    model: MarketStateModel = FakeMarketStateModel()
    observation = _observation()

    state = model.evaluate(observation)

    assert state.symbol == observation.identity.symbol
    assert state.interval == observation.identity.interval
    assert state.as_of == observation.identity.as_of
    assert state.provenance.observation_fingerprint == "sha256:observation"
    assert state.quality is StateQuality.UNAVAILABLE


def test_state_package_has_no_forbidden_business_layer_imports() -> None:
    package_file = state_package.__file__
    assert package_file is not None
    package_dir = Path(package_file).parent
    forbidden = (
        "market_platform.research",
        "market_platform.strategy",
        "market_platform.cli",
    )

    imported_modules: set[str] = set()
    for source_path in package_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)

    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden
    )
