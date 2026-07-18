from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_platform.observation.models import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
    PriceFacts,
)
from market_platform.state.models import (
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
    BaselineVolatilityRegimeStrategy,
    Strategy,
    StrategyEvaluationStatus,
    StrategyInstance,
    StrategyRunner,
)
from market_platform.strategy.configuration import StrategyConfiguration
from market_platform.strategy.models import StrategyEvidenceSource

_AS_OF = datetime(2026, 7, 16, tzinfo=UTC)
_OBSERVATION_FINGERPRINT = "sha256:observation"
_STATE_MODEL_ID = "baseline_market_state_model"
_STATE_MODEL_VERSION = "1.0.0"


def test_identity_and_protocols() -> None:
    strategy = BaselineVolatilityRegimeStrategy()

    assert strategy.strategy_id == "baseline_volatility_regime"
    assert strategy.strategy_version == "1.0.0"
    assert isinstance(strategy, Strategy)
    assert isinstance(strategy, StrategyInstance)


def test_configuration_records_rules_and_is_immutable() -> None:
    strategy = BaselineVolatilityRegimeStrategy()
    configuration = strategy.configuration

    assert configuration.strategy_id == strategy.strategy_id
    assert configuration.strategy_version == strategy.strategy_version
    assert configuration.fingerprint
    assert (
        BaselineVolatilityRegimeStrategy().configuration.fingerprint
        == configuration.fingerprint
    )
    assert configuration.parameters["compatible_volatility_regimes"] == (
        VolatilityRegime.LOW.value,
        VolatilityRegime.NORMAL.value,
    )
    assert configuration.parameters["unavailable_volatility_regimes"] == (
        VolatilityRegime.UNAVAILABLE.value,
    )
    assert configuration.parameters["indeterminate_policy"] == "not_applicable"

    with pytest.raises(FrozenInstanceError):
        configuration.strategy_id = "changed"  # type: ignore[misc]


def test_configuration_and_execution_rules_share_one_contract() -> None:
    strategy = BaselineVolatilityRegimeStrategy()
    observation = _observation()

    compatible = strategy.configuration.parameters[
        "compatible_volatility_regimes"
    ]
    assert isinstance(compatible, tuple)
    for value in compatible:
        evaluation = strategy.evaluate(
            _state(volatility_regime=VolatilityRegime(value)),
            observation,
        )
        assert evaluation.status is StrategyEvaluationStatus.APPLICABLE

    unavailable = strategy.configuration.parameters[
        "unavailable_volatility_regimes"
    ]
    assert isinstance(unavailable, tuple)
    for value in unavailable:
        evaluation = strategy.evaluate(
            _state(volatility_regime=VolatilityRegime(value)),
            observation,
        )
        assert evaluation.status is StrategyEvaluationStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize(
    "regime",
    [VolatilityRegime.LOW, VolatilityRegime.NORMAL],
)
def test_applicable_for_compatible_volatility_regimes(
    regime: VolatilityRegime,
) -> None:
    evaluation = BaselineVolatilityRegimeStrategy().evaluate(
        _state(volatility_regime=regime),
        _observation(),
    )

    assert evaluation.status is StrategyEvaluationStatus.APPLICABLE
    assert evaluation.missing_inputs == ()
    assert evaluation.rationale == (
        "volatility regime is compatible with the configured "
        "baseline conditions"
    )


def test_not_applicable_for_high_volatility_regime() -> None:
    evaluation = BaselineVolatilityRegimeStrategy().evaluate(
        _state(volatility_regime=VolatilityRegime.HIGH),
        _observation(),
    )

    assert evaluation.status is StrategyEvaluationStatus.NOT_APPLICABLE
    assert evaluation.missing_inputs == ()
    assert evaluation.rationale == (
        "volatility regime is not compatible with the configured "
        "baseline conditions"
    )


def test_indeterminate_policy_maps_to_not_applicable() -> None:
    strategy = BaselineVolatilityRegimeStrategy()
    evaluation = strategy.evaluate(
        _state(volatility_regime=VolatilityRegime.INDETERMINATE),
        _observation(),
    )

    assert strategy.configuration.parameters["indeterminate_policy"] == (
        "not_applicable"
    )
    assert evaluation.status is StrategyEvaluationStatus.NOT_APPLICABLE
    assert evaluation.missing_inputs == ()
    assert evaluation.rationale == (
        "indeterminate volatility is not applicable under the configured policy"
    )


def test_unavailable_volatility_regime_is_insufficient_data() -> None:
    evaluation = BaselineVolatilityRegimeStrategy().evaluate(
        _state(volatility_regime=VolatilityRegime.UNAVAILABLE),
        _observation(),
    )

    assert evaluation.status is StrategyEvaluationStatus.INSUFFICIENT_DATA
    assert evaluation.missing_inputs == ("volatility_regime",)
    assert evaluation.rationale == "required volatility regime is unavailable"


def test_evidence_records_market_state_volatility_regime() -> None:
    evaluation = BaselineVolatilityRegimeStrategy().evaluate(
        _state(volatility_regime=VolatilityRegime.NORMAL),
        _observation(),
    )

    assert len(evaluation.evidence) == 1
    evidence = evaluation.evidence[0]
    assert evidence.source is StrategyEvidenceSource.MARKET_STATE
    assert evidence.field == "volatility_regime"
    assert evidence.observed_value == VolatilityRegime.NORMAL.value
    assert evidence.observed_at == _AS_OF


def test_provenance_binds_strategy_configuration_observation_and_state_model() -> None:
    strategy = BaselineVolatilityRegimeStrategy()
    evaluation = strategy.evaluate(
        _state(volatility_regime=VolatilityRegime.NORMAL),
        _observation(),
    )

    assert evaluation.provenance.strategy_id == strategy.strategy_id
    assert evaluation.provenance.strategy_version == strategy.strategy_version
    assert (
        evaluation.provenance.configuration_fingerprint
        == strategy.configuration.fingerprint
    )
    assert (
        evaluation.provenance.observation_fingerprint
        == _OBSERVATION_FINGERPRINT
    )
    assert evaluation.provenance.state_model_id == _STATE_MODEL_ID
    assert evaluation.provenance.state_model_version == _STATE_MODEL_VERSION


def test_identity_mismatch_between_state_and_observation_is_rejected() -> None:
    strategy = BaselineVolatilityRegimeStrategy()

    with pytest.raises(ValueError):
        strategy.evaluate(
            _state(symbol="MSFT"),
            _observation(symbol="AAPL"),
        )


def test_strategy_runner_runs_baseline_volatility_strategy() -> None:
    strategy = BaselineVolatilityRegimeStrategy()
    result = StrategyRunner().evaluate(
        (strategy,),
        observation=_observation(),
        state=_state(volatility_regime=VolatilityRegime.LOW),
    )

    assert result.strategy_count == 1
    assert result.evaluations[0].provenance.strategy_id == strategy.strategy_id
    assert result.evaluations[0].status is StrategyEvaluationStatus.APPLICABLE


def test_strategy_runner_preserves_order_with_trend_strategy() -> None:
    result = StrategyRunner().evaluate(
        (BaselineTrendRegimeStrategy(), BaselineVolatilityRegimeStrategy()),
        observation=_observation(),
        state=_state(volatility_regime=VolatilityRegime.NORMAL),
    )

    assert tuple(
        evaluation.provenance.strategy_id for evaluation in result.evaluations
    ) == (
        "baseline_trend_regime",
        "baseline_volatility_regime",
    )


def test_inputs_are_not_modified() -> None:
    strategy = BaselineVolatilityRegimeStrategy()
    state = _state(volatility_regime=VolatilityRegime.NORMAL)
    observation = _observation()
    state_before = state.to_dict()
    observation_before = observation.to_dict()
    configuration_before = strategy.configuration.to_dict()

    strategy.evaluate(state, observation)

    assert state.to_dict() == state_before
    assert observation.to_dict() == observation_before
    assert strategy.configuration.to_dict() == configuration_before


def test_custom_configuration_identity_cannot_diverge() -> None:
    with pytest.raises(ValueError):
        BaselineVolatilityRegimeStrategy(
            configuration=StrategyConfiguration(
                strategy_id="other",
                strategy_version="1.0.0",
                parameters={
                    "compatible_volatility_regimes": (
                        VolatilityRegime.LOW.value,
                        VolatilityRegime.NORMAL.value,
                    ),
                    "unavailable_volatility_regimes": (
                        VolatilityRegime.UNAVAILABLE.value,
                    ),
                    "indeterminate_policy": "not_applicable",
                },
            )
        )


def test_custom_configuration_rules_cannot_diverge() -> None:
    with pytest.raises(ValueError):
        BaselineVolatilityRegimeStrategy(
            configuration=StrategyConfiguration(
                strategy_id="baseline_volatility_regime",
                strategy_version="1.0.0",
                parameters={
                    "compatible_volatility_regimes": (
                        VolatilityRegime.HIGH.value,
                    ),
                    "unavailable_volatility_regimes": (
                        VolatilityRegime.UNAVAILABLE.value,
                    ),
                    "indeterminate_policy": "not_applicable",
                },
            )
        )


def test_baseline_volatility_dependency_boundary() -> None:
    source_path = (
        Path(__file__).parents[2]
        / "src"
        / "market_platform"
        / "strategy"
        / "baseline_volatility.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_modules = {
        "market_platform.research",
        "market_platform.cli",
        "market_platform.provider",
        "market_platform.replay",
        "market_platform.portfolio",
        "market_platform.risk",
        "market_platform.execution",
    }
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imported_modules
        for forbidden in forbidden_modules
    )


def test_output_has_no_trading_or_performance_meaning() -> None:
    forbidden_terms = {
        "buy",
        "sell",
        "hold",
        "long",
        "short",
        "entry",
        "exit",
        "position",
        "target",
        "probability",
        "return",
        "p&l",
        "profit",
    }
    payloads = []
    for regime in VolatilityRegime:
        evaluation = BaselineVolatilityRegimeStrategy().evaluate(
            _state(volatility_regime=regime),
            _observation(),
        )
        payloads.append(json.dumps(evaluation.to_dict()).lower())

    combined = "\n".join(payloads)
    assert not any(term in combined for term in forbidden_terms)


def _observation(
    *,
    symbol: str = "MSFT",
    interval: str = "1day",
    as_of: datetime = _AS_OF,
) -> MarketObservation:
    return MarketObservation(
        identity=ObservationIdentity(
            symbol=symbol,
            interval=interval,
            as_of=as_of,
            window_start=as_of,
            window_end=as_of,
        ),
        provenance=ObservationProvenance(
            provider="test-provider",
            methodology="test-observation",
            methodology_version="1.0.0",
            parameters={},
            input_fingerprint=_OBSERVATION_FINGERPRINT,
        ),
        price_facts=PriceFacts(
            latest_price=100.0,
            observed_at=as_of,
        ),
    )


def _state(
    *,
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL,
    symbol: str = "MSFT",
    interval: str = "1day",
    as_of: datetime = _AS_OF,
) -> MarketState:
    return MarketState(
        symbol=symbol,
        interval=interval,
        as_of=as_of,
        provenance=StateModelProvenance(
            model_id=_STATE_MODEL_ID,
            model_version=_STATE_MODEL_VERSION,
            parameters={},
            observation_fingerprint=_OBSERVATION_FINGERPRINT,
        ),
        directional_regime=DirectionalRegime.UP,
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.POSITIVE,
        volatility_regime=volatility_regime,
        structure_state=StructureState.AVAILABLE,
        quality=StateQuality.COMPLETE,
    )
