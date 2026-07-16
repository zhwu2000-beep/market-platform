"""Replaceable market state model boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from market_platform.observation.models import MarketObservation
from market_platform.state.models import MarketState


@runtime_checkable
class MarketStateModel(Protocol):
    """Evaluate an observation without prescribing a market action."""

    @property
    def model_id(self) -> str:
        """Return the stable model identity."""
        ...

    @property
    def model_version(self) -> str:
        """Return the version of the model rules and parameters."""
        ...

    def evaluate(self, observation: MarketObservation) -> MarketState:
        """Return the point-in-time state for an immutable observation."""
        ...
