from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError

import pytest

from market_platform.strategy import StrategyConfiguration, StrategyProvenance


def _configuration(**overrides: object) -> StrategyConfiguration:
    values: dict[str, object] = {
        "strategy_id": " trend-strategy ",
        "strategy_version": " v1 ",
        "parameters": {
            "threshold": 0.25,
            "inputs": ["trend", "momentum"],
        },
    }
    values.update(overrides)
    return StrategyConfiguration(**values)  # type: ignore[arg-type]


def _provenance(**overrides: object) -> StrategyProvenance:
    values: dict[str, object] = {
        "strategy_id": "trend-strategy",
        "strategy_version": "v1",
        "parameters": {},
        "observation_fingerprint": "sha256:observation",
        "state_model_id": "baseline-market-state",
        "state_model_version": "v1",
    }
    values.update(overrides)
    return StrategyProvenance(**values)  # type: ignore[arg-type]


def test_strategy_configuration_is_frozen_and_uses_slots() -> None:
    configuration = _configuration()

    assert not hasattr(configuration, "__dict__")
    with pytest.raises(FrozenInstanceError):
        configuration.strategy_id = "replacement"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        configuration.fingerprint = "replacement"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("strategy_id", " "),
        ("strategy_version", " "),
    ],
)
def test_strategy_configuration_rejects_empty_identity(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        _configuration(**{field_name: value})


def test_strategy_configuration_deeply_freezes_parameters() -> None:
    nested = {"minimum": 0.25}
    inputs = ["trend", {"name": "momentum"}]
    parameters: dict[str, object] = {
        "thresholds": nested,
        "inputs": inputs,
    }

    configuration = _configuration(parameters=parameters)
    nested["minimum"] = 0.75
    inputs.append("volatility")
    parameters["replacement"] = True

    assert isinstance(configuration.parameters, Mapping)
    assert configuration.to_dict()["parameters"] == {
        "inputs": ["trend", {"name": "momentum"}],
        "thresholds": {"minimum": 0.25},
    }
    with pytest.raises(TypeError):
        configuration.parameters["replacement"] = True  # type: ignore[index]
    thresholds = configuration.parameters["thresholds"]
    assert isinstance(thresholds, Mapping)
    with pytest.raises(TypeError):
        thresholds["minimum"] = 0.75  # type: ignore[index]


def test_lists_and_tuples_are_frozen_as_tuples() -> None:
    configuration = _configuration(
        parameters={
            "list_value": [1, 2],
            "tuple_value": (3, 4),
        }
    )

    assert configuration.parameters["list_value"] == (1, 2)
    assert configuration.parameters["tuple_value"] == (3, 4)
    assert isinstance(configuration.parameters["list_value"], tuple)
    assert isinstance(configuration.parameters["tuple_value"], tuple)


def test_sets_are_frozen_as_frozensets() -> None:
    values = {"trend", "momentum"}

    configuration = _configuration(parameters={"inputs": values})
    values.add("volatility")

    assert configuration.parameters["inputs"] == frozenset(
        {"trend", "momentum"}
    )
    assert isinstance(configuration.parameters["inputs"], frozenset)


@pytest.mark.parametrize(
    "value",
    [
        object(),
        lambda: None,
        StrategyConfiguration,
    ],
)
def test_unserializable_parameter_values_are_rejected(value: object) -> None:
    with pytest.raises(TypeError, match="JSON-compatible"):
        _configuration(parameters={"invalid": value})


def test_identical_configuration_inputs_have_identical_fingerprints() -> None:
    first = _configuration()
    second = _configuration()

    assert first.fingerprint == second.fingerprint
    assert first.fingerprint.startswith("sha256:")
    assert len(first.fingerprint) == len("sha256:") + 64


def test_parameter_change_changes_fingerprint() -> None:
    first = _configuration(parameters={"threshold": 0.25})
    second = _configuration(parameters={"threshold": 0.5})

    assert first.fingerprint != second.fingerprint


def test_mapping_key_order_does_not_change_fingerprint() -> None:
    first = _configuration(
        parameters={
            "threshold": 0.25,
            "inputs": ["trend", "momentum"],
        }
    )
    second = _configuration(
        parameters={
            "inputs": ["trend", "momentum"],
            "threshold": 0.25,
        }
    )

    assert first.fingerprint == second.fingerprint


def test_set_iteration_order_does_not_change_fingerprint() -> None:
    first = _configuration(parameters={"inputs": {"trend", "momentum"}})
    second = _configuration(parameters={"inputs": {"momentum", "trend"}})

    assert first.fingerprint == second.fingerprint


def test_configuration_to_dict_is_json_compatible() -> None:
    configuration = _configuration(
        parameters={
            "inputs": {"trend", "momentum"},
            "thresholds": {"minimum": 0.25},
        }
    )

    payload = configuration.to_dict()

    assert payload == {
        "strategy_id": "trend-strategy",
        "strategy_version": "v1",
        "parameters": {
            "inputs": ["momentum", "trend"],
            "thresholds": {"minimum": 0.25},
        },
        "fingerprint": configuration.fingerprint,
    }
    json.dumps(payload)


def test_strategy_provenance_preserves_configuration_fingerprint() -> None:
    configuration = _configuration()

    provenance = _provenance(
        configuration_fingerprint=configuration.fingerprint
    )

    assert provenance.configuration_fingerprint == configuration.fingerprint
    assert (
        provenance.to_dict()["configuration_fingerprint"]
        == configuration.fingerprint
    )


def test_legacy_strategy_provenance_construction_remains_valid() -> None:
    provenance = _provenance()

    assert provenance.configuration_fingerprint is None
    assert provenance.to_dict()["configuration_fingerprint"] is None
