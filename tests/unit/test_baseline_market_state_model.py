from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

from market_platform.observation import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
    PriceFacts,
    SignalFacts,
    StructureFacts,
)
from market_platform.signals.models import MarketSignal
from market_platform.state import (
    BaselineMarketStateModel,
    DirectionalRegime,
    MarketState,
    MarketStateModel,
    MomentumRegime,
    StateQuality,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)
from market_platform.structure.models import PriceStructureStatus

_AS_OF = datetime(2026, 7, 16, tzinfo=UTC)


def _signal(name: str, value: float | None) -> MarketSignal:
    return MarketSignal(
        symbol="MSFT",
        name=name,
        value=value,
        timestamp=_AS_OF,
        parameters={"source": "test"},
    )


def _observation(
    *,
    include_signal_facts: bool = True,
    include_volatility: bool = True,
    include_structure_facts: bool = True,
    structure_status: PriceStructureStatus = PriceStructureStatus.OK,
) -> MarketObservation:
    signals = [
        _signal("trend", 0.08),
        _signal("momentum", 0.10),
        _signal("current_drawdown", 0.16),
        _signal("distance_from_moving_average", 0.08),
    ]
    if include_volatility:
        signals.append(_signal("realized_volatility", 0.20))
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
            methodology="market-observation",
            methodology_version="v1",
            parameters={"window": 100},
            input_fingerprint="sha256:observation-input",
        ),
        price_facts=PriceFacts(latest_price=101.0, observed_at=_AS_OF),
        signal_facts=(
            SignalFacts(symbol="MSFT", as_of=_AS_OF, signals=tuple(signals))
            if include_signal_facts
            else None
        ),
        structure_facts=(
            StructureFacts(
                status=structure_status,
                as_of=_AS_OF,
                current_price=101.0,
                atr=2.0,
                confirmed_pivots=(),
                available_zones=(),
            )
            if include_structure_facts
            else None
        ),
    )


def test_baseline_model_satisfies_protocol_and_evaluates_normal_observation() -> None:
    model: MarketStateModel = BaselineMarketStateModel()

    state = model.evaluate(_observation())

    assert isinstance(model, MarketStateModel)
    assert state.directional_regime is DirectionalRegime.STRONG_UP
    assert state.trend_regime is TrendRegime.STRONG_UP
    assert state.momentum_regime is MomentumRegime.POSITIVE
    assert state.volatility_regime is VolatilityRegime.NORMAL
    assert state.structure_state is StructureState.AVAILABLE
    assert state.quality is StateQuality.COMPLETE
    assert state.missing_inputs == ()


def test_missing_signal_facts_produces_unavailable_signal_states() -> None:
    state = BaselineMarketStateModel().evaluate(
        _observation(include_signal_facts=False)
    )

    assert state.directional_regime is DirectionalRegime.UNAVAILABLE
    assert state.trend_regime is TrendRegime.UNAVAILABLE
    assert state.momentum_regime is MomentumRegime.UNAVAILABLE
    assert state.volatility_regime is VolatilityRegime.UNAVAILABLE
    assert state.structure_state is StructureState.AVAILABLE
    assert state.quality is StateQuality.DEGRADED
    assert state.missing_inputs == ("signal_facts",)


def test_missing_volatility_is_unavailable_not_neutral() -> None:
    state = BaselineMarketStateModel().evaluate(
        _observation(include_volatility=False)
    )

    assert state.volatility_regime is VolatilityRegime.UNAVAILABLE
    assert state.quality is StateQuality.DEGRADED
    assert state.missing_inputs == ("realized_volatility",)


def test_missing_structure_facts_produces_unavailable_structure_state() -> None:
    state = BaselineMarketStateModel().evaluate(
        _observation(include_structure_facts=False)
    )

    assert state.structure_state is StructureState.UNAVAILABLE
    assert state.quality is StateQuality.DEGRADED
    assert state.missing_inputs == ("structure_facts",)


def test_unavailable_structure_status_does_not_become_available() -> None:
    state = BaselineMarketStateModel().evaluate(
        _observation(
            structure_status=PriceStructureStatus.INSUFFICIENT_DATA,
        )
    )

    assert state.structure_state is StructureState.UNAVAILABLE
    assert state.quality is StateQuality.DEGRADED
    assert state.missing_inputs == ("structure_facts",)


def test_baseline_provenance_identifies_rules_and_source_observation() -> None:
    model = BaselineMarketStateModel()

    state = model.evaluate(_observation())
    parameters = state.provenance.to_dict()["parameters"]

    assert model.model_id == "baseline_rule_state_model"
    assert model.model_version == "1.0.0"
    assert state.provenance.model_id == model.model_id
    assert state.provenance.model_version == model.model_version
    assert state.provenance.observation_fingerprint == (
        "sha256:observation-input"
    )
    assert isinstance(parameters, dict)
    assert parameters["rules_version"] == "baseline_state_rules_v1"
    assert parameters["directional_components"] == [
        "trend",
        "momentum",
        "current_drawdown",
        "distance_from_moving_average",
    ]
    assert parameters["structure_rule"] == "status_ok"


def test_evaluate_is_deterministic_for_same_observation() -> None:
    observation = _observation()
    model = BaselineMarketStateModel()

    first = model.evaluate(observation)
    second = model.evaluate(observation)

    assert first == second
    assert first.to_dict() == second.to_dict()


def test_evaluate_does_not_modify_observation() -> None:
    observation = _observation()
    before = observation.to_dict()
    signal_parameters = (
        dict(observation.signal_facts.signals[0].parameters)
        if observation.signal_facts is not None
        else {}
    )

    BaselineMarketStateModel().evaluate(observation)

    assert observation.to_dict() == before
    assert observation.signal_facts is not None
    assert observation.signal_facts.signals[0].parameters == signal_parameters


def test_baseline_state_has_no_decision_or_prediction_fields() -> None:
    forbidden = {
        "buy",
        "sell",
        "hold",
        "target",
        "target_price",
        "probability",
        "position",
        "option",
        "options",
        "prediction",
    }

    assert {field.name for field in fields(MarketState)}.isdisjoint(forbidden)


def test_state_implementation_does_not_depend_on_research() -> None:
    package = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "market_platform"
        / "state"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )

    assert "market_platform.research" not in source
