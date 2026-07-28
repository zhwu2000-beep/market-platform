"""Synchronous composition service for historical Replay research."""

from __future__ import annotations

from market_platform.replay import (
    HistoricalReplayArtifact,
    HistoricalReplayExecution,
    HistoricalReplayExperimentSpecification,
    HistoricalReplayService,
    create_historical_replay_experiment,
)
from market_platform.research.historical_replay_workflow import (
    HistoricalReplayResearchMemberSpecification,
    HistoricalReplayResearchWorkflowCandidateResult,
    HistoricalReplayResearchWorkflowFailureCode,
    HistoricalReplayResearchWorkflowResult,
    HistoricalReplayResearchWorkflowSkipReason,
    HistoricalReplayResearchWorkflowSpecification,
    HistoricalReplayResearchWorkflowStepStatus,
    _validate_execution_correspondence,
    _validate_member_runtime_snapshot,
)
from market_platform.strategy import StrategyRunnerError

_CAPTURED_REPLAY_EXECUTION_ERRORS = (StrategyRunnerError,)


class HistoricalReplayResearchWorkflowService:
    """Compose Replay, Artifact, and Experiment domain operations."""

    def __init__(self, replay_service: HistoricalReplayService) -> None:
        if not isinstance(replay_service, HistoricalReplayService):
            raise TypeError("replay_service must be a HistoricalReplayService")
        self._replay_service = replay_service

    def run(
        self,
        specification: HistoricalReplayResearchWorkflowSpecification,
    ) -> HistoricalReplayResearchWorkflowResult:
        """Run one synchronous historical Replay research workflow."""

        if not isinstance(
            specification,
            HistoricalReplayResearchWorkflowSpecification,
        ):
            raise TypeError(
                "specification must be a "
                "HistoricalReplayResearchWorkflowSpecification"
            )

        baseline_execution = self._execute_member(
            specification,
            specification.baseline,
        )
        if baseline_execution is None:
            skipped_candidates = tuple(
                HistoricalReplayResearchWorkflowCandidateResult(
                    candidate_index=index,
                    member_specification_fingerprint=member.member_fingerprint,
                    replay_status=(
                        HistoricalReplayResearchWorkflowStepStatus.SKIPPED
                    ),
                    skip_reason=(
                        HistoricalReplayResearchWorkflowSkipReason.DEPENDENCY_FAILED
                    ),
                )
                for index, member in enumerate(specification.candidates)
            )
            return HistoricalReplayResearchWorkflowResult._create(
                specification=specification,
                baseline_artifact=None,
                baseline_failure_code=(
                    HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
                ),
                candidates=skipped_candidates,
                experiment=None,
            )

        baseline_artifact = HistoricalReplayArtifact.from_execution(
            baseline_execution
        )
        candidate_results: list[
            HistoricalReplayResearchWorkflowCandidateResult
        ] = []
        for index, member in enumerate(specification.candidates):
            execution = self._execute_member(specification, member)
            if execution is None:
                candidate_results.append(
                    HistoricalReplayResearchWorkflowCandidateResult(
                        candidate_index=index,
                        member_specification_fingerprint=member.member_fingerprint,
                        replay_status=(
                            HistoricalReplayResearchWorkflowStepStatus.FAILED
                        ),
                        failure_code=(
                            HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
                        ),
                    )
                )
                continue
            candidate_results.append(
                HistoricalReplayResearchWorkflowCandidateResult(
                    candidate_index=index,
                    member_specification_fingerprint=member.member_fingerprint,
                    replay_status=(
                        HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED
                    ),
                    artifact=HistoricalReplayArtifact.from_execution(execution),
                )
            )

        candidate_tuple = tuple(candidate_results)
        if not specification.candidates:
            return HistoricalReplayResearchWorkflowResult._create(
                specification=specification,
                baseline_artifact=baseline_artifact,
                baseline_failure_code=None,
                candidates=(),
                experiment=None,
            )
        if any(
            candidate.replay_status
            is HistoricalReplayResearchWorkflowStepStatus.FAILED
            for candidate in candidate_tuple
        ):
            return HistoricalReplayResearchWorkflowResult._create(
                specification=specification,
                baseline_artifact=baseline_artifact,
                baseline_failure_code=None,
                candidates=candidate_tuple,
                experiment=None,
            )

        candidate_artifacts = tuple(
            _required_candidate_artifact(candidate)
            for candidate in candidate_tuple
        )
        experiment_specification = HistoricalReplayExperimentSpecification(
            baseline=baseline_artifact,
            candidates=candidate_artifacts,
            software_revision=specification.comparison_software_revision,
        )
        experiment = create_historical_replay_experiment(
            experiment_specification
        )
        return HistoricalReplayResearchWorkflowResult._create(
            specification=specification,
            baseline_artifact=baseline_artifact,
            baseline_failure_code=None,
            candidates=candidate_tuple,
            experiment=experiment,
        )

    def _execute_member(
        self,
        workflow: HistoricalReplayResearchWorkflowSpecification,
        member: HistoricalReplayResearchMemberSpecification,
    ) -> HistoricalReplayExecution | None:
        _validate_member_runtime_snapshot(member)
        try:
            execution = self._replay_service.run_execution(
                workflow.source.to_dataframe(),
                member.replay_specification,
                strategies=member.strategies,
                state_model=member.state_model,
                software_revision=workflow.replay_software_revision,
                structure_derivation=member.structure_derivation,
                state_model_configuration_fingerprint=(
                    member.state_model_configuration_fingerprint
                ),
            )
        except _CAPTURED_REPLAY_EXECUTION_ERRORS:
            return None
        _validate_member_runtime_snapshot(member)
        _validate_execution_correspondence(workflow, member, execution)
        return execution


def _required_candidate_artifact(
    candidate: HistoricalReplayResearchWorkflowCandidateResult,
) -> HistoricalReplayArtifact:
    if candidate.artifact is None:
        raise ValueError("successful candidate result requires an Artifact")
    return candidate.artifact


__all__ = ["HistoricalReplayResearchWorkflowService"]
