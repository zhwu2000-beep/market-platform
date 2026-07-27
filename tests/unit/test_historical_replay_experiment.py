from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from market_platform.replay import (
    HistoricalReplayArtifact,
    HistoricalReplayComparisonIncompatibilityReason,
    HistoricalReplayExecution,
    HistoricalReplayExecutionDifference,
    HistoricalReplayExperimentSpecification,
    HistoricalReplayResult,
    HistoricalReplayRunProvenance,
    HistoricalReplaySpecification,
    HistoricalReplayStep,
    ReplaySignalDerivationIdentity,
    ReplayStrategyIdentity,
    ReplayStructureDerivationIdentity,
    SoftwareRevision,
    compare_historical_replay_artifacts,
    create_historical_replay_experiment,
)
from market_platform.state import (
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StateClassificationThresholdEvidence,
    StateCompositeEvidence,
    StateEvaluationEvidence,
    StateModelProvenance,
    StateQuality,
    StateSignalEvidence,
    StateVolatilityEvidence,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)
from market_platform.strategy import (
    StrategyEvaluation,
    StrategyEvaluationStatus,
    StrategyEvidence,
    StrategyEvidenceSource,
    StrategyProvenance,
    StrategyRunResult,
)

_START = datetime(2026, 8, 1, tzinfo=UTC)
_DATASET = 'sha256:' + 'a' * 64
_OBSERVATIONS = ('sha256:' + 'b' * 64, 'sha256:' + 'c' * 64)
_SIGNALS = 'sha256:' + 'd' * 64
_STRUCTURE = 'sha256:' + 'e' * 64
_STATE_CONFIG = 'sha256:' + 'f' * 64
_STRATEGY_CONFIG = 'sha256:' + '1' * 64
_COMPARISON_SOFTWARE = SoftwareRevision('comparison-revision', False)


def _identity(
    strategy_id: str = 'strategy',
    version: str = '1.0.0',
    configuration: str | None = _STRATEGY_CONFIG,
) -> ReplayStrategyIdentity:
    return ReplayStrategyIdentity(strategy_id, version, configuration)


def _state(
    as_of: datetime,
    observation_fingerprint: str,
    *,
    directional: DirectionalRegime = DirectionalRegime.UP,
    quality: StateQuality = StateQuality.COMPLETE,
    missing_inputs: tuple[str, ...] = (),
    provenance_marker: str = 'base',
    evidence_score: float | None = 0.5,
) -> MarketState:
    evaluation_evidence = None
    if evidence_score is not None:
        component = StateSignalEvidence(
            name='trend',
            raw_value=evidence_score,
            normalized_score=evidence_score,
            normalization_scale=1.0,
            configured_weight=1.0,
            normalized_weight=1.0,
            weighted_contribution=evidence_score,
            interpreted_state='up',
            methodology='experiment-test',
            source_parameters={'marker': provenance_marker},
        )
        evaluation_evidence = StateEvaluationEvidence(
            directional_components=(component,),
            composite=StateCompositeEvidence(
                score=evidence_score,
                classification='up',
                methodology='experiment-test',
                formula='trend',
                thresholds=StateClassificationThresholdEvidence(
                    strong_bearish=-0.5,
                    bearish=-0.1,
                    bullish=0.1,
                    strong_bullish=0.5,
                ),
                component_order=('trend',),
                included_signals=('trend',),
                missing_signals=(),
            ),
            volatility=StateVolatilityEvidence(
                raw_value=0.2,
                low_threshold=0.1,
                high_threshold=0.3,
                regime=VolatilityRegime.NORMAL,
                methodology='experiment-test',
            ),
        )
    return MarketState(
        symbol='MSFT',
        interval='1day',
        as_of=as_of,
        provenance=StateModelProvenance(
            model_id='state-model',
            model_version='1.0.0',
            parameters={'marker': provenance_marker},
            observation_fingerprint=observation_fingerprint,
        ),
        directional_regime=directional,
        trend_regime=TrendRegime.UP,
        momentum_regime=MomentumRegime.POSITIVE,
        volatility_regime=VolatilityRegime.NORMAL,
        structure_state=StructureState.AVAILABLE,
        quality=quality,
        missing_inputs=missing_inputs,
        evaluation_evidence=evaluation_evidence,
    )


def _evaluation(
    identity: ReplayStrategyIdentity,
    as_of: datetime,
    observation_fingerprint: str,
    *,
    status: StrategyEvaluationStatus = StrategyEvaluationStatus.APPLICABLE,
    rationale: str = 'Strategy applies.',
    evidence_value: object = 'up',
    provenance_marker: str = 'base',
) -> StrategyEvaluation:
    missing_inputs = (
        ('trend_regime',)
        if status is StrategyEvaluationStatus.INSUFFICIENT_DATA
        else ()
    )
    return StrategyEvaluation(
        symbol='MSFT',
        interval='1day',
        as_of=as_of,
        provenance=StrategyProvenance(
            strategy_id=identity.strategy_id,
            strategy_version=identity.strategy_version,
            parameters={'marker': provenance_marker},
            observation_fingerprint=observation_fingerprint,
            state_model_id='state-model',
            state_model_version='1.0.0',
            configuration_fingerprint=identity.configuration_fingerprint,
        ),
        status=status,
        rationale=rationale,
        required_inputs=('trend_regime',),
        missing_inputs=missing_inputs,
        evidence=(
            StrategyEvidence(
                source=StrategyEvidenceSource.MARKET_STATE,
                field='trend_regime',
                observed_value=evidence_value,  # type: ignore[arg-type]
                rationale='Observed structural state.',
                observed_at=as_of,
            ),
        ),
    )


def _artifact(
    *,
    symbol: str = 'MSFT',
    interval: str = '1day',
    dataset_fingerprint: str = _DATASET,
    provider: str = 'provider-a',
    timestamps: tuple[datetime, ...] = (_START, _START + timedelta(days=1)),
    observation_fingerprints: tuple[str, ...] = _OBSERVATIONS,
    identities: tuple[ReplayStrategyIdentity, ...] = (_identity(),),
    statuses: tuple[tuple[StrategyEvaluationStatus, ...], ...] | None = None,
    states: tuple[MarketState, ...] | None = None,
    rationale: str = 'Strategy applies.',
    evidence_value: object = 'up',
    strategy_provenance_marker: str = 'base',
    replay_revision: str = 'replay-revision',
) -> HistoricalReplayArtifact:
    if len(timestamps) != len(observation_fingerprints):
        raise ValueError('test timestamps and observations must align')
    if statuses is None:
        statuses = tuple(
            tuple(StrategyEvaluationStatus.APPLICABLE for _ in identities)
            for _ in timestamps
        )
    if states is None:
        states = tuple(
            _state(as_of, fingerprint)
            for as_of, fingerprint in zip(
                timestamps,
                observation_fingerprints,
                strict=True,
            )
        )
    steps = []
    for step_index, (as_of, fingerprint, state) in enumerate(
        zip(timestamps, observation_fingerprints, states, strict=True)
    ):
        evaluations = tuple(
            _evaluation(
                identity,
                as_of,
                fingerprint,
                status=statuses[step_index][identity_index],
                rationale=rationale,
                evidence_value=evidence_value,
                provenance_marker=strategy_provenance_marker,
            )
            for identity_index, identity in enumerate(identities)
        )
        steps.append(
            HistoricalReplayStep(
                symbol=symbol,
                interval=interval,
                as_of=as_of,
                observation_fingerprint=fingerprint,
                state=replace(state, symbol=symbol, interval=interval),
                strategy_result=StrategyRunResult(
                    symbol=symbol,
                    interval=interval,
                    as_of=as_of,
                    observation_fingerprint=fingerprint,
                    state_model_id='state-model',
                    state_model_version='1.0.0',
                    evaluations=tuple(
                        replace(
                            evaluation,
                            symbol=symbol,
                            interval=interval,
                        )
                        for evaluation in evaluations
                    ),
                ),
            )
        )
    result = HistoricalReplayResult(
        symbol=symbol,
        interval=interval,
        start_as_of=timestamps[0],
        end_as_of=timestamps[-1],
        steps=tuple(steps),
        state_model_id='state-model',
        state_model_version='1.0.0',
        strategies=identities,
    )
    specification = HistoricalReplaySpecification(
        symbol=symbol,
        interval=interval,
        context_start=timestamps[0] - timedelta(days=2),
        evaluation_start=timestamps[0],
        evaluation_end=timestamps[-1],
    )
    provenance = HistoricalReplayRunProvenance(
        specification=specification,
        specification_fingerprint=specification.fingerprint,
        dataset_content_fingerprint=dataset_fingerprint,
        provider=provider,
        context_start=timestamps[0] - timedelta(days=2),
        context_end=timestamps[-1],
        context_row_count=len(timestamps) + 2,
        evaluation_start=timestamps[0],
        evaluation_end=timestamps[-1],
        evaluation_step_count=len(timestamps),
        signal_derivation=ReplaySignalDerivationIdentity(
            'signals',
            '1.0.0',
            _SIGNALS,
        ),
        structure_derivation=ReplayStructureDerivationIdentity(
            'structure',
            '1.0.0',
            _STRUCTURE,
        ),
        state_model_id='state-model',
        state_model_version='1.0.0',
        state_model_configuration_fingerprint=_STATE_CONFIG,
        strategies=identities,
        software_revision=SoftwareRevision(replay_revision, False),
    )
    return HistoricalReplayArtifact.from_execution(
        HistoricalReplayExecution(result=result, provenance=provenance)
    )


def _artifact_with_states(
    baseline: HistoricalReplayArtifact,
    states: tuple[MarketState, ...],
) -> HistoricalReplayArtifact:
    result = baseline.execution.result
    steps = tuple(
        replace(step, state=state)
        for step, state in zip(result.steps, states, strict=True)
    )
    execution = HistoricalReplayExecution(
        result=replace(result, steps=steps),
        provenance=baseline.execution.provenance,
    )
    return HistoricalReplayArtifact.from_execution(execution)


def _artifact_with_required_inputs(
    baseline: HistoricalReplayArtifact,
    required_inputs: tuple[str, ...],
) -> HistoricalReplayArtifact:
    result = baseline.execution.result
    steps = tuple(
        replace(
            step,
            strategy_result=replace(
                step.strategy_result,
                evaluations=tuple(
                    replace(evaluation, required_inputs=required_inputs)
                    for evaluation in step.strategy_result.evaluations
                ),
            ),
        )
        for step in result.steps
    )
    execution = HistoricalReplayExecution(
        result=replace(result, steps=steps),
        provenance=baseline.execution.provenance,
    )
    return HistoricalReplayArtifact.from_execution(execution)


def _artifact_with_strategy_parameters(
    baseline: HistoricalReplayArtifact,
    parameters: Mapping[str, object],
) -> HistoricalReplayArtifact:
    result = baseline.execution.result
    steps = tuple(
        replace(
            step,
            strategy_result=replace(
                step.strategy_result,
                evaluations=tuple(
                    replace(
                        evaluation,
                        provenance=replace(
                            evaluation.provenance,
                            parameters=parameters,
                        ),
                    )
                    for evaluation in step.strategy_result.evaluations
                ),
            ),
        )
        for step in result.steps
    )
    return HistoricalReplayArtifact.from_execution(
        HistoricalReplayExecution(
            result=replace(result, steps=steps),
            provenance=baseline.execution.provenance,
        )
    )


def _artifact_with_state_parameters(
    baseline: HistoricalReplayArtifact,
    parameters: Mapping[str, object],
) -> HistoricalReplayArtifact:
    result = baseline.execution.result
    states = tuple(
        replace(
            step.state,
            provenance=replace(step.state.provenance, parameters=parameters),
        )
        for step in result.steps
    )
    return _artifact_with_states(baseline, states)


def test_experiment_identity_is_deterministic_ordered_and_immutable() -> None:
    baseline = _artifact()
    first = _artifact(replay_revision='candidate-one')
    second = _artifact(rationale='Different rationale.')
    specification = HistoricalReplayExperimentSpecification(
        baseline,
        (first, second),
        _COMPARISON_SOFTWARE,
    )

    assert replace(specification).experiment_fingerprint == (
        specification.experiment_fingerprint
    )
    assert HistoricalReplayExperimentSpecification(
        baseline,
        (second, first),
        _COMPARISON_SOFTWARE,
    ).experiment_fingerprint != specification.experiment_fingerprint
    assert HistoricalReplayExperimentSpecification(
        baseline,
        (first, second),
        SoftwareRevision('other-comparison', False),
    ).experiment_fingerprint != specification.experiment_fingerprint
    assert HistoricalReplayExperimentSpecification(
        baseline,
        (first, second),
        SoftwareRevision('comparison-revision', True),
    ).experiment_fingerprint != specification.experiment_fingerprint
    assert HistoricalReplayExperimentSpecification(
        baseline,
        (first, first),
        _COMPARISON_SOFTWARE,
    ).candidates == (first, first)
    with pytest.raises(FrozenInstanceError):
        specification.candidates = ()  # type: ignore[misc]
    with pytest.raises(ValueError, match='candidates'):
        HistoricalReplayExperimentSpecification(
            baseline,
            (),
            _COMPARISON_SOFTWARE,
        )


@pytest.mark.parametrize(
    ('candidate', 'expected'),
    [
        (
            _artifact(symbol='AAPL'),
            (HistoricalReplayComparisonIncompatibilityReason.SYMBOL_MISMATCH,),
        ),
        (
            _artifact(interval='daily'),
            (HistoricalReplayComparisonIncompatibilityReason.INTERVAL_MISMATCH,),
        ),
        (
            _artifact(dataset_fingerprint='sha256:' + '2' * 64),
            (
                HistoricalReplayComparisonIncompatibilityReason
                .DATASET_CONTENT_FINGERPRINT_MISMATCH,
            ),
        ),
        (
            _artifact(
                timestamps=(_START, _START + timedelta(days=2)),
            ),
            (
                HistoricalReplayComparisonIncompatibilityReason
                .EVALUATION_TIMESTAMPS_MISMATCH,
            ),
        ),
        (
            _artifact(
                observation_fingerprints=(
                    _OBSERVATIONS[0],
                    'sha256:' + '3' * 64,
                )
            ),
            (
                HistoricalReplayComparisonIncompatibilityReason
                .OBSERVATION_FINGERPRINTS_MISMATCH,
            ),
        ),
    ],
)
def test_compatibility_reasons_are_independent_and_suppress_aligned_detail(
    candidate: HistoricalReplayArtifact,
    expected: tuple[HistoricalReplayComparisonIncompatibilityReason, ...],
) -> None:
    comparison = compare_historical_replay_artifacts(
        _artifact(),
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.compatibility.reasons == expected
    assert not comparison.compatibility.compatible
    assert comparison.summary is None
    assert comparison.changed_steps == ()


def test_multiple_incompatibilities_have_policy_order() -> None:
    comparison = compare_historical_replay_artifacts(
        _artifact(),
        _artifact(
            symbol='AAPL',
            interval='daily',
            dataset_fingerprint='sha256:' + '4' * 64,
            timestamps=(_START, _START + timedelta(days=3)),
            observation_fingerprints=(
                'sha256:' + '5' * 64,
                'sha256:' + '6' * 64,
            ),
        ),
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.compatibility.reasons == tuple(
        HistoricalReplayComparisonIncompatibilityReason
    )


def test_unequal_step_lengths_report_complete_sequence_mismatches() -> None:
    comparison = compare_historical_replay_artifacts(
        _artifact(),
        _artifact(
            timestamps=(_START,),
            observation_fingerprints=(_OBSERVATIONS[0],),
        ),
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.compatibility.reasons == (
        HistoricalReplayComparisonIncompatibilityReason
        .EVALUATION_TIMESTAMPS_MISMATCH,
        HistoricalReplayComparisonIncompatibilityReason
        .OBSERVATION_FINGERPRINTS_MISMATCH,
    )
    assert comparison.summary is None
    assert comparison.changed_steps == ()


def test_provider_difference_is_reported_but_not_an_independent_rejection() -> None:
    baseline = _artifact(provider='provider-a')
    same_observations = _artifact(provider='provider-b')
    compatible = compare_historical_replay_artifacts(
        baseline,
        same_observations,
        software_revision=_COMPARISON_SOFTWARE,
    )
    mismatched_observations = compare_historical_replay_artifacts(
        baseline,
        _artifact(
            provider='provider-b',
            observation_fingerprints=(
                'sha256:' + '7' * 64,
                'sha256:' + '8' * 64,
            ),
        ),
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert compatible.compatibility.compatible
    assert 'provider' in {
        difference.field for difference in compatible.execution_differences
    }
    assert mismatched_observations.compatibility.reasons == (
        HistoricalReplayComparisonIncompatibilityReason
        .OBSERVATION_FINGERPRINTS_MISMATCH,
    )


def test_identical_outputs_have_complete_zero_summary() -> None:
    artifact = _artifact()
    comparison = compare_historical_replay_artifacts(
        artifact,
        artifact,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.compatibility.compatible
    assert comparison.changed_steps == ()
    assert comparison.summary is not None
    assert comparison.summary.total_aligned_steps == 2
    assert comparison.summary.unchanged_step_count == 2
    assert comparison.summary.changed_step_count == 0
    assert comparison.summary.first_differing_as_of is None
    assert comparison.summary.last_differing_as_of is None
    assert comparison.execution_differences == ()


def test_state_semantic_provenance_and_evidence_changes_are_distinct() -> None:
    baseline = _artifact()
    result = baseline.execution.result
    first = result.steps[0].state
    second = result.steps[1].state
    candidate = _artifact_with_states(
        baseline,
        (
            replace(first, directional_regime=DirectionalRegime.DOWN),
            _state(
                second.as_of,
                second.provenance.observation_fingerprint or '',
                provenance_marker='changed',
                evidence_score=0.4,
            ),
        ),
    )

    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert comparison.summary is not None
    assert comparison.summary.changed_step_count == 2
    assert comparison.summary.state_semantic_change_count == 1
    assert comparison.summary.state_provenance_change_count == 1
    assert comparison.summary.state_evaluation_evidence_change_count == 1
    assert comparison.summary.first_differing_as_of == _START
    assert comparison.summary.last_differing_as_of == _START + timedelta(days=1)
    state_difference = comparison.changed_steps[0].state_difference
    assert state_difference is not None
    assert tuple(
        difference.field for difference in state_difference.field_differences
    ) == ('directional_regime',)


def test_state_quality_and_missing_inputs_use_fixed_field_order() -> None:
    baseline = _artifact()
    result = baseline.execution.result
    candidate = _artifact_with_states(
        baseline,
        tuple(
            replace(
                step.state,
                quality=StateQuality.DEGRADED,
                missing_inputs=('momentum',),
            )
            for step in result.steps
        ),
    )

    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.summary is not None
    assert comparison.summary.state_semantic_change_count == 2
    assert tuple(
        difference.field
        for difference in comparison.changed_steps[0]
        .state_difference.field_differences  # type: ignore[union-attr]
    ) == ('quality', 'missing_inputs')


def test_strategy_changes_are_typed_counted_and_fingerprinted() -> None:
    baseline = _artifact()
    candidate = _artifact(
        statuses=(
            (StrategyEvaluationStatus.NOT_APPLICABLE,),
            (StrategyEvaluationStatus.APPLICABLE,),
        ),
        rationale='Changed rationale.',
        evidence_value=datetime(2026, 8, 1, tzinfo=UTC),
        strategy_provenance_marker='changed',
    )

    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )
    repeated = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert repeated == comparison
    assert repeated.comparison_fingerprint == comparison.comparison_fingerprint
    assert comparison.summary is not None
    assert comparison.summary.status_change_count == 1
    assert comparison.summary.rationale_change_count == 2
    assert comparison.summary.evidence_change_count == 2
    assert comparison.summary.strategy_provenance_change_count == 2
    difference = comparison.changed_steps[0].strategy_differences[0]
    assert difference.status_changed
    assert difference.rationale_changed
    assert difference.evidence_changed
    payload = comparison.to_dict()
    observed = payload['changed_steps'][0]['strategy_differences'][0][  # type: ignore[index]
        'candidate_evaluation'
    ]['evidence'][0]['observed_value']
    assert observed['type'] == 'datetime'


def test_strategy_missing_input_change_is_counted() -> None:
    baseline = _artifact()
    candidate = _artifact(
        statuses=(
            (StrategyEvaluationStatus.INSUFFICIENT_DATA,),
            (StrategyEvaluationStatus.INSUFFICIENT_DATA,),
        )
    )

    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.summary is not None
    assert comparison.summary.status_change_count == 2
    assert comparison.summary.missing_input_change_count == 2
    baseline_distribution = comparison.summary.strategy_members[
        0
    ].baseline_status_distribution
    candidate_distribution = comparison.summary.strategy_members[
        0
    ].candidate_status_distribution
    assert tuple(value.count for value in baseline_distribution) == (2, 0, 0)
    assert tuple(value.count for value in candidate_distribution) == (0, 0, 2)


def test_strategy_required_input_change_is_counted() -> None:
    baseline = _artifact()
    candidate = _artifact_with_required_inputs(
        baseline,
        ('trend_regime', 'volatility_regime'),
    )

    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.summary is not None
    assert comparison.summary.required_input_change_count == 2
    assert comparison.summary.missing_input_change_count == 0
    assert all(
        difference.required_inputs_changed
        for step in comparison.changed_steps
        for difference in step.strategy_differences
    )


def test_typed_evidence_changes_comparison_identity() -> None:
    visible_text = '2026-08-01T00:00:00+00:00'
    string_candidate = _artifact(evidence_value=visible_text)
    datetime_candidate = _artifact(
        evidence_value=datetime(2026, 8, 1, tzinfo=UTC)
    )

    string_comparison = compare_historical_replay_artifacts(
        _artifact(),
        string_candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )
    datetime_comparison = compare_historical_replay_artifacts(
        _artifact(),
        datetime_candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert string_comparison.comparison_fingerprint != (
        datetime_comparison.comparison_fingerprint
    )
    assert string_comparison.summary is not None
    assert datetime_comparison.summary is not None
    assert string_comparison.summary.evidence_change_count == 2
    assert datetime_comparison.summary.evidence_change_count == 2


@pytest.mark.parametrize(
    ('baseline_value', 'candidate_value'),
    [
        (True, 1),
        (1, 1.0),
        (None, 'none'),
        (1.0, -1.0),
    ],
)
def test_typed_evidence_scalar_changes_are_detected(
    baseline_value: object,
    candidate_value: object,
) -> None:
    comparison = compare_historical_replay_artifacts(
        _artifact(evidence_value=baseline_value),
        _artifact(evidence_value=candidate_value),
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.summary is not None
    assert comparison.summary.evidence_change_count == 2
    assert comparison.summary.changed_step_count == 2


def test_signed_zero_evidence_is_semantically_equal() -> None:
    positive_zero = compare_historical_replay_artifacts(
        _artifact(evidence_value=0.0),
        _artifact(evidence_value=0.0),
        software_revision=_COMPARISON_SOFTWARE,
    )
    signed_zero = compare_historical_replay_artifacts(
        _artifact(evidence_value=0.0),
        _artifact(evidence_value=-0.0),
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert signed_zero.summary is not None
    assert signed_zero.summary.evidence_change_count == 0
    assert signed_zero.changed_steps == ()
    assert signed_zero.comparison_fingerprint == positive_zero.comparison_fingerprint


def test_nested_provenance_comparison_is_typed_and_order_independent() -> None:
    baseline = _artifact()
    strategy_bool = _artifact_with_strategy_parameters(
        baseline,
        {'nested': {'value': True}, 'other': 2},
    )
    strategy_int = _artifact_with_strategy_parameters(
        baseline,
        {'other': 2, 'nested': {'value': 1}},
    )
    strategy_float = _artifact_with_strategy_parameters(
        baseline,
        {'nested': {'value': 1.0}, 'other': 2},
    )
    bool_to_int = compare_historical_replay_artifacts(
        strategy_bool,
        strategy_int,
        software_revision=_COMPARISON_SOFTWARE,
    )
    int_to_float = compare_historical_replay_artifacts(
        strategy_int,
        strategy_float,
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert bool_to_int.summary is not None
    assert int_to_float.summary is not None
    assert bool_to_int.summary.strategy_provenance_change_count == 2
    assert int_to_float.summary.strategy_provenance_change_count == 2

    ordered = _artifact_with_strategy_parameters(
        baseline,
        {'first': 0.0, 'second': {'value': 1}},
    )
    reordered_signed_zero = _artifact_with_strategy_parameters(
        baseline,
        {'second': {'value': 1}, 'first': -0.0},
    )
    equivalent = compare_historical_replay_artifacts(
        ordered,
        reordered_signed_zero,
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert equivalent.summary is not None
    assert equivalent.summary.strategy_provenance_change_count == 0
    assert equivalent.changed_steps == ()


def test_state_provenance_typed_changes_and_signed_zero_canonicalization() -> None:
    baseline = _artifact()
    state_bool = _artifact_with_state_parameters(
        baseline,
        {'nested': {'value': True}},
    )
    state_int = _artifact_with_state_parameters(
        baseline,
        {'nested': {'value': 1}},
    )
    typed_change = compare_historical_replay_artifacts(
        state_bool,
        state_int,
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert typed_change.summary is not None
    assert typed_change.summary.state_provenance_change_count == 2

    zero = _artifact_with_state_parameters(baseline, {'nested': {'value': 0.0}})
    signed_zero = _artifact_with_state_parameters(
        baseline,
        {'nested': {'value': -0.0}},
    )
    equivalent = compare_historical_replay_artifacts(
        zero,
        signed_zero,
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert equivalent.summary is not None
    assert equivalent.summary.state_provenance_change_count == 0
    assert equivalent.changed_steps == ()


def test_state_payload_signed_zero_is_fingerprint_neutral() -> None:
    timestamps = (_START, _START + timedelta(days=1))
    baseline_states = tuple(
        _state(as_of, fingerprint, evidence_score=0.0)
        for as_of, fingerprint in zip(timestamps, _OBSERVATIONS, strict=True)
    )
    baseline = _artifact(states=baseline_states)
    candidate_zero = _artifact(
        states=tuple(
            replace(state, directional_regime=DirectionalRegime.DOWN)
            for state in baseline_states
        )
    )
    candidate_signed_zero = _artifact(
        states=tuple(
            replace(
                _state(as_of, fingerprint, evidence_score=-0.0),
                directional_regime=DirectionalRegime.DOWN,
            )
            for as_of, fingerprint in zip(timestamps, _OBSERVATIONS, strict=True)
        )
    )
    zero_comparison = compare_historical_replay_artifacts(
        baseline,
        candidate_zero,
        software_revision=_COMPARISON_SOFTWARE,
    )
    signed_comparison = compare_historical_replay_artifacts(
        baseline,
        candidate_signed_zero,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert zero_comparison.comparison_fingerprint == (
        signed_comparison.comparison_fingerprint
    )
    assert signed_comparison.summary is not None
    assert signed_comparison.summary.state_semantic_change_count == 2
    assert signed_comparison.summary.state_evaluation_evidence_change_count == 0


def test_strategy_alignment_handles_reorder_duplicates_add_remove_and_empty() -> None:
    first = _identity('first')
    duplicate_v1 = _identity('duplicate', '1.0.0')
    duplicate_v2 = _identity('duplicate', '2.0.0')
    baseline = _artifact(identities=(first, duplicate_v1, duplicate_v2))
    candidate = _artifact(
        identities=(duplicate_v1, duplicate_v2, _identity('added')),
    )

    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert comparison.summary is not None
    keys = tuple(
        summary.member_key
        for summary in comparison.summary.strategy_members
    )
    assert tuple((key.strategy_id, key.occurrence_index) for key in keys) == (
        ('first', 0),
        ('duplicate', 0),
        ('duplicate', 1),
        ('added', 0),
    )
    assert comparison.summary.added_strategy_member_count == 1
    assert comparison.summary.removed_strategy_member_count == 1

    empty = compare_historical_replay_artifacts(
        _artifact(identities=()),
        _artifact(identities=()),
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert empty.summary is not None
    assert empty.summary.total_strategy_member_comparisons == 0
    assert empty.summary.strategy_members == ()


def test_version_and_configuration_changes_align_by_id_occurrence() -> None:
    baseline = _artifact(identities=(_identity('same', '1.0.0'),))
    candidate = _artifact(
        identities=(
            _identity('same', '2.0.0', 'sha256:' + '9' * 64),
        )
    )
    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert comparison.summary is not None
    assert comparison.summary.identity_version_change_count == 2
    assert comparison.summary.configuration_fingerprint_change_count == 2
    difference = comparison.changed_steps[0].strategy_differences[0]
    assert difference.member_key.strategy_id == 'same'
    assert difference.identity_version_changed
    assert difference.configuration_fingerprint_changed


def test_experiment_preserves_candidate_order_and_mixed_compatibility() -> None:
    baseline = _artifact()
    first = _artifact(rationale='Changed.')
    second = _artifact(dataset_fingerprint='sha256:' + '0' * 64)
    specification = HistoricalReplayExperimentSpecification(
        baseline,
        (first, second, first),
        _COMPARISON_SOFTWARE,
    )
    experiment = create_historical_replay_experiment(specification)

    assert experiment.experiment_fingerprint == specification.experiment_fingerprint
    assert tuple(result.candidate_index for result in experiment.comparisons) == (
        0,
        1,
        2,
    )
    assert experiment.comparisons[0].compatibility.compatible
    assert not experiment.comparisons[1].compatibility.compatible
    assert experiment.comparisons[2] == replace(
        experiment.comparisons[0],
        candidate_index=2,
    )


def test_comparison_does_not_execute_replay_or_use_filesystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import market_platform.replay.artifact_file as artifact_file
    import market_platform.replay.service as replay_service

    baseline = _artifact()
    candidate = _artifact(rationale='Changed.')

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError('comparison crossed an execution or I/O boundary')

    monkeypatch.setattr(replay_service.HistoricalReplayService, 'run', forbidden)
    monkeypatch.setattr(
        replay_service.HistoricalReplayService,
        'run_with_specification',
        forbidden,
    )
    monkeypatch.setattr(
        replay_service.HistoricalReplayService,
        'run_execution',
        forbidden,
    )
    monkeypatch.setattr(
        artifact_file,
        'load_historical_replay_artifact',
        forbidden,
    )

    comparison = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )
    assert comparison.compatibility.compatible


def test_existing_artifacts_and_result_serialization_are_not_modified() -> None:
    artifact = _artifact()
    artifact_payload = artifact.to_dict()
    result_payload = artifact.execution.result.to_dict()

    compare_historical_replay_artifacts(
        artifact,
        artifact,
        software_revision=_COMPARISON_SOFTWARE,
    )

    assert artifact.to_dict() == artifact_payload
    assert artifact.execution.result.to_dict() == result_payload


def test_compatibility_constructor_requires_canonical_reasons() -> None:
    compatible = compare_historical_replay_artifacts(
        _artifact(),
        _artifact(),
        software_revision=_COMPARISON_SOFTWARE,
    ).compatibility
    with pytest.raises(ValueError, match='reasons'):
        replace(
            compatible,
            reasons=(
                HistoricalReplayComparisonIncompatibilityReason.SYMBOL_MISMATCH,
            ),
        )

    incompatible = compare_historical_replay_artifacts(
        _artifact(),
        _artifact(symbol='AAPL', interval='daily'),
        software_revision=_COMPARISON_SOFTWARE,
    ).compatibility
    with pytest.raises(ValueError, match='reasons'):
        replace(incompatible, reasons=())
    with pytest.raises(ValueError, match='unique and ordered'):
        replace(
            incompatible,
            reasons=(incompatible.reasons[0], incompatible.reasons[0]),
        )


def test_summary_constructor_rejects_contradictory_denominators() -> None:
    comparison = compare_historical_replay_artifacts(
        _artifact(),
        _artifact(),
        software_revision=_COMPARISON_SOFTWARE,
    )
    summary = comparison.summary
    assert summary is not None
    with pytest.raises(ValueError, match='aligned steps'):
        replace(summary, state_semantic_change_count=3)
    with pytest.raises(ValueError, match='state field counts'):
        replace(
            summary,
            state_field_change_counts=(
                replace(summary.state_field_change_counts[0], name='unsupported'),
                *summary.state_field_change_counts[1:],
            ),
        )
    with pytest.raises(ValueError, match='unique keys'):
        replace(
            summary,
            strategy_members=(
                summary.strategy_members[0],
                summary.strategy_members[0],
            ),
            total_strategy_member_comparisons=4,
        )
    member = summary.strategy_members[0]
    invalid_distribution = (
        replace(
            member.baseline_status_distribution[0],
            count=member.baseline_status_distribution[0].count + 1,
        ),
        *member.baseline_status_distribution[1:],
    )
    with pytest.raises(ValueError, match='distribution total'):
        replace(
            summary,
            strategy_members=(
                replace(
                    member,
                    baseline_status_distribution=invalid_distribution,
                ),
            ),
        )
    with pytest.raises(ValueError, match='total strategy member'):
        replace(summary, total_strategy_member_comparisons=1)
    with pytest.raises(ValueError, match='added strategy'):
        replace(summary, added_strategy_member_count=1)


@pytest.mark.parametrize(
    'field_name',
    [
        'state_semantic_change_count',
        'state_provenance_change_count',
        'state_evaluation_evidence_change_count',
        'status_change_count',
        'rationale_change_count',
        'required_input_change_count',
        'missing_input_change_count',
        'evidence_change_count',
        'strategy_provenance_change_count',
        'identity_version_change_count',
        'configuration_fingerprint_change_count',
    ],
)
def test_result_rejects_each_detail_counter_mismatch(field_name: str) -> None:
    comparison = compare_historical_replay_artifacts(
        _artifact(),
        _artifact(rationale='Changed.'),
        software_revision=_COMPARISON_SOFTWARE,
    )
    summary = comparison.summary
    assert summary is not None
    replacement_value = 0 if getattr(summary, field_name) else 1
    invalid_summary = replace(
        summary,
        **{field_name: replacement_value},  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match=field_name):
        replace(comparison, summary=invalid_summary)


def test_result_rejects_inconsistent_changed_step_detail() -> None:
    comparison = compare_historical_replay_artifacts(
        _artifact(),
        _artifact(rationale='Changed.'),
        software_revision=_COMPARISON_SOFTWARE,
    )
    summary = comparison.summary
    assert summary is not None
    with pytest.raises(ValueError, match='strictly ordered'):
        replace(comparison, changed_steps=tuple(reversed(comparison.changed_steps)))

    shifted = replace(
        comparison.changed_steps[0],
        as_of=comparison.changed_steps[0].as_of + timedelta(hours=1),
    )
    with pytest.raises(ValueError, match='timestamp must be aligned'):
        replace(
            comparison,
            changed_steps=(shifted, *comparison.changed_steps[1:]),
        )

    invalid_bounds = replace(
        summary,
        first_differing_as_of=summary.last_differing_as_of,
    )
    with pytest.raises(ValueError, match='first differing'):
        replace(comparison, summary=invalid_bounds)

    difference = comparison.changed_steps[0].strategy_differences[0]
    with pytest.raises(ValueError, match='unique member keys'):
        replace(
            comparison.changed_steps[0],
            strategy_differences=(difference, difference),
        )


def test_experiment_rejects_fabricated_comparison_content() -> None:
    specification = HistoricalReplayExperimentSpecification(
        _artifact(),
        (_artifact(),),
        _COMPARISON_SOFTWARE,
    )
    experiment = create_historical_replay_experiment(specification)
    comparison = experiment.comparisons[0]
    fabricated = replace(
        comparison,
        execution_differences=(
            HistoricalReplayExecutionDifference(
                field='fabricated',
                baseline='baseline',
                candidate='candidate',
            ),
        ),
    )

    with pytest.raises(ValueError, match='canonical experiment result'):
        replace(experiment, comparisons=(fabricated,))
    with pytest.raises(ValueError, match='contiguous'):
        replace(
            experiment,
            comparisons=(replace(comparison, candidate_index=1),),
        )


def test_pairwise_fingerprint_is_intentionally_experiment_contextual() -> None:
    baseline = _artifact()
    candidate = _artifact(rationale='Changed.')
    pairwise = compare_historical_replay_artifacts(
        baseline,
        candidate,
        software_revision=_COMPARISON_SOFTWARE,
    )
    multi = create_historical_replay_experiment(
        HistoricalReplayExperimentSpecification(
            baseline,
            (candidate, _artifact(replay_revision='other')),
            _COMPARISON_SOFTWARE,
        )
    ).comparisons[0]

    assert pairwise.changed_steps == multi.changed_steps
    assert pairwise.summary == multi.summary
    assert pairwise.experiment_fingerprint != multi.experiment_fingerprint
    assert pairwise.comparison_fingerprint != multi.comparison_fingerprint
