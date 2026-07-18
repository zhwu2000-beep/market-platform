from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from market_platform.replay import (
    HistoricalReplayResult,
    HistoricalReplayStep,
    HistoricalReplaySummary,
    ReplayStrategyIdentity,
    summarize_historical_replay,
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
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyProvenance,
    StrategyRunResult,
)

_AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
_FINGERPRINT = "sha256:observation"
_STATE_MODEL_ID = "state-model"
_STATE_MODEL_VERSION = "1.0.0"


def _identity(
    strategy_id: str = "trend",
    strategy_version: str = "1.0.0",
    configuration_fingerprint: str | None = "sha256:cfg",
) -> ReplayStrategyIdentity:
    return ReplayStrategyIdentity(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        configuration_fingerprint=configuration_fingerprint,
    )


def _state(as_of: datetime) -> MarketState:
    return MarketState(
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        provenance=StateModelProvenance(
            model_id=_STATE_MODEL_ID,
            model_version=_STATE_MODEL_VERSION,
            parameters={},
            observation_fingerprint=_FINGERPRINT,
        ),
        directional_regime=DirectionalRegime.UP,
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.POSITIVE,
        volatility_regime=VolatilityRegime.NORMAL,
        structure_state=StructureState.AVAILABLE,
        quality=StateQuality.COMPLETE,
    )


def _evaluation(
    identity: ReplayStrategyIdentity,
    status: StrategyEvaluationStatus,
    as_of: datetime,
    *,
    configuration_fingerprint: str | None = None,
) -> StrategyEvaluation:
    fingerprint = (
        identity.configuration_fingerprint
        if configuration_fingerprint is None
        else configuration_fingerprint
    )
    required_inputs = ()
    missing_inputs = ()
    if status is StrategyEvaluationStatus.INSUFFICIENT_DATA:
        required_inputs = ("market_state",)
        missing_inputs = ("market_state",)
    return StrategyEvaluation(
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        provenance=StrategyProvenance(
            strategy_id=identity.strategy_id,
            strategy_version=identity.strategy_version,
            parameters={},
            observation_fingerprint=_FINGERPRINT,
            state_model_id=_STATE_MODEL_ID,
            state_model_version=_STATE_MODEL_VERSION,
            configuration_fingerprint=fingerprint,
        ),
        status=status,
        rationale=f"{status.value} for test",
        required_inputs=required_inputs,
        missing_inputs=missing_inputs,
    )


def _step(
    as_of: datetime,
    identities: tuple[ReplayStrategyIdentity, ...],
    statuses: tuple[StrategyEvaluationStatus, ...],
) -> HistoricalReplayStep:
    evaluations = tuple(
        _evaluation(identity, status, as_of)
        for identity, status in zip(identities, statuses, strict=True)
    )
    return HistoricalReplayStep(
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        observation_fingerprint=_FINGERPRINT,
        state=_state(as_of),
        strategy_result=StrategyRunResult(
            symbol="MSFT",
            interval="1day",
            as_of=as_of,
            observation_fingerprint=_FINGERPRINT,
            state_model_id=_STATE_MODEL_ID,
            state_model_version=_STATE_MODEL_VERSION,
            evaluations=evaluations,
        ),
    )


def _result(
    rows: tuple[tuple[StrategyEvaluationStatus, ...], ...],
    identities: tuple[ReplayStrategyIdentity, ...],
) -> HistoricalReplayResult:
    steps = tuple(
        _step(_AS_OF + timedelta(days=index), identities, statuses)
        for index, statuses in enumerate(rows)
    )
    return HistoricalReplayResult(
        symbol="MSFT",
        interval="1day",
        start_as_of=steps[0].as_of if steps else None,
        end_as_of=steps[-1].as_of if steps else None,
        steps=steps,
        state_model_id=_STATE_MODEL_ID,
        state_model_version=_STATE_MODEL_VERSION,
        strategies=identities,
    )


def test_summary_counts_three_statuses_and_applicable_bounds() -> None:
    identity = _identity()
    result = _result(
        (
            (StrategyEvaluationStatus.INSUFFICIENT_DATA,),
            (StrategyEvaluationStatus.APPLICABLE,),
            (StrategyEvaluationStatus.NOT_APPLICABLE,),
            (StrategyEvaluationStatus.APPLICABLE,),
        ),
        (identity,),
    )

    summary = summarize_historical_replay(result)
    strategy = summary.strategies[0]

    assert strategy.step_count == 4
    assert strategy.applicable_count == 2
    assert strategy.not_applicable_count == 1
    assert strategy.insufficient_data_count == 1
    assert strategy.first_applicable_as_of == _AS_OF + timedelta(days=1)
    assert strategy.last_applicable_as_of == _AS_OF + timedelta(days=3)


def test_summary_has_no_applicable_bounds_when_none_apply() -> None:
    result = _result(
        (
            (StrategyEvaluationStatus.INSUFFICIENT_DATA,),
            (StrategyEvaluationStatus.NOT_APPLICABLE,),
            (StrategyEvaluationStatus.NOT_APPLICABLE,),
        ),
        (_identity(),),
    )

    strategy = summarize_historical_replay(result).strategies[0]

    assert strategy.applicable_count == 0
    assert strategy.first_applicable_as_of is None
    assert strategy.last_applicable_as_of is None


def test_summary_counts_status_transitions() -> None:
    result = _result(
        (
            (StrategyEvaluationStatus.INSUFFICIENT_DATA,),
            (StrategyEvaluationStatus.INSUFFICIENT_DATA,),
            (StrategyEvaluationStatus.NOT_APPLICABLE,),
            (StrategyEvaluationStatus.NOT_APPLICABLE,),
            (StrategyEvaluationStatus.APPLICABLE,),
            (StrategyEvaluationStatus.NOT_APPLICABLE,),
        ),
        (_identity(),),
    )

    strategy = summarize_historical_replay(result).strategies[0]

    assert strategy.status_transition_count == 3


def test_summary_preserves_strategy_order() -> None:
    first = _identity("first", "1.0.0", "sha256:first")
    second = _identity("second", "2.0.0", "sha256:second")
    result = _result(
        (
            (
                StrategyEvaluationStatus.APPLICABLE,
                StrategyEvaluationStatus.NOT_APPLICABLE,
            ),
        ),
        (first, second),
    )

    summary = summarize_historical_replay(result)

    assert tuple(item.strategy for item in summary.strategies) == (first, second)


def test_summary_handles_multiple_strategies_independently() -> None:
    first = _identity("first", "1.0.0", "sha256:first")
    second = _identity("second", "2.0.0", "sha256:second")
    result = _result(
        (
            (
                StrategyEvaluationStatus.APPLICABLE,
                StrategyEvaluationStatus.NOT_APPLICABLE,
            ),
            (
                StrategyEvaluationStatus.NOT_APPLICABLE,
                StrategyEvaluationStatus.APPLICABLE,
            ),
            (
                StrategyEvaluationStatus.INSUFFICIENT_DATA,
                StrategyEvaluationStatus.APPLICABLE,
            ),
        ),
        (first, second),
    )

    first_summary, second_summary = summarize_historical_replay(result).strategies

    assert first_summary.applicable_count == 1
    assert first_summary.not_applicable_count == 1
    assert first_summary.insufficient_data_count == 1
    assert second_summary.applicable_count == 2
    assert second_summary.not_applicable_count == 1
    assert second_summary.insufficient_data_count == 0


def test_summary_handles_empty_strategy_identities() -> None:
    result = _result(((),), ())

    summary = summarize_historical_replay(result)

    assert summary.step_count == 1
    assert summary.strategies == ()


def test_summary_handles_empty_replay_when_model_allows_empty_steps() -> None:
    result = _result((), ())

    summary = summarize_historical_replay(result)

    assert summary.start_as_of is None
    assert summary.end_as_of is None
    assert summary.step_count == 0
    assert summary.strategies == ()


def test_summary_rejects_evaluation_identity_mismatch() -> None:
    identity = _identity(configuration_fingerprint="sha256:expected")
    as_of = _AS_OF
    evaluation = _evaluation(
        identity,
        StrategyEvaluationStatus.APPLICABLE,
        as_of,
        configuration_fingerprint="sha256:other",
    )
    step = HistoricalReplayStep(
        symbol="MSFT",
        interval="1day",
        as_of=as_of,
        observation_fingerprint=_FINGERPRINT,
        state=_state(as_of),
        strategy_result=StrategyRunResult(
            symbol="MSFT",
            interval="1day",
            as_of=as_of,
            observation_fingerprint=_FINGERPRINT,
            state_model_id=_STATE_MODEL_ID,
            state_model_version=_STATE_MODEL_VERSION,
            evaluations=(evaluation,),
        ),
    )
    result = HistoricalReplayResult(
        symbol="MSFT",
        interval="1day",
        start_as_of=as_of,
        end_as_of=as_of,
        steps=(step,),
        state_model_id=_STATE_MODEL_ID,
        state_model_version=_STATE_MODEL_VERSION,
        strategies=(identity,),
    )

    with pytest.raises(ValueError, match="configuration_fingerprint"):
        summarize_historical_replay(result)


def test_summary_to_dict_is_json_compatible() -> None:
    result = _result(((StrategyEvaluationStatus.APPLICABLE,),), (_identity(),))

    payload = summarize_historical_replay(result).to_dict()

    json.dumps(payload)
    assert payload["strategies"][0]["strategy"]["strategy_id"] == "trend"


def test_summary_does_not_modify_input_and_is_frozen() -> None:
    result = _result(((StrategyEvaluationStatus.APPLICABLE,),), (_identity(),))
    before = result.to_dict()

    summary = summarize_historical_replay(result)

    assert result.to_dict() == before
    with pytest.raises(FrozenInstanceError):
        summary.step_count = 99  # type: ignore[misc]
    assert isinstance(summary, HistoricalReplaySummary)


def test_replay_summary_has_no_forbidden_dependencies() -> None:
    paths = [Path("src/market_platform/replay/summary.py")]
    forbidden = {
        "pandas",
        "market_platform.research",
        "market_platform.cli",
        "market_platform.provider",
        "market_platform.portfolio",
        "market_platform.risk",
        "market_platform.execution",
    }
    imported: set[str] = set()
    for path in paths:
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
