"""Strategy instance contract bound to immutable configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from market_platform.strategy.configuration import StrategyConfiguration
from market_platform.strategy.models import StrategyProvenance


@runtime_checkable
class StrategyInstance(Protocol):
    """Strategy object that derives identity from its configuration."""

    @property
    def configuration(self) -> StrategyConfiguration:
        """Return the immutable configuration for this strategy instance."""

    @property
    def strategy_id(self) -> str:
        """Return configuration.strategy_id."""

    @property
    def strategy_version(self) -> str:
        """Return configuration.strategy_version."""


def get_strategy_provenance(strategy: StrategyInstance) -> StrategyProvenance:
    """Build identity/configuration provenance from a strategy instance."""

    if not isinstance(strategy, StrategyInstance):
        raise TypeError("strategy must satisfy StrategyInstance")

    configuration = strategy.configuration
    if not isinstance(configuration, StrategyConfiguration):
        raise TypeError("strategy configuration must be a StrategyConfiguration")

    if strategy.strategy_id != configuration.strategy_id:
        raise ValueError("strategy_id must come from configuration")
    if strategy.strategy_version != configuration.strategy_version:
        raise ValueError("strategy_version must come from configuration")

    parameters = configuration.to_dict()["parameters"]
    if not isinstance(parameters, Mapping):
        raise TypeError("configuration parameters must serialize to a mapping")

    return StrategyProvenance(
        strategy_id=configuration.strategy_id,
        strategy_version=configuration.strategy_version,
        parameters=parameters,
        configuration_fingerprint=configuration.fingerprint,
    )


__all__ = ["StrategyInstance", "get_strategy_provenance"]
