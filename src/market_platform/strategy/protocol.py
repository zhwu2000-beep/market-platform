"""Replaceable strategy evaluation boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState
from market_platform.strategy.models import StrategyEvaluation


@runtime_checkable
class Strategy(Protocol):
    """Evaluate immutable point-in-time inputs without execution side effects."""

    @property
    def strategy_id(self) -> str:
        """Return the stable strategy identity."""
        ...

    @property
    def strategy_version(self) -> str:
        """Return the version of the strategy rules and parameters."""
        ...

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        """Return one point-in-time evaluation for matching immutable inputs."""
        ...
