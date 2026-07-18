"""Tests for configured strategy instance contracts."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from market_platform.strategy.configuration import StrategyConfiguration
from market_platform.strategy.instance import (
    StrategyInstance,
    get_strategy_provenance,
)


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
    strategy_id_value: str = "other"
    strategy_version_value: str = "2.0.0"

    @property
    def strategy_id(self) -> str:
        return self.strategy_id_value

    @property
    def strategy_version(self) -> str:
        return self.strategy_version_value


class WrongConfigurationStrategy:
    configuration = {"strategy_id": "trend", "strategy_version": "1.0.0"}
    strategy_id = "trend"
    strategy_version = "1.0.0"


def _configuration() -> StrategyConfiguration:
    return StrategyConfiguration(
        strategy_id=" trend ",
        strategy_version=" 1.0.0 ",
        parameters={
            "lookback": 20,
            "thresholds": [1.5, 2.0],
            "tags": {"breakout", "trend"},
            "nested": {"enabled": True},
        },
    )


def test_fake_strategy_instance_is_runtime_compatible() -> None:
    strategy = FakeStrategyInstance(_configuration())

    assert isinstance(strategy, StrategyInstance)
    assert strategy.strategy_id == "trend"
    assert strategy.strategy_version == "1.0.0"


def test_configuration_identity_consistency_required() -> None:
    strategy = MismatchedStrategyInstance(_configuration())

    with pytest.raises(ValueError, match="strategy_id must come from configuration"):
        get_strategy_provenance(strategy)


def test_strategy_version_consistency_required() -> None:
    strategy = MismatchedStrategyInstance(
        _configuration(),
        strategy_id_value="trend",
        strategy_version_value="2.0.0",
    )

    with pytest.raises(
        ValueError,
        match="strategy_version must come from configuration",
    ):
        get_strategy_provenance(strategy)


def test_provenance_generation_preserves_configuration_identity() -> None:
    configuration = _configuration()
    strategy = FakeStrategyInstance(configuration)

    provenance = get_strategy_provenance(strategy)

    assert provenance.strategy_id == configuration.strategy_id
    assert provenance.strategy_version == configuration.strategy_version
    assert provenance.configuration_fingerprint == configuration.fingerprint
    assert provenance.observation_fingerprint is None
    assert provenance.state_model_id is None
    assert provenance.state_model_version is None
    assert provenance.to_dict()["parameters"] == configuration.to_dict()["parameters"]


def test_configuration_fingerprint_preserved() -> None:
    configuration = _configuration()
    strategy = FakeStrategyInstance(configuration)

    provenance = get_strategy_provenance(strategy)

    assert provenance.configuration_fingerprint == configuration.fingerprint


def test_configuration_remains_immutable() -> None:
    strategy = FakeStrategyInstance(_configuration())

    with pytest.raises(FrozenInstanceError):
        strategy.configuration.strategy_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        strategy.configuration.parameters["lookback"] = 30


def test_non_instance_rejected() -> None:
    with pytest.raises(TypeError, match="strategy must satisfy StrategyInstance"):
        get_strategy_provenance(object())  # type: ignore[arg-type]


def test_invalid_configuration_type_rejected() -> None:
    with pytest.raises(
        TypeError,
        match="strategy configuration must be a StrategyConfiguration",
    ):
        get_strategy_provenance(WrongConfigurationStrategy())  # type: ignore[arg-type]


def test_provenance_parameters_are_json_projection() -> None:
    configuration = _configuration()
    strategy = FakeStrategyInstance(configuration)

    provenance = get_strategy_provenance(strategy)
    parameters = provenance.to_dict()["parameters"]

    assert isinstance(parameters, Mapping)
    assert parameters["thresholds"] == [1.5, 2.0]
    assert parameters["tags"] == ["breakout", "trend"]


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
