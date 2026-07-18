"""Immutable ordered collection of strategy instances."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from market_platform.strategy.protocol import Strategy


@dataclass(frozen=True, slots=True)
class StrategyCollection:
    """A deterministic ordered group of strategy implementations."""

    strategies: tuple[Strategy, ...]

    def __post_init__(self) -> None:
        strategies = _normalize_strategies(self.strategies)
        object.__setattr__(self, "strategies", strategies)

    @property
    def strategy_count(self) -> int:
        """Return the number of strategies in the collection."""

        return len(self.strategies)

    @property
    def strategy_ids(self) -> tuple[str, ...]:
        """Return strategy ids in collection order."""

        return tuple(strategy.strategy_id for strategy in self.strategies)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible collection identity representation."""

        return {
            "strategies": [
                {
                    "strategy_id": strategy.strategy_id,
                    "strategy_version": strategy.strategy_version,
                }
                for strategy in self.strategies
            ],
        }


def create_strategy_collection(
    strategies: Sequence[Strategy],
) -> StrategyCollection:
    """Create an immutable collection from a strategy sequence."""

    return StrategyCollection(strategies=tuple(strategies))


def _normalize_strategies(value: object) -> tuple[Strategy, ...]:
    if isinstance(value, tuple):
        strategies = value
    elif isinstance(value, list):
        strategies = tuple(value)
    else:
        raise TypeError("strategies must be a tuple or list")

    for strategy in strategies:
        if not isinstance(strategy, Strategy):
            raise TypeError("strategies elements must satisfy Strategy")
    return strategies


__all__ = ["StrategyCollection", "create_strategy_collection"]
