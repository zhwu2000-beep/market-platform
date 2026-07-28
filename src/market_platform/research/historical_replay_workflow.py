"""Deterministic models for historical Replay research composition."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from market_platform._fingerprint import canonical_fingerprint
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.replay import (
    HistoricalReplayArtifact,
    HistoricalReplayExecution,
    HistoricalReplayExperiment,
    HistoricalReplaySpecification,
    ReplayStrategyIdentity,
    ReplayStructureDerivationIdentity,
    SoftwareRevision,
)
from market_platform.state import MarketStateModel
from market_platform.strategy import (
    StrategyCollection,
    StrategyInstance,
    get_strategy_provenance,
)

HISTORICAL_REPLAY_RESEARCH_MEMBER_SCHEMA_VERSION = (
    "historical_replay_research_workflow_member/v1"
)
HISTORICAL_REPLAY_RESEARCH_WORKFLOW_SCHEMA_VERSION = (
    "historical_replay_research_workflow/v1"
)
HISTORICAL_REPLAY_RESEARCH_WORKFLOW_POLICY_VERSION = (
    "historical_replay_research_workflow_policy/v1"
)
HISTORICAL_REPLAY_RESEARCH_WORKFLOW_RESULT_SCHEMA_VERSION = (
    "historical_replay_research_workflow_result/v1"
)

_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class HistoricalReplayResearchWorkflowStatus(StrEnum):
    """Terminal status of a historical Replay research workflow."""

    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"


class HistoricalReplayResearchWorkflowStepStatus(StrEnum):
    """Terminal status of one fixed historical workflow step."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class HistoricalReplayResearchWorkflowStepKind(StrEnum):
    """Kinds in the fixed historical workflow projection."""

    BASELINE_REPLAY = "baseline_replay"
    BASELINE_ARTIFACT = "baseline_artifact"
    CANDIDATE_REPLAY = "candidate_replay"
    CANDIDATE_ARTIFACT = "candidate_artifact"
    EXPERIMENT = "experiment"


class HistoricalReplayResearchWorkflowFailureCode(StrEnum):
    """Stable failure categories captured by the v1 workflow."""

    REPLAY_EXECUTION_FAILED = "replay_execution_failed"


class HistoricalReplayResearchWorkflowSkipReason(StrEnum):
    """Stable reasons why a dependent workflow step was not performed."""

    DEPENDENCY_FAILED = "dependency_failed"


@runtime_checkable
class HistoricalReplayResearchStateModelInstance(MarketStateModel, Protocol):
    """State model with complete re-derivable behavior identity.

    Implementers must include every behavior-affecting runtime parameter in
    ``configuration_fingerprint``. ``None`` is reserved for models whose stable
    id/version completely identify stateless behavior.
    """

    @property
    def configuration_fingerprint(self) -> str | None:
        """Return the current complete configuration identity, if any."""
        ...


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchMemberSpecification:
    """One executable Replay request with a captured semantic identity."""

    replay_specification: HistoricalReplaySpecification
    strategies: StrategyCollection = field(compare=False, hash=False, repr=False)
    state_model: HistoricalReplayResearchStateModelInstance = field(
        compare=False,
        hash=False,
        repr=False,
    )
    structure_derivation: ReplayStructureDerivationIdentity
    state_model_configuration_fingerprint: str | None = field(init=False)
    schema_version: str = field(
        init=False,
        default=HISTORICAL_REPLAY_RESEARCH_MEMBER_SCHEMA_VERSION,
    )
    state_model_id: str = field(init=False)
    state_model_version: str = field(init=False)
    strategy_identities: tuple[ReplayStrategyIdentity, ...] = field(init=False)
    member_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.replay_specification, HistoricalReplaySpecification):
            raise TypeError(
                "replay_specification must be a HistoricalReplaySpecification"
            )
        if not isinstance(self.strategies, StrategyCollection):
            raise TypeError("strategies must be a StrategyCollection")
        if not isinstance(
            self.state_model,
            HistoricalReplayResearchStateModelInstance,
        ):
            raise TypeError(
                "state_model must implement "
                "HistoricalReplayResearchStateModelInstance"
            )
        if not isinstance(
            self.structure_derivation,
            ReplayStructureDerivationIdentity,
        ):
            raise TypeError(
                "structure_derivation must be a ReplayStructureDerivationIdentity"
            )
        (
            state_model_id,
            state_model_version,
            state_configuration,
        ) = _state_model_identity(self.state_model)
        strategy_identities = _strategy_identities(self.strategies)
        object.__setattr__(
            self,
            "state_model_configuration_fingerprint",
            state_configuration,
        )
        object.__setattr__(self, "state_model_id", state_model_id)
        object.__setattr__(self, "state_model_version", state_model_version)
        object.__setattr__(self, "strategy_identities", strategy_identities)
        _validate_member_runtime_snapshot(self)
        object.__setattr__(
            self,
            "member_fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": HISTORICAL_REPLAY_RESEARCH_MEMBER_SCHEMA_VERSION,
            "replay_specification_fingerprint": (
                self.replay_specification.fingerprint
            ),
            "state_model": {
                "model_id": self.state_model_id,
                "model_version": self.state_model_version,
                "configuration_fingerprint": (
                    self.state_model_configuration_fingerprint
                ),
            },
            "structure_derivation": self.structure_derivation.to_dict(),
            "strategies": [
                identity.to_dict() for identity in self.strategy_identities
            ],
        }

    def to_dict(self) -> dict[str, object]:
        """Return the stable semantic member identity."""

        return {
            **self._fingerprint_payload(),
            "member_fingerprint": self.member_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchWorkflowSpecification:
    """One source, baseline, and ordered candidates for historical research."""

    source: HistoricalPriceSeries = field(compare=False, hash=False, repr=False)
    baseline: HistoricalReplayResearchMemberSpecification
    candidates: tuple[HistoricalReplayResearchMemberSpecification, ...]
    replay_software_revision: SoftwareRevision
    comparison_software_revision: SoftwareRevision
    workflow_software_revision: SoftwareRevision
    schema_version: str = field(
        init=False,
        default=HISTORICAL_REPLAY_RESEARCH_WORKFLOW_SCHEMA_VERSION,
    )
    policy_version: str = field(
        init=False,
        default=HISTORICAL_REPLAY_RESEARCH_WORKFLOW_POLICY_VERSION,
    )
    source_content_fingerprint: str = field(init=False)
    source_symbol: str = field(init=False)
    source_interval: str = field(init=False)
    source_provider: str = field(init=False)
    source_row_count: int = field(init=False)
    workflow_specification_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source, HistoricalPriceSeries):
            raise TypeError("source must be a HistoricalPriceSeries")
        if not isinstance(
            self.baseline,
            HistoricalReplayResearchMemberSpecification,
        ):
            raise TypeError(
                "baseline must be a HistoricalReplayResearchMemberSpecification"
            )
        if not isinstance(self.candidates, tuple):
            raise TypeError("candidates must be a tuple")
        for candidate in self.candidates:
            if not isinstance(
                candidate,
                HistoricalReplayResearchMemberSpecification,
            ):
                raise TypeError(
                    "candidates elements must be "
                    "HistoricalReplayResearchMemberSpecification"
                )
        for name, revision in (
            ("replay_software_revision", self.replay_software_revision),
            ("comparison_software_revision", self.comparison_software_revision),
            ("workflow_software_revision", self.workflow_software_revision),
        ):
            if not isinstance(revision, SoftwareRevision):
                raise TypeError(f"{name} must be a SoftwareRevision")

        source_symbol = self.source.symbol
        source_interval = self.baseline.replay_specification.interval
        members = (self.baseline, *self.candidates)
        for member in members:
            specification = member.replay_specification
            if specification.symbol != source_symbol:
                raise ValueError(
                    "member Replay specifications must match the source symbol"
                )
            if specification.interval != source_interval:
                raise ValueError(
                    "member Replay specifications must use one source interval"
                )

        object.__setattr__(
            self,
            "source_content_fingerprint",
            self.source.content_fingerprint,
        )
        object.__setattr__(self, "source_symbol", source_symbol)
        object.__setattr__(self, "source_interval", source_interval)
        object.__setattr__(self, "source_provider", self.source.provider)
        object.__setattr__(self, "source_row_count", len(self.source))
        object.__setattr__(
            self,
            "workflow_specification_fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": HISTORICAL_REPLAY_RESEARCH_WORKFLOW_SCHEMA_VERSION,
            "policy": _workflow_policy_payload(),
            "source": {
                "content_fingerprint": self.source_content_fingerprint,
                "symbol": self.source_symbol,
                "interval": self.source_interval,
                "provider": self.source_provider,
                "row_count": self.source_row_count,
            },
            "baseline_member_fingerprint": self.baseline.member_fingerprint,
            "candidates": [
                {
                    "candidate_index": index,
                    "member_fingerprint": candidate.member_fingerprint,
                }
                for index, candidate in enumerate(self.candidates)
            ],
            "replay_software_revision": self.replay_software_revision.to_dict(),
            "comparison_software_revision": (
                self.comparison_software_revision.to_dict()
            ),
            "workflow_software_revision": self.workflow_software_revision.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic workflow request identity."""

        return {
            **self._fingerprint_payload(),
            "source_row_count": self.source_row_count,
            "workflow_specification_fingerprint": (
                self.workflow_specification_fingerprint
            ),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchWorkflowCandidateResult:
    """Terminal result for one requested candidate position."""

    candidate_index: int
    member_specification_fingerprint: str
    replay_status: HistoricalReplayResearchWorkflowStepStatus
    artifact: HistoricalReplayArtifact | None = None
    failure_code: HistoricalReplayResearchWorkflowFailureCode | None = None
    skip_reason: HistoricalReplayResearchWorkflowSkipReason | None = None

    def __post_init__(self) -> None:
        candidate_index = _normalize_nonnegative_int(
            self.candidate_index,
            "candidate_index",
        )
        member_fingerprint = _normalize_fingerprint(
            self.member_specification_fingerprint,
            "member_specification_fingerprint",
        )
        if not isinstance(
            self.replay_status,
            HistoricalReplayResearchWorkflowStepStatus,
        ):
            raise TypeError(
                "replay_status must be a HistoricalReplayResearchWorkflowStepStatus"
            )
        if self.artifact is not None and not isinstance(
            self.artifact,
            HistoricalReplayArtifact,
        ):
            raise TypeError("artifact must be a HistoricalReplayArtifact or None")
        _validate_candidate_terminal_fields(self)
        object.__setattr__(self, "candidate_index", candidate_index)
        object.__setattr__(
            self,
            "member_specification_fingerprint",
            member_fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        """Return stable candidate status and output identities."""

        return {
            "candidate_index": self.candidate_index,
            "member_specification_fingerprint": (
                self.member_specification_fingerprint
            ),
            "replay_status": self.replay_status.value,
            "run_fingerprint": (
                self.artifact.execution.run_fingerprint
                if self.artifact is not None
                else None
            ),
            "result_fingerprint": (
                self.artifact.result_fingerprint
                if self.artifact is not None
                else None
            ),
            "failure_code": (
                self.failure_code.value if self.failure_code is not None else None
            ),
            "skip_reason": (
                self.skip_reason.value if self.skip_reason is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResearchWorkflowStepResult:
    """One terminal step in the fixed workflow projection."""

    kind: HistoricalReplayResearchWorkflowStepKind
    status: HistoricalReplayResearchWorkflowStepStatus
    candidate_index: int | None = None
    run_fingerprint: str | None = None
    result_fingerprint: str | None = None
    experiment_fingerprint: str | None = None
    comparison_fingerprints: tuple[str, ...] = ()
    failure_code: HistoricalReplayResearchWorkflowFailureCode | None = None
    skip_reason: HistoricalReplayResearchWorkflowSkipReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, HistoricalReplayResearchWorkflowStepKind):
            raise TypeError(
                "kind must be a HistoricalReplayResearchWorkflowStepKind"
            )
        if not isinstance(
            self.status,
            HistoricalReplayResearchWorkflowStepStatus,
        ):
            raise TypeError(
                "status must be a HistoricalReplayResearchWorkflowStepStatus"
            )
        candidate_index = self.candidate_index
        if self.kind in (
            HistoricalReplayResearchWorkflowStepKind.CANDIDATE_REPLAY,
            HistoricalReplayResearchWorkflowStepKind.CANDIDATE_ARTIFACT,
        ):
            if candidate_index is None:
                raise ValueError("candidate steps require a candidate_index")
            candidate_index = _normalize_nonnegative_int(
                candidate_index,
                "candidate_index",
            )
        elif candidate_index is not None:
            raise ValueError("baseline and experiment steps forbid candidate_index")

        run_fingerprint = _normalize_optional_fingerprint(
            self.run_fingerprint,
            "run_fingerprint",
        )
        result_fingerprint = _normalize_optional_fingerprint(
            self.result_fingerprint,
            "result_fingerprint",
        )
        experiment_fingerprint = _normalize_optional_fingerprint(
            self.experiment_fingerprint,
            "experiment_fingerprint",
        )
        comparisons = _fingerprint_tuple(
            self.comparison_fingerprints,
            "comparison_fingerprints",
        )
        object.__setattr__(self, "candidate_index", candidate_index)
        object.__setattr__(self, "run_fingerprint", run_fingerprint)
        object.__setattr__(self, "result_fingerprint", result_fingerprint)
        object.__setattr__(
            self,
            "experiment_fingerprint",
            experiment_fingerprint,
        )
        object.__setattr__(self, "comparison_fingerprints", comparisons)
        _validate_step_terminal_fields(self)

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic step projection."""

        return {
            "kind": self.kind.value,
            "candidate_index": self.candidate_index,
            "status": self.status.value,
            "run_fingerprint": self.run_fingerprint,
            "result_fingerprint": self.result_fingerprint,
            "experiment_fingerprint": self.experiment_fingerprint,
            "comparison_fingerprints": list(self.comparison_fingerprints),
            "failure_code": (
                self.failure_code.value if self.failure_code is not None else None
            ),
            "skip_reason": (
                self.skip_reason.value if self.skip_reason is not None else None
            ),
        }


@dataclass(frozen=True, slots=True, init=False)
class HistoricalReplayResearchWorkflowResult:
    """Immutable canonical terminal outcome of one historical workflow."""

    specification: HistoricalReplayResearchWorkflowSpecification
    baseline_artifact: HistoricalReplayArtifact | None
    baseline_failure_code: (
        HistoricalReplayResearchWorkflowFailureCode | None
    )
    candidates: tuple[HistoricalReplayResearchWorkflowCandidateResult, ...]
    experiment: HistoricalReplayExperiment | None
    status: HistoricalReplayResearchWorkflowStatus
    steps: tuple[HistoricalReplayResearchWorkflowStepResult, ...]
    schema_version: str
    workflow_result_fingerprint: str

    def __init__(self) -> None:
        raise TypeError(
            "HistoricalReplayResearchWorkflowResult is created by "
            "HistoricalReplayResearchWorkflowService.run()"
        )

    @classmethod
    def _create(
        cls,
        *,
        specification: HistoricalReplayResearchWorkflowSpecification,
        baseline_artifact: HistoricalReplayArtifact | None,
        baseline_failure_code: (
            HistoricalReplayResearchWorkflowFailureCode | None
        ),
        candidates: tuple[
            HistoricalReplayResearchWorkflowCandidateResult,
            ...,
        ],
        experiment: HistoricalReplayExperiment | None,
    ) -> HistoricalReplayResearchWorkflowResult:
        if not isinstance(
            specification,
            HistoricalReplayResearchWorkflowSpecification,
        ):
            raise TypeError(
                "specification must be a "
                "HistoricalReplayResearchWorkflowSpecification"
            )
        if baseline_artifact is not None and not isinstance(
            baseline_artifact,
            HistoricalReplayArtifact,
        ):
            raise TypeError(
                "baseline_artifact must be a HistoricalReplayArtifact or None"
            )
        if baseline_failure_code is not None and not isinstance(
            baseline_failure_code,
            HistoricalReplayResearchWorkflowFailureCode,
        ):
            raise TypeError(
                "baseline_failure_code must be a workflow failure code or None"
            )
        normalized_candidates = _candidate_result_tuple(candidates)
        if experiment is not None and not isinstance(
            experiment,
            HistoricalReplayExperiment,
        ):
            raise TypeError(
                "experiment must be a HistoricalReplayExperiment or None"
            )

        _validate_workflow_membership(
            specification,
            baseline_artifact=baseline_artifact,
            baseline_failure_code=baseline_failure_code,
            candidates=normalized_candidates,
            experiment=experiment,
        )
        status = _derive_workflow_status(
            baseline_artifact=baseline_artifact,
            candidates=normalized_candidates,
        )
        steps = _derive_workflow_steps(
            specification,
            baseline_artifact=baseline_artifact,
            baseline_failure_code=baseline_failure_code,
            candidates=normalized_candidates,
            experiment=experiment,
        )

        instance = cls.__new__(cls)
        object.__setattr__(instance, "specification", specification)
        object.__setattr__(instance, "baseline_artifact", baseline_artifact)
        object.__setattr__(
            instance,
            "baseline_failure_code",
            baseline_failure_code,
        )
        object.__setattr__(instance, "candidates", normalized_candidates)
        object.__setattr__(instance, "experiment", experiment)
        object.__setattr__(instance, "status", status)
        object.__setattr__(instance, "steps", steps)
        object.__setattr__(
            instance,
            "schema_version",
            HISTORICAL_REPLAY_RESEARCH_WORKFLOW_RESULT_SCHEMA_VERSION,
        )
        object.__setattr__(
            instance,
            "workflow_result_fingerprint",
            canonical_fingerprint(instance._fingerprint_payload()),
        )
        return instance

    def _fingerprint_payload(self) -> dict[str, object]:
        baseline_identity: dict[str, str] | None = None
        if self.baseline_artifact is not None:
            baseline_identity = _artifact_identity(self.baseline_artifact)
        experiment_payload: dict[str, object] | None = None
        if self.experiment is not None:
            experiment_payload = {
                "experiment_fingerprint": (
                    self.experiment.specification.experiment_fingerprint
                ),
                "comparison_fingerprints": [
                    comparison.comparison_fingerprint
                    for comparison in self.experiment.comparisons
                ],
            }
        return {
            "schema_version": (
                HISTORICAL_REPLAY_RESEARCH_WORKFLOW_RESULT_SCHEMA_VERSION
            ),
            "workflow_specification_fingerprint": (
                self.specification.workflow_specification_fingerprint
            ),
            "status": self.status.value,
            "steps": [step.to_dict() for step in self.steps],
            "baseline": {
                "artifact": baseline_identity,
                "failure_code": (
                    self.baseline_failure_code.value
                    if self.baseline_failure_code is not None
                    else None
                ),
            },
            "candidates": [
                candidate.to_dict() for candidate in self.candidates
            ],
            "experiment": experiment_payload,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the terminal semantic identity without serializing members."""

        return {
            **self._fingerprint_payload(),
            "workflow_result_fingerprint": self.workflow_result_fingerprint,
        }


def _workflow_policy_payload() -> dict[str, object]:
    return {
        "schema_version": HISTORICAL_REPLAY_RESEARCH_WORKFLOW_POLICY_VERSION,
        "baseline_required": True,
        "candidate_cardinality": "zero_or_more",
        "candidate_order": "position_sensitive",
        "duplicate_candidates": "permitted",
        "baseline_failure": "skip_all_dependents",
        "candidate_failure": "continue_independent_candidates",
        "reduced_experiment": "forbidden",
        "experiment_creation": "all_requested_candidates_succeeded",
        "execution": "synchronous",
        "retries": False,
        "parallel_execution": False,
    }


def _strategy_identities(
    strategies: StrategyCollection,
) -> tuple[ReplayStrategyIdentity, ...]:
    identities: list[ReplayStrategyIdentity] = []
    for strategy in strategies.strategies:
        if not isinstance(strategy, StrategyInstance):
            raise TypeError(
                "historical Replay research workflow strategies must "
                "implement StrategyInstance"
            )
        provenance = get_strategy_provenance(strategy)
        identities.append(
            ReplayStrategyIdentity(
                strategy_id=provenance.strategy_id,
                strategy_version=provenance.strategy_version,
                configuration_fingerprint=provenance.configuration_fingerprint,
            )
        )
    return tuple(identities)


def _state_model_identity(
    state_model: HistoricalReplayResearchStateModelInstance,
) -> tuple[str, str, str | None]:
    if not isinstance(
        state_model,
        HistoricalReplayResearchStateModelInstance,
    ):
        raise TypeError(
            "state_model must implement "
            "HistoricalReplayResearchStateModelInstance"
        )
    return (
        _normalize_required_text(
            state_model.model_id,
            "state_model.model_id",
        ),
        _normalize_required_text(
            state_model.model_version,
            "state_model.model_version",
        ),
        _normalize_optional_fingerprint(
            state_model.configuration_fingerprint,
            "state_model.configuration_fingerprint",
        ),
    )


def _validate_member_runtime_snapshot(
    member: HistoricalReplayResearchMemberSpecification,
) -> None:
    state_identity = _state_model_identity(member.state_model)
    expected_state_identity = (
        member.state_model_id,
        member.state_model_version,
        member.state_model_configuration_fingerprint,
    )
    if state_identity != expected_state_identity:
        raise ValueError(
            "state model executable identity no longer matches "
            "the member specification"
        )
    if _strategy_identities(member.strategies) != member.strategy_identities:
        raise ValueError(
            "strategy collection executable identity no longer matches "
            "the member specification"
        )


def _validate_candidate_terminal_fields(
    candidate: HistoricalReplayResearchWorkflowCandidateResult,
) -> None:
    if candidate.replay_status is HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED:
        if candidate.artifact is None:
            raise ValueError("successful candidate requires an Artifact")
        if candidate.failure_code is not None or candidate.skip_reason is not None:
            raise ValueError("successful candidate forbids failure and skip fields")
        return
    if candidate.replay_status is HistoricalReplayResearchWorkflowStepStatus.FAILED:
        if candidate.artifact is not None:
            raise ValueError("failed candidate forbids an Artifact")
        if (
            candidate.failure_code
            is not HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
        ):
            raise ValueError(
                "failed candidate requires replay_execution_failed"
            )
        if candidate.skip_reason is not None:
            raise ValueError("failed candidate forbids a skip reason")
        return
    if candidate.artifact is not None or candidate.failure_code is not None:
        raise ValueError("skipped candidate forbids Artifact and failure code")
    if (
        candidate.skip_reason
        is not HistoricalReplayResearchWorkflowSkipReason.DEPENDENCY_FAILED
    ):
        raise ValueError("skipped candidate requires dependency_failed")


def _validate_step_terminal_fields(
    step: HistoricalReplayResearchWorkflowStepResult,
) -> None:
    replay_kind = step.kind in (
        HistoricalReplayResearchWorkflowStepKind.BASELINE_REPLAY,
        HistoricalReplayResearchWorkflowStepKind.CANDIDATE_REPLAY,
    )
    artifact_kind = step.kind in (
        HistoricalReplayResearchWorkflowStepKind.BASELINE_ARTIFACT,
        HistoricalReplayResearchWorkflowStepKind.CANDIDATE_ARTIFACT,
    )
    has_run_identity = (
        step.run_fingerprint is not None and step.result_fingerprint is not None
    )
    has_any_output = (
        step.run_fingerprint is not None
        or step.result_fingerprint is not None
        or step.experiment_fingerprint is not None
        or bool(step.comparison_fingerprints)
    )
    if (step.run_fingerprint is None) != (step.result_fingerprint is None):
        raise ValueError("run and result fingerprints must be present together")

    if step.status is HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED:
        if step.failure_code is not None or step.skip_reason is not None:
            raise ValueError("successful step forbids failure and skip fields")
        if replay_kind or artifact_kind:
            if not has_run_identity:
                raise ValueError("successful member step requires run/result identity")
            if (
                step.experiment_fingerprint is not None
                or step.comparison_fingerprints
            ):
                raise ValueError("member step forbids experiment identities")
        else:
            if step.experiment_fingerprint is None:
                raise ValueError(
                    "successful experiment step requires experiment identity"
                )
            if not step.comparison_fingerprints:
                raise ValueError(
                    "successful experiment step requires comparison identities"
                )
            if has_run_identity:
                raise ValueError("experiment step forbids run/result identities")
        return

    if step.status is HistoricalReplayResearchWorkflowStepStatus.FAILED:
        if not replay_kind:
            raise ValueError("only Replay steps may fail in workflow v1")
        if has_any_output or step.skip_reason is not None:
            raise ValueError("failed step forbids outputs and skip reason")
        if (
            step.failure_code
            is not HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
        ):
            raise ValueError("failed Replay step requires replay_execution_failed")
        return

    if has_any_output or step.failure_code is not None:
        raise ValueError("skipped step forbids output and failure identities")
    if (
        step.skip_reason
        is not HistoricalReplayResearchWorkflowSkipReason.DEPENDENCY_FAILED
    ):
        raise ValueError("skipped step requires dependency_failed")


def _candidate_result_tuple(
    value: object,
) -> tuple[HistoricalReplayResearchWorkflowCandidateResult, ...]:
    if not isinstance(value, tuple):
        raise TypeError("candidates must be a tuple")
    for candidate in value:
        if not isinstance(
            candidate,
            HistoricalReplayResearchWorkflowCandidateResult,
        ):
            raise TypeError(
                "candidates elements must be "
                "HistoricalReplayResearchWorkflowCandidateResult"
            )
    return value


def _validate_workflow_membership(
    specification: HistoricalReplayResearchWorkflowSpecification,
    *,
    baseline_artifact: HistoricalReplayArtifact | None,
    baseline_failure_code: HistoricalReplayResearchWorkflowFailureCode | None,
    candidates: tuple[HistoricalReplayResearchWorkflowCandidateResult, ...],
    experiment: HistoricalReplayExperiment | None,
) -> None:
    if len(candidates) != len(specification.candidates):
        raise ValueError("candidate results must cover every requested candidate")
    for index, (candidate, member) in enumerate(
        zip(candidates, specification.candidates, strict=True)
    ):
        if candidate.candidate_index != index:
            raise ValueError("candidate result indices must be contiguous and ordered")
        if candidate.member_specification_fingerprint != member.member_fingerprint:
            raise ValueError("candidate result belongs to another member")

    if baseline_artifact is None:
        if (
            baseline_failure_code
            is not HistoricalReplayResearchWorkflowFailureCode.REPLAY_EXECUTION_FAILED
        ):
            raise ValueError("missing baseline requires replay_execution_failed")
        if any(
            candidate.replay_status
            is not HistoricalReplayResearchWorkflowStepStatus.SKIPPED
            for candidate in candidates
        ):
            raise ValueError("baseline failure requires all candidates skipped")
        if experiment is not None:
            raise ValueError("baseline failure forbids an Experiment")
        return

    if baseline_failure_code is not None:
        raise ValueError("successful baseline forbids a failure code")
    _validate_artifact_correspondence(
        specification,
        specification.baseline,
        baseline_artifact,
    )
    if any(
        candidate.replay_status
        is HistoricalReplayResearchWorkflowStepStatus.SKIPPED
        for candidate in candidates
    ):
        raise ValueError("successful baseline forbids skipped candidates")
    for candidate, member in zip(
        candidates,
        specification.candidates,
        strict=True,
    ):
        if candidate.artifact is not None:
            _validate_artifact_correspondence(
                specification,
                member,
                candidate.artifact,
            )

    all_succeeded = all(
        candidate.replay_status
        is HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED
        for candidate in candidates
    )
    if not candidates:
        if experiment is not None:
            raise ValueError("Replay-only workflow forbids an Experiment")
        return
    if all_succeeded:
        if experiment is None:
            raise ValueError("complete candidate success requires an Experiment")
        expected_artifacts = tuple(
            candidate.artifact for candidate in candidates
        )
        if any(artifact is None for artifact in expected_artifacts):
            raise ValueError("successful candidates require Artifacts")
        if experiment.specification.baseline is not baseline_artifact:
            raise ValueError("Experiment must own the exact baseline Artifact")
        if any(
            actual is not expected
            for actual, expected in zip(
                experiment.specification.candidates,
                expected_artifacts,
                strict=True,
            )
        ):
            raise ValueError("Experiment candidate Artifact order is inconsistent")
        if (
            experiment.specification.software_revision
            != specification.comparison_software_revision
        ):
            raise ValueError("Experiment comparison revision is inconsistent")
    elif experiment is not None:
        raise ValueError("candidate failure forbids a reduced Experiment")


def _validate_artifact_correspondence(
    workflow: HistoricalReplayResearchWorkflowSpecification,
    member: HistoricalReplayResearchMemberSpecification,
    artifact: HistoricalReplayArtifact,
) -> None:
    execution = artifact.execution
    _validate_execution_correspondence(workflow, member, execution)


def _validate_execution_correspondence(
    workflow: HistoricalReplayResearchWorkflowSpecification,
    member: HistoricalReplayResearchMemberSpecification,
    execution: HistoricalReplayExecution,
) -> None:
    if not isinstance(execution, HistoricalReplayExecution):
        raise TypeError("execution must be a HistoricalReplayExecution")
    provenance = execution.provenance
    expected_series = _member_context_series(workflow.source, member)
    specification = member.replay_specification
    if provenance.specification != specification:
        raise ValueError("Artifact Replay specification does not match member")
    if provenance.specification_fingerprint != specification.fingerprint:
        raise ValueError("Artifact specification fingerprint does not match member")
    if provenance.dataset_content_fingerprint != expected_series.content_fingerprint:
        raise ValueError("Artifact dataset fingerprint does not match source context")
    if provenance.provider != workflow.source_provider:
        raise ValueError("Artifact provider does not match workflow source")
    if provenance.context_start != expected_series.timestamp_at(0):
        raise ValueError("Artifact context start does not match source context")
    if provenance.context_end != expected_series.as_of:
        raise ValueError("Artifact context end does not match source context")
    if provenance.context_row_count != len(expected_series):
        raise ValueError("Artifact context row count does not match source context")
    if provenance.software_revision != workflow.replay_software_revision:
        raise ValueError("Artifact Replay software revision does not match workflow")
    if provenance.structure_derivation != member.structure_derivation:
        raise ValueError("Artifact structure identity does not match member")
    if provenance.state_model_id != member.state_model_id:
        raise ValueError("Artifact state-model id does not match member")
    if provenance.state_model_version != member.state_model_version:
        raise ValueError("Artifact state-model version does not match member")
    if (
        provenance.state_model_configuration_fingerprint
        != member.state_model_configuration_fingerprint
    ):
        raise ValueError("Artifact state-model configuration does not match member")
    if provenance.strategies != member.strategy_identities:
        raise ValueError("Artifact strategy identities do not match member")
    if execution.result.symbol != workflow.source_symbol:
        raise ValueError("Artifact result symbol does not match source")
    if execution.result.interval != workflow.source_interval:
        raise ValueError("Artifact result interval does not match source")


def _member_context_series(
    source: HistoricalPriceSeries,
    member: HistoricalReplayResearchMemberSpecification,
) -> HistoricalPriceSeries:
    specification = member.replay_specification
    frame = source.to_dataframe()
    retained = frame.loc[
        (frame["timestamp"] >= specification.context_start)
        & (frame["timestamp"] <= specification.evaluation_end)
    ].reset_index(drop=True)
    if retained.empty:
        raise ValueError("member Replay context does not contain source rows")
    return HistoricalPriceSeries(
        retained,
        symbol=source.symbol,
        provider=source.provider,
    )


def _derive_workflow_status(
    *,
    baseline_artifact: HistoricalReplayArtifact | None,
    candidates: tuple[HistoricalReplayResearchWorkflowCandidateResult, ...],
) -> HistoricalReplayResearchWorkflowStatus:
    if baseline_artifact is None:
        return HistoricalReplayResearchWorkflowStatus.FAILED
    if any(
        candidate.replay_status
        is HistoricalReplayResearchWorkflowStepStatus.FAILED
        for candidate in candidates
    ):
        return HistoricalReplayResearchWorkflowStatus.PARTIALLY_SUCCEEDED
    return HistoricalReplayResearchWorkflowStatus.SUCCEEDED


def _derive_workflow_steps(
    specification: HistoricalReplayResearchWorkflowSpecification,
    *,
    baseline_artifact: HistoricalReplayArtifact | None,
    baseline_failure_code: HistoricalReplayResearchWorkflowFailureCode | None,
    candidates: tuple[HistoricalReplayResearchWorkflowCandidateResult, ...],
    experiment: HistoricalReplayExperiment | None,
) -> tuple[HistoricalReplayResearchWorkflowStepResult, ...]:
    steps: list[HistoricalReplayResearchWorkflowStepResult] = []
    if baseline_artifact is None:
        steps.append(
            _failed_replay_step(
                HistoricalReplayResearchWorkflowStepKind.BASELINE_REPLAY,
                failure_code=baseline_failure_code,
            )
        )
        steps.append(
            _skipped_step(
                HistoricalReplayResearchWorkflowStepKind.BASELINE_ARTIFACT
            )
        )
    else:
        steps.extend(
            _successful_member_steps(
                HistoricalReplayResearchWorkflowStepKind.BASELINE_REPLAY,
                HistoricalReplayResearchWorkflowStepKind.BASELINE_ARTIFACT,
                baseline_artifact,
            )
        )

    for candidate in candidates:
        if (
            candidate.replay_status
            is HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED
        ):
            if candidate.artifact is None:
                raise ValueError("successful candidate requires an Artifact")
            steps.extend(
                _successful_member_steps(
                    HistoricalReplayResearchWorkflowStepKind.CANDIDATE_REPLAY,
                    HistoricalReplayResearchWorkflowStepKind.CANDIDATE_ARTIFACT,
                    candidate.artifact,
                    candidate_index=candidate.candidate_index,
                )
            )
        elif (
            candidate.replay_status
            is HistoricalReplayResearchWorkflowStepStatus.FAILED
        ):
            steps.append(
                _failed_replay_step(
                    HistoricalReplayResearchWorkflowStepKind.CANDIDATE_REPLAY,
                    candidate_index=candidate.candidate_index,
                    failure_code=candidate.failure_code,
                )
            )
            steps.append(
                _skipped_step(
                    HistoricalReplayResearchWorkflowStepKind.CANDIDATE_ARTIFACT,
                    candidate_index=candidate.candidate_index,
                )
            )
        else:
            steps.append(
                _skipped_step(
                    HistoricalReplayResearchWorkflowStepKind.CANDIDATE_REPLAY,
                    candidate_index=candidate.candidate_index,
                )
            )
            steps.append(
                _skipped_step(
                    HistoricalReplayResearchWorkflowStepKind.CANDIDATE_ARTIFACT,
                    candidate_index=candidate.candidate_index,
                )
            )

    if specification.candidates:
        if experiment is None:
            steps.append(
                _skipped_step(
                    HistoricalReplayResearchWorkflowStepKind.EXPERIMENT
                )
            )
        else:
            steps.append(
                HistoricalReplayResearchWorkflowStepResult(
                    kind=HistoricalReplayResearchWorkflowStepKind.EXPERIMENT,
                    status=HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED,
                    experiment_fingerprint=(
                        experiment.specification.experiment_fingerprint
                    ),
                    comparison_fingerprints=tuple(
                        comparison.comparison_fingerprint
                        for comparison in experiment.comparisons
                    ),
                )
            )
    return tuple(steps)


def _successful_member_steps(
    replay_kind: HistoricalReplayResearchWorkflowStepKind,
    artifact_kind: HistoricalReplayResearchWorkflowStepKind,
    artifact: HistoricalReplayArtifact,
    *,
    candidate_index: int | None = None,
) -> tuple[HistoricalReplayResearchWorkflowStepResult, ...]:
    identity = _artifact_identity(artifact)
    return (
        HistoricalReplayResearchWorkflowStepResult(
            kind=replay_kind,
            status=HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED,
            candidate_index=candidate_index,
            run_fingerprint=identity["run_fingerprint"],
            result_fingerprint=identity["result_fingerprint"],
        ),
        HistoricalReplayResearchWorkflowStepResult(
            kind=artifact_kind,
            status=HistoricalReplayResearchWorkflowStepStatus.SUCCEEDED,
            candidate_index=candidate_index,
            run_fingerprint=identity["run_fingerprint"],
            result_fingerprint=identity["result_fingerprint"],
        ),
    )


def _failed_replay_step(
    kind: HistoricalReplayResearchWorkflowStepKind,
    *,
    failure_code: HistoricalReplayResearchWorkflowFailureCode | None,
    candidate_index: int | None = None,
) -> HistoricalReplayResearchWorkflowStepResult:
    return HistoricalReplayResearchWorkflowStepResult(
        kind=kind,
        status=HistoricalReplayResearchWorkflowStepStatus.FAILED,
        candidate_index=candidate_index,
        failure_code=failure_code,
    )


def _skipped_step(
    kind: HistoricalReplayResearchWorkflowStepKind,
    *,
    candidate_index: int | None = None,
) -> HistoricalReplayResearchWorkflowStepResult:
    return HistoricalReplayResearchWorkflowStepResult(
        kind=kind,
        status=HistoricalReplayResearchWorkflowStepStatus.SKIPPED,
        candidate_index=candidate_index,
        skip_reason=HistoricalReplayResearchWorkflowSkipReason.DEPENDENCY_FAILED,
    )


def _artifact_identity(
    artifact: HistoricalReplayArtifact,
) -> dict[str, str]:
    return {
        "run_fingerprint": artifact.execution.run_fingerprint,
        "result_fingerprint": artifact.result_fingerprint,
    }


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_fingerprint(value: object, field_name: str) -> str:
    normalized = _normalize_required_text(value, field_name)
    if _FINGERPRINT_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a sha256 fingerprint")
    return normalized


def _normalize_optional_fingerprint(
    value: object,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _normalize_fingerprint(value, field_name)


def _normalize_nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _fingerprint_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    return tuple(
        _normalize_fingerprint(item, f"{field_name} item") for item in value
    )


__all__ = [
    "HISTORICAL_REPLAY_RESEARCH_MEMBER_SCHEMA_VERSION",
    "HISTORICAL_REPLAY_RESEARCH_WORKFLOW_POLICY_VERSION",
    "HISTORICAL_REPLAY_RESEARCH_WORKFLOW_RESULT_SCHEMA_VERSION",
    "HISTORICAL_REPLAY_RESEARCH_WORKFLOW_SCHEMA_VERSION",
    "HistoricalReplayResearchMemberSpecification",
    "HistoricalReplayResearchStateModelInstance",
    "HistoricalReplayResearchWorkflowCandidateResult",
    "HistoricalReplayResearchWorkflowFailureCode",
    "HistoricalReplayResearchWorkflowResult",
    "HistoricalReplayResearchWorkflowSkipReason",
    "HistoricalReplayResearchWorkflowSpecification",
    "HistoricalReplayResearchWorkflowStatus",
    "HistoricalReplayResearchWorkflowStepKind",
    "HistoricalReplayResearchWorkflowStepResult",
    "HistoricalReplayResearchWorkflowStepStatus",
]
