from __future__ import annotations

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
from market_platform.strategy import validate_strategy_inputs

_AS_OF = datetime(2026, 7, 17, tzinfo=UTC)


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
            input_fingerprint="sha256:observation",
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
            observation_fingerprint="sha256:observation",
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


def test_matching_strategy_inputs_pass_validation() -> None:
    validate_strategy_inputs(_state(), _observation())


def test_symbol_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="symbols must match"):
        validate_strategy_inputs(_state(symbol="AAPL"), _observation())


def test_interval_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="intervals must match"):
        validate_strategy_inputs(_state(interval="1hour"), _observation())


def test_as_of_mismatch_is_rejected_without_tolerance() -> None:
    with pytest.raises(ValueError, match="as_of values must match"):
        validate_strategy_inputs(
            _state(as_of=_AS_OF - timedelta(microseconds=1)),
            _observation(),
        )


def test_observation_fingerprint_conflict_is_rejected() -> None:
    provenance = StateModelProvenance(
        model_id="baseline-market-state",
        model_version="v1",
        parameters={},
        observation_fingerprint="sha256:different",
    )

    with pytest.raises(ValueError, match="fingerprints must match"):
        validate_strategy_inputs(_state(provenance=provenance), _observation())


def test_missing_state_fingerprint_is_not_inferred_or_rejected() -> None:
    provenance = StateModelProvenance(
        model_id="custom-state",
        model_version="v1",
        parameters={},
        observation_fingerprint=None,
    )

    validate_strategy_inputs(_state(provenance=provenance), _observation())

    assert provenance.observation_fingerprint is None


def test_validation_does_not_modify_inputs() -> None:
    state = _state()
    observation = _observation()
    state_before = state.to_dict()
    observation_before = observation.to_dict()

    validate_strategy_inputs(state, observation)

    assert state.to_dict() == state_before
    assert observation.to_dict() == observation_before


@pytest.mark.parametrize(
    ("state", "observation", "message"),
    [
        (object(), _observation(), "state must be a MarketState"),
        (_state(), object(), "observation must be a MarketObservation"),
    ],
)
def test_validation_rejects_wrong_input_types(
    state: object,
    observation: object,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        validate_strategy_inputs(state, observation)  # type: ignore[arg-type]
