"""Tests for the baseline trend-regime strategy."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

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
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    StrategyEvaluationStatus,
    StrategyEvidenceSource,
    StrategyRunner,
    StrategyRunResult,
)

_AS_OF = datetime(2026, 7, 17, tzinfo=UTC)
_FINGERPRINT = "sha256:observation"
_BANNED_TERMS = (
    "BUY",
    "SELL",
    "HOLD",
    "LONG",
    "SHORT",
    "ENTRY",
    "EXIT",
    "TARGET",
    "PROBABILITY",
    "POSITION",
)


def _observation() -> MarketObservation:
    return MarketObservation(
        identity=ObservationIdentity(
            symbol="MSFT",
            interval="1day",
            as_of=_AS_OF,
            window_start=datetime(2026, 4, 1, tzinfo=UTC),
            window_end=_AS_OF,
        ),
        provenance=ObservationProvenance(
            provider="test-provider",
            methodology="test-observation",
            methodology_version="v1",
            parameters={},
            input_fingerprint=_FINGERPRINT,
        ),
    )


def _state(
    *,
    trend_regime: TrendRegime = TrendRegime.UP,
    momentum_regime: MomentumRegime = MomentumRegime.POSITIVE,
) -> MarketState:
    return MarketState(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        provenance=StateModelProvenance(
            model_id="baseline-market-state",
            model_version="v1",
            parameters={},
            observation_fingerprint=_FINGERPRINT,
        ),
        directional_regime=DirectionalRegime.UP,
        trend_regime=trend_regime,
        momentum_regime=momentum_regime,
        volatility_regime=VolatilityRegime.NORMAL,
        structure_state=StructureState.AVAILABLE,
        quality=StateQuality.COMPLETE,
    )


def _evaluate(
    *,
    trend_regime: TrendRegime = TrendRegime.UP,
    momentum_regime: MomentumRegime = MomentumRegime.POSITIVE,
):
    return BaselineTrendRegimeStrategy().evaluate(
        _state(
            trend_regime=trend_regime,
            momentum_regime=momentum_regime,
        ),
        _observation(),
    )


def test_strategy_identity() -> None:
    strategy = BaselineTrendRegimeStrategy()

    assert strategy.strategy_id == "baseline_trend_regime"
    assert strategy.strategy_version == "1.0.0"
    assert strategy.configuration.to_dict()["parameters"] == {
        "required_momentum_regimes": ["positive", "strong_positive"],
        "required_trend_regimes": ["up", "strong_up"],
    }


def test_configuration_fingerprint_exists() -> None:
    strategy = BaselineTrendRegimeStrategy()

    assert strategy.configuration.fingerprint.startswith("sha256:")
    assert len(strategy.configuration.fingerprint) == 71


def test_applicable_for_strong_up_trend_and_positive_momentum() -> None:
    evaluation = _evaluate(
        trend_regime=TrendRegime.STRONG_UP,
        momentum_regime=MomentumRegime.POSITIVE,
    )

    assert evaluation.status is StrategyEvaluationStatus.APPLICABLE
    assert evaluation.rationale == "trend and momentum regimes are aligned"


def test_applicable_for_up_trend_and_strong_positive_momentum() -> None:
    evaluation = _evaluate(
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.STRONG_POSITIVE,
    )

    assert evaluation.status is StrategyEvaluationStatus.APPLICABLE
    assert evaluation.rationale == "trend and momentum regimes are aligned"


def test_not_applicable_for_down_trend_and_negative_momentum() -> None:
    evaluation = _evaluate(
        trend_regime=TrendRegime.DOWN,
        momentum_regime=MomentumRegime.NEGATIVE,
    )

    assert evaluation.status is StrategyEvaluationStatus.NOT_APPLICABLE
    assert evaluation.missing_inputs == ()


def test_insufficient_data_for_unavailable_trend() -> None:
    evaluation = _evaluate(
        trend_regime=TrendRegime.UNAVAILABLE,
        momentum_regime=MomentumRegime.POSITIVE,
    )

    assert evaluation.status is StrategyEvaluationStatus.INSUFFICIENT_DATA
    assert evaluation.missing_inputs == ("trend_regime",)


def test_insufficient_data_for_unavailable_momentum() -> None:
    evaluation = _evaluate(
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.UNAVAILABLE,
    )

    assert evaluation.status is StrategyEvaluationStatus.INSUFFICIENT_DATA
    assert evaluation.missing_inputs == ("momentum_regime",)


def test_evidence_records_used_market_state_fields() -> None:
    evaluation = _evaluate(
        trend_regime=TrendRegime.STRONG_UP,
        momentum_regime=MomentumRegime.POSITIVE,
    )

    evidence_by_field = {item.field: item for item in evaluation.evidence}
    assert tuple(evidence_by_field) == ("trend_regime", "momentum_regime")
    assert evidence_by_field["trend_regime"].source is (
        StrategyEvidenceSource.MARKET_STATE
    )
    assert evidence_by_field["trend_regime"].observed_value == "strong_up"
    assert evidence_by_field["trend_regime"].observed_at == _AS_OF
    assert evidence_by_field["momentum_regime"].source is (
        StrategyEvidenceSource.MARKET_STATE
    )
    assert evidence_by_field["momentum_regime"].observed_value == "positive"
    assert evidence_by_field["momentum_regime"].observed_at == _AS_OF


def test_provenance_is_bound_to_strategy_configuration_and_inputs() -> None:
    strategy = BaselineTrendRegimeStrategy()
    evaluation = strategy.evaluate(_state(), _observation())

    provenance = evaluation.provenance
    assert provenance.strategy_id == strategy.strategy_id
    assert provenance.strategy_version == strategy.strategy_version
    assert provenance.configuration_fingerprint == strategy.configuration.fingerprint
    assert provenance.observation_fingerprint == _FINGERPRINT
    assert provenance.state_model_id == "baseline-market-state"
    assert provenance.state_model_version == "v1"


def test_strategy_runner_collects_baseline_trend_result() -> None:
    result = StrategyRunner().evaluate(
        [BaselineTrendRegimeStrategy()],
        observation=_observation(),
        state=_state(),
    )

    assert isinstance(result, StrategyRunResult)
    assert result.strategy_count == 1
    assert result.evaluations[0].provenance.strategy_id == "baseline_trend_regime"


def test_inputs_are_not_modified() -> None:
    strategy = BaselineTrendRegimeStrategy()
    observation = _observation()
    state = _state()
    observation_before = observation.to_dict()
    state_before = state.to_dict()
    configuration_before = strategy.configuration.to_dict()

    strategy.evaluate(state, observation)

    assert observation.to_dict() == observation_before
    assert state.to_dict() == state_before
    assert strategy.configuration.to_dict() == configuration_before


def test_evaluation_contains_no_trading_semantics() -> None:
    evaluation = _evaluate()
    payload = str(evaluation.to_dict()).upper()

    assert all(term not in payload for term in _BANNED_TERMS)


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
