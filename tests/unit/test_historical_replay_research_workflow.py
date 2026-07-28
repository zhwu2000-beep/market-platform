from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import NoReturn

import pandas as pd
import pytest

import market_platform.research.historical_replay_workflow_service as workflow_service
from market_platform._fingerprint import canonical_fingerprint
from market_platform.data import HistoricalPriceSeries
from market_platform.observation import MarketObservation
from market_platform.replay import (
    HistoricalReplayArtifact,
    HistoricalReplayExperimentSpecification,
    HistoricalReplayService,
    HistoricalReplaySpecification,
    SoftwareRevision,
    create_historical_replay_experiment,
    default_replay_structure_derivation_identity,
)
from market_platform.research import (
    DefaultResearchWorkflow,
    HistoricalReplayResearchMemberSpecification,
    HistoricalReplayResearchStateModelInstance,
    HistoricalReplayResearchWorkflowCandidateResult,
    HistoricalReplayResearchWorkflowFailureCode,
    HistoricalReplayResearchWorkflowResult,
    HistoricalReplayResearchWorkflowService,
    HistoricalReplayResearchWorkflowSkipReason,
    HistoricalReplayResearchWorkflowSpecification,
    HistoricalReplayResearchWorkflowStatus,
    HistoricalReplayResearchWorkflowStepKind,
    HistoricalReplayResearchWorkflowStepResult,
    HistoricalReplayResearchWorkflowStepStatus,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
    ResearchWorkflow,
)
from market_platform.state import BaselineMarketStateModel, MarketState
from market_platform.strategy import (
    BaselineTrendRegimeStrategy,
    BaselineVolatilityRegimeStrategy,
    StrategyConfiguration,
    StrategyEvaluation,
    StrategyRunnerError,
    create_strategy_collection,
)

_START = datetime(2026, 1, 1, tzinfo=UTC)
_REPLAY_REVISION = SoftwareRevision("replay-revision", False)
_COMPARISON_REVISION = SoftwareRevision("comparison-revision", False)
_WORKFLOW_REVISION = SoftwareRevision("workflow-revision", False)


class _BroadOnlyStrategy:
    def __init__(self) -> None:
        self._delegate = BaselineTrendRegimeStrategy()

    @property
    def strategy_id(self) -> str:
        return self._delegate.strategy_id

    @property
    def strategy_version(self) -> str:
        return self._delegate.strategy_version

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        return self._delegate.evaluate(state, observation)


class _MutableStrategyInstance:
    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    @property
    def configuration(self) -> StrategyConfiguration:
        parameters = BaselineTrendRegimeStrategy().configuration.to_dict()[
            "parameters"
        ]
        assert isinstance(parameters, dict)
        return StrategyConfiguration(
            strategy_id="baseline_trend_regime",
            strategy_version="1.0.0",
            parameters={**parameters, "mutable_threshold": self.threshold},
        )

    @property
    def strategy_id(self) -> str:
        return self.configuration.strategy_id

    @property
    def strategy_version(self) -> str:
        return self.configuration.strategy_version

    def evaluate(
        self,
        state: MarketState,
        observation: MarketObservation,
    ) -> StrategyEvaluation:
        if self.threshold < 0:
            raise AssertionError("threshold changes evaluation behavior")
        return BaselineTrendRegimeStrategy(self.configuration).evaluate(
            state,
            observation,
        )


class _BroadOnlyStateModel:
    _delegate = BaselineMarketStateModel()

    @property
    def model_id(self) -> str:
        return self._delegate.model_id

    @property
    def model_version(self) -> str:
        return self._delegate.model_version

    def evaluate(self, observation: MarketObservation) -> MarketState:
        return self._delegate.evaluate(observation)


class _MutableStateModel(_BroadOnlyStateModel):
    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    @property
    def configuration_fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "schema_version": "test_mutable_state_model_configuration/v1",
                "mutable_threshold": self.threshold,
            }
        )

    def evaluate(self, observation: MarketObservation) -> MarketState:
        if self.threshold < 0:
            raise AssertionError("threshold changes evaluation behavior")
        return super().evaluate(observation)


class _InvalidIdentityStateModel(_BroadOnlyStateModel):
    @property
    def configuration_fingerprint(self) -> str:
        return "not-a-fingerprint"


def _prices(
    count: int = 60,
    *,
    provider: str = "workflow-provider",
    symbol: str = "MSFT",
) -> pd.DataFrame:
    closes = [100.0 + index * 0.25 for index in range(count)]
    return pd.DataFrame(
        {
            "symbol": [symbol] * count,
            "timestamp": [
                _START + timedelta(days=index) for index in range(count)
            ],
            "open": closes,
            "high": [close + 1.0 for close in closes],
            "low": [close - 1.0 for close in closes],
            "close": closes,
            "volume": [1_000_000.0] * count,
            "provider": [provider] * count,
        }
    )


def _replay_specification(
    *,
    symbol: str = "MSFT",
    interval: str = "1day",
    evaluation_start: datetime = _START + timedelta(days=50),
    evaluation_end: datetime = _START + timedelta(days=52),
) -> HistoricalReplaySpecification:
    return HistoricalReplaySpecification(
        symbol=symbol,
        interval=interval,
        context_start=_START,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )


def _member(
    *,
    replay_specification: HistoricalReplaySpecification | None = None,
    reverse_strategies: bool = False,
    state_model: HistoricalReplayResearchStateModelInstance | None = None,
) -> HistoricalReplayResearchMemberSpecification:
    strategies = [
        BaselineTrendRegimeStrategy(),
        BaselineVolatilityRegimeStrategy(),
    ]
    if reverse_strategies:
        strategies.reverse()
    return HistoricalReplayResearchMemberSpecification(
        replay_specification=(
            _replay_specification()
            if replay_specification is None
            else replay_specification
        ),
        strategies=create_strategy_collection(strategies),
        state_model=(
            BaselineMarketStateModel()
            if state_model is None
            else state_model
        ),
        structure_derivation=default_replay_structure_derivation_identity(),
    )


def _workflow_specification(
    *,
    source: HistoricalPriceSeries | None = None,
    baseline: HistoricalReplayResearchMemberSpecification | None = None,
    candidates: tuple[
        HistoricalReplayResearchMemberSpecification,
        ...,
    ] = (),
    replay_revision: SoftwareRevision = _REPLAY_REVISION,
    comparison_revision: SoftwareRevision = _COMPARISON_REVISION,
    workflow_revision: SoftwareRevision = _WORKFLOW_REVISION,
) -> HistoricalReplayResearchWorkflowSpecification:
    return HistoricalReplayResearchWorkflowSpecification(
        source=(
            HistoricalPriceSeries(_prices())
            if source is None
            else source
        ),
        baseline=_member() if baseline is None else baseline,
        candidates=candidates,
        replay_software_revision=replay_revision,
        comparison_software_revision=comparison_revision,
        workflow_software_revision=workflow_revision,
    )


def _run(
    specification: HistoricalReplayResearchWorkflowSpecification,
    *,
    replay_service: HistoricalReplayService | None = None,
) -> HistoricalReplayResearchWorkflowResult:
    return HistoricalReplayResearchWorkflowService(
        HistoricalReplayService()
        if replay_service is None
        else replay_service
    ).run(specification)


class _ControlledReplayService(HistoricalReplayService):
    def __init__(
        self,
        failures: dict[int, BaseException],
    ) -> None:
        super().__init__()
        self.failures = failures
        self.calls = 0

    def run_execution(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        call_index = self.calls
        self.calls += 1
        failure = self.failures.get(call_index)
        if failure is not None:
            raise failure
        return super().run_execution(*args, **kwargs)  # type: ignore[arg-type]


class _MismatchedProvenanceReplayService(HistoricalReplayService):
    def run_execution(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        execution = super().run_execution(*args, **kwargs)  # type: ignore[arg-type]
        return replace(
            execution,
            provenance=replace(
                execution.provenance,
                provider="fabricated-provider",
            ),
        )


class _MutatingReplayService(HistoricalReplayService):
    def __init__(
        self,
        strategy: _MutableStrategyInstance,
        *,
        mutate_on_call: int,
    ) -> None:
        super().__init__()
        self.strategy = strategy
        self.mutate_on_call = mutate_on_call
        self.calls = 0

    def run_execution(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        execution = super().run_execution(*args, **kwargs)  # type: ignore[arg-type]
        self.calls += 1
        if self.calls == self.mutate_on_call:
            self.strategy.threshold += 1
        return execution


def test_existing_provider_research_boundary_remains_public() -> None:
    assert ResearchRequest is not None
    assert ResearchResult is not None
    assert ResearchStatus is not None
    assert ResearchWorkflow is not None
    assert DefaultResearchWorkflow is not None
    assert (StrategyRunnerError,) == (
        workflow_service._CAPTURED_REPLAY_EXECUTION_ERRORS
    )


def test_member_identity_is_deterministic_and_runtime_identity_neutral() -> None:
    first = _member()
    repeated = _member()
    reversed_member = _member(reverse_strategies=True)

    assert first == repeated
    assert first.member_fingerprint == repeated.member_fingerprint
    assert "state_model=" not in repr(first)
    assert "strategies=" not in repr(first)
    assert reversed_member.member_fingerprint != first.member_fingerprint
    assert tuple(
        identity.strategy_id for identity in reversed_member.strategy_identities
    ) == tuple(
        reversed(
            tuple(
                identity.strategy_id for identity in first.strategy_identities
            )
        )
    )


def test_member_identity_covers_state_structure_and_strategy_configuration() -> None:
    baseline = _member()
    state_configured = _member(state_model=_MutableStateModel(1))
    changed_structure = replace(
        baseline,
        structure_derivation=replace(
            baseline.structure_derivation,
            version="2.0.0",
        ),
    )

    assert state_configured.member_fingerprint != baseline.member_fingerprint
    assert changed_structure.member_fingerprint != baseline.member_fingerprint
    assert baseline.to_dict()["strategies"] == [
        identity.to_dict() for identity in baseline.strategy_identities
    ]


def test_member_strategy_mapping_order_is_neutral_and_duplicates_are_significant(
) -> None:
    default = BaselineTrendRegimeStrategy().configuration.to_dict()["parameters"]
    assert isinstance(default, dict)
    reversed_parameters = dict(reversed(tuple(default.items())))
    first_strategy = BaselineTrendRegimeStrategy(
        StrategyConfiguration(
            strategy_id="baseline_trend_regime",
            strategy_version="1.0.0",
            parameters=default,
        )
    )
    reordered_strategy = BaselineTrendRegimeStrategy(
        StrategyConfiguration(
            strategy_id="baseline_trend_regime",
            strategy_version="1.0.0",
            parameters=reversed_parameters,
        )
    )

    def configured_member(*strategies: BaselineTrendRegimeStrategy):
        return HistoricalReplayResearchMemberSpecification(
            replay_specification=_replay_specification(),
            strategies=create_strategy_collection(strategies),
            state_model=BaselineMarketStateModel(),
            structure_derivation=default_replay_structure_derivation_identity(),
        )

    first = configured_member(first_strategy)
    reordered = configured_member(reordered_strategy)
    duplicate = configured_member(first_strategy, first_strategy)

    assert first.member_fingerprint == reordered.member_fingerprint
    assert duplicate.member_fingerprint != first.member_fingerprint
    assert len(duplicate.strategy_identities) == 2


def test_workflow_rejects_strategy_without_strategy_instance_identity() -> None:
    broad_strategy = _BroadOnlyStrategy()
    strategies = create_strategy_collection([broad_strategy])
    execution = HistoricalReplayService().run_execution(
        _prices(),
        _replay_specification(),
        strategies=strategies,
        state_model=BaselineMarketStateModel(),
        software_revision=_REPLAY_REVISION,
        structure_derivation=default_replay_structure_derivation_identity(),
    )
    assert execution.result.step_count > 0

    with pytest.raises(TypeError, match="StrategyInstance"):
        HistoricalReplayResearchMemberSpecification(
            replay_specification=_replay_specification(),
            strategies=strategies,
            state_model=BaselineMarketStateModel(),
            structure_derivation=default_replay_structure_derivation_identity(),
        )


def test_mutated_strategy_identity_is_rejected_before_replay() -> None:
    strategy = _MutableStrategyInstance(1)
    member = HistoricalReplayResearchMemberSpecification(
        replay_specification=_replay_specification(),
        strategies=create_strategy_collection([strategy]),
        state_model=BaselineMarketStateModel(),
        structure_derivation=default_replay_structure_derivation_identity(),
    )
    unchanged = _run(
        _workflow_specification(
            baseline=HistoricalReplayResearchMemberSpecification(
                replay_specification=_replay_specification(),
                strategies=create_strategy_collection(
                    [_MutableStrategyInstance(1)]
                ),
                state_model=BaselineMarketStateModel(),
                structure_derivation=(
                    default_replay_structure_derivation_identity()
                ),
            )
        )
    )
    assert unchanged.status is HistoricalReplayResearchWorkflowStatus.SUCCEEDED

    specification = _workflow_specification(baseline=member)
    member_fingerprint = member.member_fingerprint
    workflow_fingerprint = specification.workflow_specification_fingerprint
    configuration_fingerprint = strategy.configuration.fingerprint
    strategy.threshold = 2
    controlled = _ControlledReplayService({})

    assert strategy.configuration.fingerprint != configuration_fingerprint
    with pytest.raises(ValueError, match="strategy collection executable identity"):
        _run(specification, replay_service=controlled)
    assert controlled.calls == 0
    assert member.member_fingerprint == member_fingerprint
    assert specification.workflow_specification_fingerprint == workflow_fingerprint


def test_workflow_requires_rederivable_state_model_identity() -> None:
    broad_model = _BroadOnlyStateModel()
    execution = HistoricalReplayService().run_execution(
        _prices(),
        _replay_specification(),
        strategies=create_strategy_collection(
            [BaselineTrendRegimeStrategy()]
        ),
        state_model=broad_model,
        software_revision=_REPLAY_REVISION,
        structure_derivation=default_replay_structure_derivation_identity(),
    )
    assert execution.result.step_count > 0

    with pytest.raises(
        TypeError,
        match="HistoricalReplayResearchStateModelInstance",
    ):
        HistoricalReplayResearchMemberSpecification(  # type: ignore[arg-type]
            replay_specification=_replay_specification(),
            strategies=create_strategy_collection(
                [BaselineTrendRegimeStrategy()]
            ),
            state_model=broad_model,
            structure_derivation=default_replay_structure_derivation_identity(),
        )


def test_mutated_state_model_identity_is_rejected_before_replay() -> None:
    state_model = _MutableStateModel(1)
    member = HistoricalReplayResearchMemberSpecification(
        replay_specification=_replay_specification(),
        strategies=create_strategy_collection(
            [BaselineTrendRegimeStrategy()]
        ),
        state_model=state_model,
        structure_derivation=default_replay_structure_derivation_identity(),
    )
    assert _run(
        _workflow_specification(
            baseline=_member(state_model=_MutableStateModel(1))
        )
    ).status is HistoricalReplayResearchWorkflowStatus.SUCCEEDED

    specification = _workflow_specification(baseline=member)
    member_fingerprint = member.member_fingerprint
    workflow_fingerprint = specification.workflow_specification_fingerprint
    configuration_fingerprint = state_model.configuration_fingerprint
    state_model.threshold = 2
    controlled = _ControlledReplayService({})

    assert state_model.configuration_fingerprint != configuration_fingerprint
    with pytest.raises(ValueError, match="state model executable identity"):
        _run(specification, replay_service=controlled)
    assert controlled.calls == 0
    assert member.member_fingerprint == member_fingerprint
    assert specification.workflow_specification_fingerprint == workflow_fingerprint


def test_identity_mutation_during_replay_is_rejected_before_artifact() -> None:
    strategy = _MutableStrategyInstance(1)
    baseline = HistoricalReplayResearchMemberSpecification(
        replay_specification=_replay_specification(),
        strategies=create_strategy_collection([strategy]),
        state_model=BaselineMarketStateModel(),
        structure_derivation=default_replay_structure_derivation_identity(),
    )
    service = _MutatingReplayService(strategy, mutate_on_call=1)

    with pytest.raises(ValueError, match="strategy collection executable identity"):
        _run(
            _workflow_specification(baseline=baseline),
            replay_service=service,
        )
    assert service.calls == 1


def test_duplicate_candidate_identity_is_revalidated_before_each_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = _MutableStrategyInstance(1)
    candidate = HistoricalReplayResearchMemberSpecification(
        replay_specification=_replay_specification(),
        strategies=create_strategy_collection([strategy]),
        state_model=BaselineMarketStateModel(),
        structure_derivation=default_replay_structure_derivation_identity(),
    )
    service = _ControlledReplayService({})
    original_artifact = HistoricalReplayArtifact.from_execution
    artifact_calls = 0

    def mutate_after_first_candidate(execution: object):
        nonlocal artifact_calls
        artifact = original_artifact(execution)  # type: ignore[arg-type]
        artifact_calls += 1
        if artifact_calls == 2:
            strategy.threshold += 1
        return artifact

    monkeypatch.setattr(
        HistoricalReplayArtifact,
        "from_execution",
        mutate_after_first_candidate,
    )
    with pytest.raises(ValueError, match="strategy collection executable identity"):
        _run(
            _workflow_specification(candidates=(candidate, candidate)),
            replay_service=service,
        )
    assert service.calls == 2
    assert artifact_calls == 2


def test_member_and_workflow_inputs_are_strictly_validated() -> None:
    with pytest.raises(TypeError, match="replay_specification"):
        HistoricalReplayResearchMemberSpecification(  # type: ignore[arg-type]
            replay_specification=object(),
            strategies=create_strategy_collection([]),
            state_model=BaselineMarketStateModel(),
            structure_derivation=default_replay_structure_derivation_identity(),
        )
    with pytest.raises(ValueError, match="sha256"):
        _member(state_model=_InvalidIdentityStateModel())
    with pytest.raises(TypeError, match="candidates must be a tuple"):
        HistoricalReplayResearchWorkflowSpecification(  # type: ignore[arg-type]
            source=HistoricalPriceSeries(_prices()),
            baseline=_member(),
            candidates=[],
            replay_software_revision=_REPLAY_REVISION,
            comparison_software_revision=_COMPARISON_REVISION,
            workflow_software_revision=_WORKFLOW_REVISION,
        )


def test_workflow_specification_order_duplicates_and_revisions_affect_identity(
) -> None:
    first_candidate = _member()
    second_candidate = _member(reverse_strategies=True)
    baseline = _workflow_specification(
        candidates=(first_candidate, second_candidate)
    )
    reordered = _workflow_specification(
        candidates=(second_candidate, first_candidate)
    )
    duplicates = _workflow_specification(
        candidates=(first_candidate, first_candidate)
    )

    assert baseline.workflow_specification_fingerprint != (
        reordered.workflow_specification_fingerprint
    )
    assert duplicates.candidates[0] == duplicates.candidates[1]
    assert duplicates.to_dict()["candidates"] == [
        {
            "candidate_index": 0,
            "member_fingerprint": first_candidate.member_fingerprint,
        },
        {
            "candidate_index": 1,
            "member_fingerprint": first_candidate.member_fingerprint,
        },
    ]
    for field_name in (
        "replay_software_revision",
        "comparison_software_revision",
        "workflow_software_revision",
    ):
        changed = replace(
            baseline,
            **{field_name: SoftwareRevision("changed", False)},
        )
        dirty = replace(
            baseline,
            **{field_name: SoftwareRevision(
                getattr(baseline, field_name).revision,
                True,
            )},
        )
        assert changed.workflow_specification_fingerprint != (
            baseline.workflow_specification_fingerprint
        )
        assert dirty.workflow_specification_fingerprint != (
            baseline.workflow_specification_fingerprint
        )


def test_workflow_source_provider_and_content_affect_identity() -> None:
    baseline = _workflow_specification()
    other_provider = _workflow_specification(
        source=HistoricalPriceSeries(_prices(provider="other-provider"))
    )
    changed_prices = _prices()
    changed_prices.loc[10, "close"] += 0.1
    changed_prices.loc[10, "high"] += 0.1
    other_content = _workflow_specification(
        source=HistoricalPriceSeries(changed_prices)
    )

    assert (
        baseline.source_content_fingerprint
        == other_provider.source_content_fingerprint
    )
    assert baseline.workflow_specification_fingerprint != (
        other_provider.workflow_specification_fingerprint
    )
    assert baseline.workflow_specification_fingerprint != (
        other_content.workflow_specification_fingerprint
    )


@pytest.mark.parametrize(
    "candidate",
    [
        _member(
            replay_specification=_replay_specification(symbol="AAPL")
        ),
        _member(
            replay_specification=_replay_specification(interval="1hour")
        ),
    ],
)
def test_workflow_rejects_member_symbol_or_interval_mismatch(
    candidate: HistoricalReplayResearchMemberSpecification,
) -> None:
    with pytest.raises(ValueError, match="source symbol|source interval"):
        _workflow_specification(candidates=(candidate,))


def test_replay_only_workflow_succeeds_deterministically() -> None:
    specification = _workflow_specification()
    first = _run(specification)
    repeated = _run(specification)

    assert first.status is HistoricalReplayResearchWorkflowStatus.SUCCEEDED
    assert first.baseline_artifact is not None
    assert first.candidates == ()
    assert first.experiment is None
    assert tuple(step.kind for step in first.steps) == (
        HistoricalReplayResearchWorkflowStepKind.BASELINE_REPLAY,
        HistoricalReplayResearchWorkflowStepKind.BASELINE_ARTIFACT,
    )
    assert first == repeated
    assert first.workflow_result_fingerprint == (
        repeated.workflow_result_fingerprint
    )


def test_complete_candidates_create_exact_existing_experiment() -> None:
    candidates = (_member(), _member(reverse_strategies=True))
    specification = _workflow_specification(candidates=candidates)
    result = _run(specification)

    assert result.status is HistoricalReplayResearchWorkflowStatus.SUCCEEDED
    assert result.baseline_artifact is not None
    assert result.experiment is not None
    artifacts = tuple(candidate.artifact for candidate in result.candidates)
    assert all(artifact is not None for artifact in artifacts)
    assert result.experiment.specification.baseline is result.baseline_artifact
    assert all(
        actual is expected
        for actual, expected in zip(
            result.experiment.specification.candidates,
            artifacts,
            strict=True,
        )
    )
    direct = create_historical_replay_experiment(
        HistoricalReplayExperimentSpecification(
            baseline=result.baseline_artifact,
            candidates=tuple(
                artifact for artifact in artifacts if artifact is not None
            ),
            software_revision=_COMPARISON_REVISION,
        )
    )
    assert result.experiment == direct


def test_incompatible_experiment_is_still_a_success() -> None:
    candidate = _member(
        replay_specification=_replay_specification(
            evaluation_start=_START + timedelta(days=51)
        )
    )
    result = _run(_workflow_specification(candidates=(candidate,)))

    assert result.status is HistoricalReplayResearchWorkflowStatus.SUCCEEDED
    assert result.experiment is not None
    assert not result.experiment.comparisons[0].compatibility.compatible


def test_duplicate_candidates_remain_distinct_positions() -> None:
    candidate = _member()
    result = _run(
        _workflow_specification(candidates=(candidate, candidate))
    )

    assert tuple(item.candidate_index for item in result.candidates) == (0, 1)
    assert result.experiment is not None
    assert tuple(
        comparison.candidate_index
        for comparison in result.experiment.comparisons
    ) == (0, 1)


def test_baseline_strategy_failure_skips_all_dependents() -> None:
    controlled = _ControlledReplayService(
        {0: StrategyRunnerError("baseline failed")}
    )
    specification = _workflow_specification(candidates=(_member(), _member()))
    first = _run(specification, replay_service=controlled)
    repeated = _run(
        specification,
        replay_service=_ControlledReplayService(
            {0: StrategyRunnerError("different unstable message")}
        ),
    )

    assert controlled.calls == 1
    assert first.status is HistoricalReplayResearchWorkflowStatus.FAILED
    assert first.baseline_artifact is None
    assert first.baseline_failure_code is (
        HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
    )
    assert all(
        candidate.replay_status
        is HistoricalReplayResearchWorkflowStepStatus.SKIPPED
        for candidate in first.candidates
    )
    assert all(
        step.status is HistoricalReplayResearchWorkflowStepStatus.SKIPPED
        for step in first.steps[1:]
    )
    assert first.workflow_result_fingerprint == (
        repeated.workflow_result_fingerprint
    )


def test_candidate_failures_continue_and_never_reduce_experiment() -> None:
    controlled = _ControlledReplayService(
        {
            1: StrategyRunnerError("first candidate failed"),
            3: StrategyRunnerError("third candidate failed"),
        }
    )
    candidates = (_member(), _member(), _member())
    result = _run(
        _workflow_specification(candidates=candidates),
        replay_service=controlled,
    )

    assert controlled.calls == 4
    assert result.status is (
        HistoricalReplayResearchWorkflowStatus.PARTIALLY_SUCCEEDED
    )
    assert tuple(
        candidate.replay_status for candidate in result.candidates
    ) == (
        HistoricalReplayResearchWorkflowStepStatus.FAILED,
        HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED,
        HistoricalReplayResearchWorkflowStepStatus.FAILED,
    )
    assert result.candidates[1].artifact is not None
    assert result.experiment is None
    assert result.steps[-1] == HistoricalReplayResearchWorkflowStepResult(
        kind=HistoricalReplayResearchWorkflowStepKind.EXPERIMENT,
        status=HistoricalReplayResearchWorkflowStepStatus.SKIPPED,
        skip_reason=(
            HistoricalReplayResearchWorkflowSkipReason.DEPENDENCY_FAILED
        ),
    )


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("value"),
        TypeError("type"),
        RuntimeError("runtime"),
        AssertionError("assertion"),
        KeyboardInterrupt(),
        SystemExit(),
    ],
)
def test_only_strategy_runner_error_is_captured(
    failure: BaseException,
) -> None:
    with pytest.raises(type(failure)):
        _run(
            _workflow_specification(),
            replay_service=_ControlledReplayService({0: failure}),
        )


def test_artifact_and_experiment_construction_failures_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_artifact(cls: object, execution: object) -> NoReturn:
        raise ValueError("artifact invariant defect")

    monkeypatch.setattr(
        HistoricalReplayArtifact,
        "from_execution",
        classmethod(fail_artifact),
    )
    with pytest.raises(ValueError, match="artifact invariant defect"):
        _run(_workflow_specification())

    monkeypatch.undo()

    def fail_experiment(specification: object) -> NoReturn:
        raise ValueError("experiment invariant defect")

    monkeypatch.setattr(
        workflow_service,
        "create_historical_replay_experiment",
        fail_experiment,
    )
    with pytest.raises(ValueError, match="experiment invariant defect"):
        _run(_workflow_specification(candidates=(_member(),)))


def test_execution_provenance_is_verified_before_artifact_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_called = False

    def unexpected_artifact(cls: object, execution: object) -> NoReturn:
        nonlocal artifact_called
        artifact_called = True
        raise AssertionError("Artifact construction must follow validation")

    monkeypatch.setattr(
        HistoricalReplayArtifact,
        "from_execution",
        classmethod(unexpected_artifact),
    )
    with pytest.raises(ValueError, match="provider does not match"):
        _run(
            _workflow_specification(),
            replay_service=_MismatchedProvenanceReplayService(),
        )

    assert not artifact_called


def test_service_invokes_replay_and_artifact_once_per_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_service = _ControlledReplayService({})
    artifact_calls = 0
    experiment_calls = 0
    original_artifact = HistoricalReplayArtifact.from_execution
    original_experiment = workflow_service.create_historical_replay_experiment

    def counted_artifact(execution: object):
        nonlocal artifact_calls
        artifact_calls += 1
        return original_artifact(execution)  # type: ignore[arg-type]

    def counted_experiment(specification: object):
        nonlocal experiment_calls
        experiment_calls += 1
        return original_experiment(specification)  # type: ignore[arg-type]

    monkeypatch.setattr(
        HistoricalReplayArtifact,
        "from_execution",
        counted_artifact,
    )
    monkeypatch.setattr(
        workflow_service,
        "create_historical_replay_experiment",
        counted_experiment,
    )
    _run(
        _workflow_specification(candidates=(_member(), _member())),
        replay_service=replay_service,
    )

    assert replay_service.calls == 3
    assert artifact_calls == 3
    assert experiment_calls == 1


def test_workflow_artifact_is_identical_to_direct_composition() -> None:
    specification = _workflow_specification()
    workflow_result = _run(specification)
    direct_execution = HistoricalReplayService().run_execution(
        specification.source.to_dataframe(),
        specification.baseline.replay_specification,
        strategies=specification.baseline.strategies,
        state_model=specification.baseline.state_model,
        software_revision=specification.replay_software_revision,
        structure_derivation=specification.baseline.structure_derivation,
        state_model_configuration_fingerprint=(
            specification.baseline.state_model_configuration_fingerprint
        ),
    )
    direct_artifact = HistoricalReplayArtifact.from_execution(direct_execution)

    assert workflow_result.baseline_artifact == direct_artifact
    assert workflow_result.baseline_artifact is not None
    assert workflow_result.baseline_artifact.to_dict() == direct_artifact.to_dict()
    assert workflow_result.baseline_artifact.integrity_checksum == (
        direct_artifact.integrity_checksum
    )
    workflow_bytes = json.dumps(
        workflow_result.baseline_artifact.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    direct_bytes = json.dumps(
        direct_artifact.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    assert workflow_bytes == direct_bytes
    assert (
        "integrity_checksum"
        not in workflow_result._fingerprint_payload()["baseline"]["artifact"]  # type: ignore[index]
    )


def test_result_direct_construction_and_fabricated_membership_are_rejected() -> None:
    with pytest.raises(
        TypeError,
        match="HistoricalReplayResearchWorkflowService.run",
    ):
        HistoricalReplayResearchWorkflowResult()

    specification = _workflow_specification(candidates=(_member(),))
    complete = _run(specification)
    assert complete.baseline_artifact is not None
    assert complete.candidates[0].artifact is not None
    fabricated = replace(
        complete.candidates[0],
        member_specification_fingerprint="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="another member"):
        HistoricalReplayResearchWorkflowResult._create(
            specification=specification,
            baseline_artifact=complete.baseline_artifact,
            baseline_failure_code=None,
            candidates=(fabricated,),
            experiment=complete.experiment,
        )


def test_candidate_and_step_local_invariants_are_enforced() -> None:
    with pytest.raises(TypeError, match="integer"):
        HistoricalReplayResearchWorkflowCandidateResult(
            candidate_index=True,  # type: ignore[arg-type]
            member_specification_fingerprint="sha256:" + "0" * 64,
            replay_status=HistoricalReplayResearchWorkflowStepStatus.FAILED,
            failure_code=(
                HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
            ),
        )
    with pytest.raises(ValueError, match="requires an Artifact"):
        HistoricalReplayResearchWorkflowCandidateResult(
            candidate_index=0,
            member_specification_fingerprint="sha256:" + "0" * 64,
            replay_status=HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED,
        )
    with pytest.raises(ValueError, match="only Replay steps may fail"):
        HistoricalReplayResearchWorkflowStepResult(
            kind=HistoricalReplayResearchWorkflowStepKind.BASELINE_ARTIFACT,
            status=HistoricalReplayResearchWorkflowStepStatus.FAILED,
            failure_code=(
                HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
            ),
        )
    with pytest.raises(ValueError, match="comparison identities"):
        HistoricalReplayResearchWorkflowStepResult(
            kind=HistoricalReplayResearchWorkflowStepKind.EXPERIMENT,
            status=HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED,
            experiment_fingerprint="sha256:" + "0" * 64,
        )


def test_models_are_frozen_and_source_data_is_not_exposed_in_repr() -> None:
    specification = _workflow_specification()
    result = _run(specification)

    assert "DataFrame" not in repr(specification)
    with pytest.raises(FrozenInstanceError):
        specification.source_provider = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.status = HistoricalReplayResearchWorkflowStatus.FAILED  # type: ignore[misc]
