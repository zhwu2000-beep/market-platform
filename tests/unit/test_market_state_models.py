from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone

import pytest

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

_AS_OF = datetime(2026, 7, 16, tzinfo=UTC)


def _provenance() -> StateModelProvenance:
    return StateModelProvenance(
        model_id="baseline-market-state",
        model_version="v1",
        parameters={"thresholds": {"up": 0.2}, "components": ["trend"]},
        observation_fingerprint="sha256:abc123",
    )


def _state(**overrides: object) -> MarketState:
    values: dict[str, object] = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF,
        "provenance": _provenance(),
        "directional_regime": DirectionalRegime.UP,
        "trend_regime": TrendRegime.UP,
        "momentum_regime": MomentumRegime.POSITIVE,
        "volatility_regime": VolatilityRegime.NORMAL,
        "structure_state": StructureState.OBSERVED,
        "quality": StateQuality.COMPLETE,
        "missing_inputs": (),
    }
    values.update(overrides)
    return MarketState(**values)  # type: ignore[arg-type]


def test_market_state_models_are_frozen_and_use_slots() -> None:
    provenance = _provenance()
    state = _state(provenance=provenance)

    assert not hasattr(provenance, "__dict__")
    assert not hasattr(state, "__dict__")
    with pytest.raises(FrozenInstanceError):
        provenance.model_id = "replacement"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        state.symbol = "AAPL"  # type: ignore[misc]


def test_provenance_defensively_freezes_nested_parameters() -> None:
    nested: dict[str, object] = {"up": 0.2}
    components = ["trend"]
    parameters: dict[str, object] = {
        "thresholds": nested,
        "components": components,
    }

    provenance = StateModelProvenance(
        model_id="baseline-market-state",
        model_version="v1",
        parameters=parameters,
    )
    nested["up"] = 0.8
    components.append("momentum")
    parameters["new"] = True

    assert provenance.to_dict()["parameters"] == {
        "thresholds": {"up": 0.2},
        "components": ["trend"],
    }
    with pytest.raises(TypeError):
        provenance.parameters["new"] = True  # type: ignore[index]
    thresholds = provenance.parameters["thresholds"]
    assert isinstance(thresholds, Mapping)
    with pytest.raises(TypeError):
        thresholds["up"] = 0.8  # type: ignore[index]


def test_market_state_normalizes_identity_and_serializes_to_json() -> None:
    state = _state(
        symbol=" msft ",
        interval=" 1day ",
        as_of=datetime(
            2026,
            7,
            16,
            8,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    )

    payload = state.to_dict()

    assert payload == {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF.isoformat(),
        "provenance": {
            "model_id": "baseline-market-state",
            "model_version": "v1",
            "parameters": {
                "thresholds": {"up": 0.2},
                "components": ["trend"],
            },
            "observation_fingerprint": "sha256:abc123",
        },
        "directional_regime": "up",
        "trend_regime": "up",
        "momentum_regime": "positive",
        "volatility_regime": "normal",
        "structure_state": "observed",
        "quality": "complete",
        "missing_inputs": [],
        "evaluation_evidence": None,
    }
    json.dumps(payload)


def test_all_state_dimensions_can_express_unavailable() -> None:
    assert DirectionalRegime.UNAVAILABLE.value == "unavailable"
    assert TrendRegime.UNAVAILABLE.value == "unavailable"
    assert MomentumRegime.UNAVAILABLE.value == "unavailable"
    assert VolatilityRegime.UNAVAILABLE.value == "unavailable"
    assert StructureState.UNAVAILABLE.value == "unavailable"
    assert StateQuality.UNAVAILABLE.value == "unavailable"


@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        ("directional_regime", "must be a DirectionalRegime"),
        ("trend_regime", "must be a TrendRegime"),
        ("momentum_regime", "must be a MomentumRegime"),
        ("volatility_regime", "must be a VolatilityRegime"),
        ("structure_state", "must be a StructureState"),
        ("quality", "must be a StateQuality"),
    ],
)
def test_market_state_rejects_raw_enum_strings(
    field_name: str,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        _state(**{field_name: "unavailable"})


def test_complete_state_rejects_missing_inputs() -> None:
    with pytest.raises(ValueError, match="complete state"):
        _state(missing_inputs=("momentum",))


def test_market_state_contains_no_decision_or_prediction_fields() -> None:
    field_names = {field.name for field in fields(MarketState)}
    forbidden = {
        "buy",
        "sell",
        "target_price",
        "probability",
        "position",
        "options",
        "prediction",
    }

    assert field_names.isdisjoint(forbidden)


@pytest.mark.parametrize("field_name", ["model_id", "model_version"])
def test_provenance_rejects_empty_identity_fields(field_name: str) -> None:
    values: dict[str, object] = {
        "model_id": "baseline-market-state",
        "model_version": "v1",
        "parameters": {},
    }
    values[field_name] = " "

    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        StateModelProvenance(**values)  # type: ignore[arg-type]


def test_market_state_requires_aware_as_of() -> None:
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        _state(as_of=datetime(2026, 7, 16))
