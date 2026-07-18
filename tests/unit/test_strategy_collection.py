"""Tests for immutable strategy collections."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from market_platform.observation import MarketObservation
from market_platform.state import MarketState
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    StrategyCollection,
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyProvenance,
    create_strategy_collection,
)


@dataclass(slots=True)
class SimpleStrategy:
    strategy_id: str
    strategy_version: str = "1.0.0"
    touched: bool = False

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        self.touched = True
        return StrategyEvaluation(
            symbol=state.symbol,
            interval=state.interval,
            as_of=state.as_of,
            provenance=StrategyProvenance(
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                parameters={},
                observation_fingerprint=observation.provenance.input_fingerprint,
                state_model_id=state.provenance.model_id,
                state_model_version=state.provenance.model_version,
            ),
            status=StrategyEvaluationStatus.NOT_APPLICABLE,
            rationale="simple protocol-compatible strategy",
        )


def test_empty_collection_is_allowed() -> None:
    collection = create_strategy_collection([])

    assert isinstance(collection, StrategyCollection)
    assert collection.strategies == ()
    assert collection.strategy_count == 0
    assert collection.strategy_ids == ()
    assert collection.to_dict() == {"strategies": []}


def test_single_strategy_collection_succeeds() -> None:
    strategy = BaselineTrendRegimeStrategy()

    collection = create_strategy_collection([strategy])

    assert collection.strategies == (strategy,)


def test_multiple_strategy_collection_preserves_order() -> None:
    strategies = [
        SimpleStrategy("trend"),
        SimpleStrategy("breakout"),
        SimpleStrategy("mean_reversion"),
    ]

    collection = create_strategy_collection(strategies)

    assert collection.strategy_ids == (
        "trend",
        "breakout",
        "mean_reversion",
    )
    assert collection.strategies == tuple(strategies)


def test_list_input_is_defensively_copied() -> None:
    strategies = [SimpleStrategy("trend")]
    collection = create_strategy_collection(strategies)

    strategies.append(SimpleStrategy("late"))

    assert collection.strategy_ids == ("trend",)


def test_invalid_object_rejected() -> None:
    with pytest.raises(TypeError, match="strategies elements must satisfy Strategy"):
        create_strategy_collection([object()])  # type: ignore[list-item]


def test_strategy_count() -> None:
    collection = create_strategy_collection(
        [SimpleStrategy("trend"), SimpleStrategy("breakout")]
    )

    assert collection.strategy_count == 2


def test_strategy_ids() -> None:
    collection = create_strategy_collection(
        [SimpleStrategy("trend"), SimpleStrategy("breakout")]
    )

    assert collection.strategy_ids == ("trend", "breakout")


def test_to_dict_is_json_compatible_identity_projection() -> None:
    collection = create_strategy_collection(
        [SimpleStrategy("trend", "1.0.0"), SimpleStrategy("breakout", "2.0.0")]
    )

    assert collection.to_dict() == {
        "strategies": [
            {"strategy_id": "trend", "strategy_version": "1.0.0"},
            {"strategy_id": "breakout", "strategy_version": "2.0.0"},
        ],
    }


def test_collection_is_frozen() -> None:
    collection = create_strategy_collection([SimpleStrategy("trend")])

    with pytest.raises(FrozenInstanceError):
        collection.strategies = ()  # type: ignore[misc]


def test_input_strategy_object_is_not_modified() -> None:
    strategy = SimpleStrategy("trend")

    create_strategy_collection([strategy])

    assert strategy.touched is False
    assert strategy.strategy_id == "trend"
    assert strategy.strategy_version == "1.0.0"


def test_strategy_collection_direct_constructor_accepts_list_copy() -> None:
    strategies = [SimpleStrategy("trend")]
    collection = StrategyCollection(strategies=strategies)  # type: ignore[arg-type]

    strategies.append(SimpleStrategy("late"))

    assert collection.strategies == (strategies[0],)


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
