"""Strategy evaluation domain and replaceable protocol."""

from market_platform.strategy.baseline_trend import BaselineTrendRegimeStrategy
from market_platform.strategy.baseline_volatility import (
    BaselineVolatilityRegimeStrategy,
)
from market_platform.strategy.collection import (
    StrategyCollection,
    create_strategy_collection,
)
from market_platform.strategy.configuration import StrategyConfiguration
from market_platform.strategy.evaluation import build_strategy_evaluation
from market_platform.strategy.instance import (
    StrategyInstance,
    get_strategy_provenance,
)
from market_platform.strategy.models import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
    StrategyEvidenceValue,
    StrategyProvenance,
    StrategyRunResult,
)
from market_platform.strategy.protocol import Strategy
from market_platform.strategy.runner import StrategyRunner, StrategyRunnerError
from market_platform.strategy.validation import (
    validate_strategy_evaluation,
    validate_strategy_inputs,
    validate_strategy_run_result,
)

__all__ = [
    "BaselineVolatilityRegimeStrategy",
    "BaselineTrendRegimeStrategy",
    "Strategy",
    "StrategyCollection",
    "StrategyConfiguration",
    "StrategyEvaluation",
    "StrategyEvaluationStatus",
    "StrategyEvidence",
    "StrategyEvidenceSource",
    "StrategyEvidenceValue",
    "StrategyInstance",
    "StrategyProvenance",
    "StrategyRunner",
    "StrategyRunnerError",
    "StrategyRunResult",
    "build_strategy_evaluation",
    "create_strategy_collection",
    "get_strategy_provenance",
    "validate_strategy_evaluation",
    "validate_strategy_inputs",
    "validate_strategy_run_result",
]
