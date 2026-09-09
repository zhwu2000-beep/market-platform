"""Trusted production freshness execution for Polygon completed-daily Evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from threading import Lock
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.polygon_completed_daily_production_construction import (  # noqa: E501
    PolygonCompletedDailyConstructionHistoryError,
    PolygonCompletedDailyProductionConstructionApplicationService,
    PolygonCompletedDailyProductionConstructionResult,
)
from market_platform.application.polygon_completed_daily_production_governance import (
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE,
    _FreshnessRuleDefinition,
    _resolve_approved_polygon_completed_daily_production_profile,
)
from market_platform.evidence.models import EvidenceArtifact
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)
from market_platform.evidence.temporal import (
    EvidenceFreshnessEvaluationRecord,
    EvidenceFreshnessEvaluationReference,
    EvidenceFreshnessRule,
    create_evidence_freshness_evaluation_record,
)
from market_platform.evidence_ingress import (
    PolygonCompletedDailyOhlcvMaterial,
    PolygonCompletedDailyOhlcvMaterialRow,
)

_VERSION = "1.0.0"
_PACKAGE_VERSION = "0.1.0"
_SCHEMA = "polygon_completed_daily_freshness_execution/v1"
_OPERATION_SCHEMA = "polygon_completed_daily_freshness_operation/v1"
_EXECUTOR_SCHEMA = "market_platform_software_executor/v1"
_PROFILE_REFERENCE_NAMESPACE = "market_platform.production_governance_profile"
_EXECUTION_ID_PATTERN = re.compile(
    r"polygon_completed_daily_freshness:[0-9a-f]{32}", flags=re.ASCII
)
_CONSTRUCTION_EXECUTION_ID_PATTERN = re.compile(
    r"polygon_completed_daily_construction:[0-9a-f]{32}", flags=re.ASCII
)
_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_freshness_history:[0-9a-f]{32}", flags=re.ASCII
)
_CONSTRUCTION_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_construction_history:[0-9a-f]{32}", flags=re.ASCII
)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_MARKET_TIMEZONE_NAME = "America/New_York"
_MARKET_TIMEZONE = ZoneInfo(_MARKET_TIMEZONE_NAME)
_MINIMUM_LAG_DAYS = 1
_MAXIMUM_LAG_DAYS = 4
_COMPANION_SEAL = object()
_RESULT_SEAL = object()
_HISTORY_SEAL = object()

_PROFILE = _resolve_approved_polygon_completed_daily_production_profile(
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE
)
_ADMISSION_DEFINITION = _PROFILE.admission_freshness
_TASK_DEFINITION = _PROFILE.task_freshness
_PROFILE_REFERENCE = EvidenceIdentityReference(
    namespace=_PROFILE_REFERENCE_NAMESPACE,
    identity_id=_PROFILE.profile_id,
    identity_version=_PROFILE.profile_version,
    identity_fingerprint=_PROFILE.fingerprint,
)
_EXECUTOR = EvidenceIdentityReference(
    namespace="market_platform.software",
    identity_id="market_platform",
    identity_version=_PACKAGE_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _EXECUTOR_SCHEMA,
            "software_id": "market_platform",
            "software_version": _PACKAGE_VERSION,
        }
    ),
)


class PolygonCompletedDailyFreshnessExecutionKind(StrEnum):
    """Closed supported freshness execution contexts."""

    ADMISSION = "admission"
    DAILY_TECHNICAL = "daily_technical"


class PolygonCompletedDailyFreshnessOutcome(StrEnum):
    """Machine-readable result cause without lifecycle authority expansion."""

    FRESH = "fresh"
    STALE_CALENDAR_LAG = "stale_calendar_lag"
    NO_ELIGIBLE_RETAINED_COMPLETED_SESSION = "no_eligible_retained_completed_session"


class PolygonCompletedDailyFreshnessRefusalReason(StrEnum):
    """Stable local reasons why no trusted freshness result was published."""

    TRUSTED_CONSTRUCTION_UNAVAILABLE = "trusted_construction_unavailable"
    ARTIFACT_MATERIAL_MISMATCH = "artifact_material_mismatch"
    POLICY_RULE_MISMATCH = "policy_rule_mismatch"
    TEMPORAL_EXECUTION_FAILURE = "temporal_execution_failure"
    HISTORY_CONFLICT_OR_CORRUPTION = "history_conflict_or_corruption"


class PolygonCompletedDailyFreshnessExecutionRefused(RuntimeError):
    """The supported operation refused to mint trusted freshness history."""

    reason: PolygonCompletedDailyFreshnessRefusalReason

    def __init__(
        self,
        reason: PolygonCompletedDailyFreshnessRefusalReason,
        message: str,
    ) -> None:
        if type(reason) is not PolygonCompletedDailyFreshnessRefusalReason:
            raise TypeError("reason must be a freshness refusal reason")
        self.reason = reason
        super().__init__(message)


class PolygonCompletedDailyFreshnessHistoryError(RuntimeError):
    """Trusted freshness history is incomplete or internally inconsistent."""


class PolygonCompletedDailyFreshnessHistoryConflictError(
    PolygonCompletedDailyFreshnessHistoryError
):
    """Retained freshness facts conflict for an exact history query."""


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyAdmissionFreshnessRequest:
    """Permitted intent for the fixed admission-time freshness operation."""

    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            _copy_artifact_reference(self.artifact_reference),
        )
        object.__setattr__(
            self,
            "construction_execution_id",
            _construction_execution_id(self.construction_execution_id),
        )

    def _validate(self) -> None:
        _copy_artifact_reference(self.artifact_reference)
        _construction_execution_id(self.construction_execution_id)


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyTaskFreshnessRequest:
    """Permitted intent for one exact Daily Technical evaluation instant."""

    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str
    evaluation_as_of: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            _copy_artifact_reference(self.artifact_reference),
        )
        object.__setattr__(
            self,
            "construction_execution_id",
            _construction_execution_id(self.construction_execution_id),
        )
        object.__setattr__(
            self,
            "evaluation_as_of",
            _timestamp(self.evaluation_as_of, "evaluation_as_of"),
        )

    def _validate(self) -> None:
        _copy_artifact_reference(self.artifact_reference)
        _construction_execution_id(self.construction_execution_id)
        _require_canonical_timestamp(self.evaluation_as_of, "evaluation_as_of")


@dataclass(frozen=True, slots=True)
class _FreshnessSupport:
    new_york_evaluation_date: date
    retained_material_row_count: int
    first_retained_session_date: date | None
    latest_retained_session_date: date | None
    eligible_completed_session_count: int
    latest_eligible_completed_session_date: date | None
    calendar_lag_days: int | None
    outcome: PolygonCompletedDailyFreshnessOutcome
    result: bool


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyFreshnessExecutionCompanion:
    """Exact provenance for one authentic source-specific freshness execution."""

    execution_id: str
    history_sequence: int
    history_namespace_id: str
    execution_kind: PolygonCompletedDailyFreshnessExecutionKind
    operation: EvidenceIdentityReference
    executor: EvidenceIdentityReference
    production_profile_reference: EvidenceIdentityReference
    production_profile_fingerprint: str
    construction_history_namespace_id: str
    construction_history_sequence: int
    construction_execution_id: str
    construction_receipt_fingerprint: str
    artifact_reference: EvidenceArtifactReference
    material_fingerprint: str
    freshness_rule: EvidenceFreshnessRule
    freshness_definition_fingerprint: str
    governance_scope: str
    observation_period_start: datetime
    observation_period_end: datetime
    evaluation_as_of: datetime
    new_york_evaluation_date: date
    retained_material_row_count: int
    first_retained_session_date: date | None
    latest_retained_session_date: date | None
    eligible_completed_session_count: int
    latest_eligible_completed_session_date: date | None
    calendar_lag_days: int | None
    outcome: PolygonCompletedDailyFreshnessOutcome
    freshness_evaluation_reference: EvidenceFreshnessEvaluationReference
    result: bool
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyFreshnessExecutionCompanion is issued only by "
            "trusted production freshness history"
        )

    @classmethod
    def _create(
        cls,
        *,
        execution_id: str,
        history_sequence: int,
        history_namespace_id: str,
        execution_kind: PolygonCompletedDailyFreshnessExecutionKind,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        freshness_definition: _FreshnessRuleDefinition,
        freshness_record: EvidenceFreshnessEvaluationRecord,
        support: _FreshnessSupport,
        execution_started_at: datetime,
        execution_completed_at: datetime,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyFreshnessExecutionCompanion:
        if seal is not _COMPANION_SEAL:
            raise TypeError("freshness execution companion issuance is private")
        construction_result._validate()
        artifact = construction_result.artifact
        temporal = artifact.temporal_identity
        observation_start = temporal.observation_period_start
        observation_end = temporal.observation_period_end
        if observation_start is None or observation_end is None:
            raise ValueError("Candidate lacks its requested observation interval")
        companion = object.__new__(cls)
        values: dict[str, object] = {
            "execution_id": _execution_id(execution_id),
            "history_sequence": _positive_integer(history_sequence, "history_sequence"),
            "history_namespace_id": _history_namespace_id(history_namespace_id),
            "execution_kind": _execution_kind(execution_kind),
            "operation": _copy_identity_reference(_operation(execution_kind)),
            "executor": _copy_identity_reference(_EXECUTOR),
            "production_profile_reference": _copy_identity_reference(
                _PROFILE_REFERENCE
            ),
            "production_profile_fingerprint": _fingerprint(
                _PROFILE.fingerprint, "production_profile_fingerprint"
            ),
            "construction_history_namespace_id": _construction_history_namespace_id(
                construction_result.receipt.history_namespace_id
            ),
            "construction_history_sequence": _positive_integer(
                construction_result.receipt.history_sequence,
                "construction_history_sequence",
            ),
            "construction_execution_id": _construction_execution_id(
                construction_result.receipt.execution_id
            ),
            "construction_receipt_fingerprint": _fingerprint(
                construction_result.receipt.fingerprint,
                "construction_receipt_fingerprint",
            ),
            "artifact_reference": _copy_artifact_reference(artifact.reference()),
            "material_fingerprint": _fingerprint(
                construction_result.material.fingerprint,
                "material_fingerprint",
            ),
            "freshness_rule": _copy_freshness_rule(freshness_definition.rule),
            "freshness_definition_fingerprint": _fingerprint(
                freshness_definition.fingerprint,
                "freshness_definition_fingerprint",
            ),
            "governance_scope": _scope(_PROFILE.scope),
            "observation_period_start": _timestamp(
                observation_start, "observation_period_start"
            ),
            "observation_period_end": _timestamp(
                observation_end, "observation_period_end"
            ),
            "evaluation_as_of": _timestamp(
                freshness_record.evaluation_as_of, "evaluation_as_of"
            ),
            "new_york_evaluation_date": support.new_york_evaluation_date,
            "retained_material_row_count": support.retained_material_row_count,
            "first_retained_session_date": support.first_retained_session_date,
            "latest_retained_session_date": support.latest_retained_session_date,
            "eligible_completed_session_count": (
                support.eligible_completed_session_count
            ),
            "latest_eligible_completed_session_date": (
                support.latest_eligible_completed_session_date
            ),
            "calendar_lag_days": support.calendar_lag_days,
            "outcome": support.outcome,
            "freshness_evaluation_reference": _copy_evaluation_reference(
                freshness_record.reference()
            ),
            "result": support.result,
            "execution_started_at": _timestamp(
                execution_started_at, "execution_started_at"
            ),
            "execution_completed_at": _timestamp(
                execution_completed_at, "execution_completed_at"
            ),
            "available_at": _timestamp(available_at, "available_at"),
            "schema_version": _SCHEMA,
        }
        for name, value in values.items():
            object.__setattr__(companion, name, value)
        object.__setattr__(
            companion,
            "fingerprint",
            canonical_fingerprint(companion._fingerprint_payload()),
        )
        companion._validate()
        return companion

    @classmethod
    def _with_available_at(
        cls,
        staged: PolygonCompletedDailyFreshnessExecutionCompanion,
        *,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyFreshnessExecutionCompanion:
        if seal is not _COMPANION_SEAL:
            raise TypeError("freshness execution publication is private")
        companion = object.__new__(cls)
        for name in (
            "execution_id",
            "history_sequence",
            "history_namespace_id",
            "execution_kind",
            "operation",
            "executor",
            "production_profile_reference",
            "production_profile_fingerprint",
            "construction_history_namespace_id",
            "construction_history_sequence",
            "construction_execution_id",
            "construction_receipt_fingerprint",
            "artifact_reference",
            "material_fingerprint",
            "freshness_rule",
            "freshness_definition_fingerprint",
            "governance_scope",
            "observation_period_start",
            "observation_period_end",
            "evaluation_as_of",
            "new_york_evaluation_date",
            "retained_material_row_count",
            "first_retained_session_date",
            "latest_retained_session_date",
            "eligible_completed_session_count",
            "latest_eligible_completed_session_date",
            "calendar_lag_days",
            "outcome",
            "freshness_evaluation_reference",
            "result",
            "execution_started_at",
            "execution_completed_at",
            "schema_version",
        ):
            object.__setattr__(companion, name, getattr(staged, name))
        object.__setattr__(
            companion, "available_at", _timestamp(available_at, "available_at")
        )
        object.__setattr__(
            companion,
            "fingerprint",
            canonical_fingerprint(companion._fingerprint_payload()),
        )
        return companion

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "history_sequence": self.history_sequence,
            "history_namespace_id": self.history_namespace_id,
            "execution_kind": self.execution_kind.value,
            "operation": self.operation.to_dict(),
            "executor": self.executor.to_dict(),
            "production_profile_reference": (
                self.production_profile_reference.to_dict()
            ),
            "production_profile_fingerprint": self.production_profile_fingerprint,
            "construction_history_namespace_id": (
                self.construction_history_namespace_id
            ),
            "construction_history_sequence": self.construction_history_sequence,
            "construction_execution_id": self.construction_execution_id,
            "construction_receipt_fingerprint": (self.construction_receipt_fingerprint),
            "artifact_reference": self.artifact_reference.to_dict(),
            "material_fingerprint": self.material_fingerprint,
            "freshness_rule": self.freshness_rule.to_dict(),
            "freshness_definition_fingerprint": (self.freshness_definition_fingerprint),
            "governance_scope": self.governance_scope,
            "observation_period_start": self.observation_period_start.isoformat(),
            "observation_period_end": self.observation_period_end.isoformat(),
            "evaluation_as_of": self.evaluation_as_of.isoformat(),
            "new_york_evaluation_date": self.new_york_evaluation_date.isoformat(),
            "retained_material_row_count": self.retained_material_row_count,
            "first_retained_session_date": _optional_date_text(
                self.first_retained_session_date
            ),
            "latest_retained_session_date": _optional_date_text(
                self.latest_retained_session_date
            ),
            "eligible_completed_session_count": (self.eligible_completed_session_count),
            "latest_eligible_completed_session_date": _optional_date_text(
                self.latest_eligible_completed_session_date
            ),
            "calendar_lag_days": self.calendar_lag_days,
            "outcome": self.outcome.value,
            "freshness_evaluation_reference": (
                self.freshness_evaluation_reference.to_dict()
            ),
            "result": self.result,
            "execution_started_at": self.execution_started_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    def _validate(self) -> None:
        try:
            schema_version = self.schema_version
            fingerprint = self.fingerprint
        except AttributeError as error:
            raise ValueError(
                "freshness companion retained state is incomplete"
            ) from error
        if schema_version != _SCHEMA:
            raise ValueError("freshness companion schema is invalid")
        _execution_id(self.execution_id)
        _positive_integer(self.history_sequence, "history_sequence")
        _history_namespace_id(self.history_namespace_id)
        kind = _execution_kind(self.execution_kind)
        self.operation._validate()
        self.executor._validate()
        self.production_profile_reference._validate()
        if self.operation != _operation(kind):
            raise ValueError("freshness operation identity is not approved")
        if self.executor != _EXECUTOR:
            raise ValueError("freshness executor identity is not approved")
        if self.production_profile_reference != _PROFILE_REFERENCE:
            raise ValueError("production profile reference is not approved")
        if self.production_profile_fingerprint != _PROFILE.fingerprint:
            raise ValueError("production profile fingerprint is not approved")
        _construction_history_namespace_id(self.construction_history_namespace_id)
        _positive_integer(
            self.construction_history_sequence, "construction_history_sequence"
        )
        _construction_execution_id(self.construction_execution_id)
        _fingerprint(
            self.construction_receipt_fingerprint,
            "construction_receipt_fingerprint",
        )
        self.artifact_reference._validate()
        _fingerprint(self.material_fingerprint, "material_fingerprint")
        definition = _approved_definition(kind)
        self.freshness_rule._validate()
        if self.freshness_rule != definition.rule:
            raise ValueError("freshness rule is not the approved exact rule")
        if self.freshness_definition_fingerprint != definition.fingerprint:
            raise ValueError("freshness definition fingerprint is not approved")
        if self.governance_scope != _PROFILE.scope:
            raise ValueError("freshness governance scope is not approved")
        observation_start = _require_canonical_timestamp(
            self.observation_period_start, "observation_period_start"
        )
        observation_end = _require_canonical_timestamp(
            self.observation_period_end, "observation_period_end"
        )
        if observation_start >= observation_end:
            raise ValueError("requested observation interval is incoherent")
        _require_canonical_timestamp(self.evaluation_as_of, "evaluation_as_of")
        _validate_support_fields(
            new_york_evaluation_date=self.new_york_evaluation_date,
            retained_material_row_count=self.retained_material_row_count,
            first_retained_session_date=self.first_retained_session_date,
            latest_retained_session_date=self.latest_retained_session_date,
            eligible_completed_session_count=self.eligible_completed_session_count,
            latest_eligible_completed_session_date=(
                self.latest_eligible_completed_session_date
            ),
            calendar_lag_days=self.calendar_lag_days,
            outcome=self.outcome,
            result=self.result,
        )
        self.freshness_evaluation_reference._validate()
        reference = self.freshness_evaluation_reference
        if (
            reference.artifact_reference != self.artifact_reference
            or reference.freshness_rule_fingerprint != self.freshness_rule.fingerprint
            or reference.evaluation_scope != self.governance_scope
            or reference.evaluation_as_of != self.evaluation_as_of
            or reference.result is not self.result
        ):
            raise ValueError(
                "freshness lifecycle reference does not correspond to companion"
            )
        started = _require_canonical_timestamp(
            self.execution_started_at, "execution_started_at"
        )
        completed = _require_canonical_timestamp(
            self.execution_completed_at, "execution_completed_at"
        )
        available = _require_canonical_timestamp(self.available_at, "available_at")
        if not started <= completed <= available:
            raise ValueError("freshness execution chronology is incoherent")
        if kind is PolygonCompletedDailyFreshnessExecutionKind.ADMISSION and not (
            started <= self.evaluation_as_of <= completed
        ):
            raise ValueError("admission freshness evaluation chronology is incoherent")
        retained = _fingerprint(fingerprint, "companion fingerprint")
        if retained != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("freshness companion fingerprint is invalid")

    def to_dict(self) -> dict[str, object]:
        """Return the exact source-specific freshness execution projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyProductionFreshnessResult:
    """One exact lifecycle record, companion, and trusted construction input."""

    construction_result: PolygonCompletedDailyProductionConstructionResult
    freshness_record: EvidenceFreshnessEvaluationRecord
    companion: PolygonCompletedDailyFreshnessExecutionCompanion

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyProductionFreshnessResult is created only by "
            "trusted production freshness history"
        )

    @classmethod
    def _create(
        cls,
        *,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        freshness_record: EvidenceFreshnessEvaluationRecord,
        companion: PolygonCompletedDailyFreshnessExecutionCompanion,
        seal: object,
    ) -> PolygonCompletedDailyProductionFreshnessResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production freshness result creation is private")
        result = object.__new__(cls)
        object.__setattr__(result, "construction_result", construction_result)
        object.__setattr__(result, "freshness_record", freshness_record)
        object.__setattr__(result, "companion", companion)
        result._validate()
        return result

    @classmethod
    def _with_companion(
        cls,
        staged: PolygonCompletedDailyProductionFreshnessResult,
        *,
        companion: PolygonCompletedDailyFreshnessExecutionCompanion,
        seal: object,
    ) -> PolygonCompletedDailyProductionFreshnessResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production freshness result publication is private")
        result = object.__new__(cls)
        object.__setattr__(result, "construction_result", staged.construction_result)
        object.__setattr__(result, "freshness_record", staged.freshness_record)
        object.__setattr__(result, "companion", companion)
        return result

    @property
    def artifact(self) -> EvidenceArtifact:
        """Return the exact Candidate retained by trusted construction history."""

        self._validate()
        return self.construction_result.artifact

    @property
    def material(self) -> PolygonCompletedDailyOhlcvMaterial:
        """Return the exact governed material retained by construction history."""

        self._validate()
        return self.construction_result.material

    def _validate(self) -> None:
        _validate_result_correspondence(
            self.construction_result,
            self.freshness_record,
            self.companion,
        )


class _InMemoryPolygonCompletedDailyFreshnessHistory:
    """Private complete history for the two approved freshness operations."""

    __slots__ = ("_lock", "_namespace_id", "_pending", "_state")

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = _issue_history_namespace_id()
        self._pending: PolygonCompletedDailyProductionFreshnessResult | None = None
        self._state: tuple[
            int, tuple[PolygonCompletedDailyProductionFreshnessResult, ...]
        ] = (1, ())

    def _retain(
        self,
        *,
        execution_id: str,
        execution_kind: PolygonCompletedDailyFreshnessExecutionKind,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        freshness_definition: _FreshnessRuleDefinition,
        freshness_record: EvidenceFreshnessEvaluationRecord,
        support: _FreshnessSupport,
        execution_started_at: datetime,
        completion_clock: Callable[[], datetime],
        availability_clock: Callable[[], datetime],
        seal: object,
    ) -> PolygonCompletedDailyProductionFreshnessResult:
        if seal is not _HISTORY_SEAL:
            raise TypeError("trusted freshness history retention is private")
        if not callable(completion_clock) or not callable(availability_clock):
            raise TypeError("completion and availability clocks must be callable")
        _validate_prepublication(
            execution_kind=execution_kind,
            construction_result=construction_result,
            freshness_definition=freshness_definition,
            freshness_record=freshness_record,
            support=support,
        )
        started_at = _timestamp(execution_started_at, "execution_started_at")
        completed_at = _timestamp(completion_clock(), "execution_completed_at")
        if completed_at < started_at:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                "freshness completion precedes execution start",
            )
        if (
            execution_kind is PolygonCompletedDailyFreshnessExecutionKind.ADMISSION
            and not started_at <= freshness_record.evaluation_as_of <= completed_at
        ):
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                "admission evaluation is outside its execution interval",
            )

        with self._lock:
            next_sequence, entries = self._state
            try:
                _validate_retained_entries(
                    entries,
                    expected_namespace_id=self._namespace_id,
                )
            except (TypeError, ValueError) as error:
                raise PolygonCompletedDailyFreshnessHistoryError(
                    "retained freshness history is incomplete or corrupt"
                ) from error
            staged_available_at = max(
                completed_at,
                entries[-1].companion.available_at if entries else completed_at,
            )
            staged_companion = PolygonCompletedDailyFreshnessExecutionCompanion._create(
                execution_id=execution_id,
                history_sequence=next_sequence,
                history_namespace_id=self._namespace_id,
                execution_kind=execution_kind,
                construction_result=construction_result,
                freshness_definition=freshness_definition,
                freshness_record=freshness_record,
                support=support,
                execution_started_at=started_at,
                execution_completed_at=completed_at,
                available_at=staged_available_at,
                seal=_COMPANION_SEAL,
            )
            staged = PolygonCompletedDailyProductionFreshnessResult._create(
                construction_result=construction_result,
                freshness_record=freshness_record,
                companion=staged_companion,
                seal=_RESULT_SEAL,
            )
            try:
                self._stage_publication(staged)
                available_at = _timestamp(availability_clock(), "available_at")
                if available_at < completed_at:
                    raise PolygonCompletedDailyFreshnessExecutionRefused(
                        PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                        "freshness availability precedes execution completion",
                    )
                if entries and available_at < entries[-1].companion.available_at:
                    raise PolygonCompletedDailyFreshnessExecutionRefused(
                        PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                        "freshness availability must not move backward",
                    )
                companion = (
                    PolygonCompletedDailyFreshnessExecutionCompanion._with_available_at(
                        staged.companion,
                        available_at=available_at,
                        seal=_COMPANION_SEAL,
                    )
                )
                retained = (
                    PolygonCompletedDailyProductionFreshnessResult._with_companion(
                        staged,
                        companion=companion,
                        seal=_RESULT_SEAL,
                    )
                )
                retained._validate()
                self._state = (next_sequence + 1, (*entries, retained))
                return retained
            finally:
                self._pending = None

    def _stage_publication(
        self,
        staged: PolygonCompletedDailyProductionFreshnessResult,
    ) -> None:
        staged._validate()
        self._pending = staged

    def _history(
        self,
        artifact_reference: EvidenceArtifactReference,
        construction_execution_id: str,
        *,
        execution_kind: PolygonCompletedDailyFreshnessExecutionKind,
        knowledge_as_of: datetime | None,
    ) -> tuple[PolygonCompletedDailyProductionFreshnessResult, ...]:
        reference = _copy_artifact_reference(artifact_reference)
        construction_id = _construction_execution_id(construction_execution_id)
        kind = _execution_kind(execution_kind)
        cutoff = (
            None
            if knowledge_as_of is None
            else _timestamp(knowledge_as_of, "knowledge_as_of")
        )
        with self._lock:
            entries = self._state[1]
        try:
            _validate_retained_entries(
                entries,
                expected_namespace_id=self._namespace_id,
            )
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyFreshnessHistoryError(
                "retained freshness history is incomplete or corrupt"
            ) from error
        relevant = tuple(
            item
            for item in entries
            if item.companion.artifact_reference.artifact_id == reference.artifact_id
            and item.companion.artifact_reference.artifact_version
            == reference.artifact_version
            and item.companion.construction_execution_id == construction_id
            and item.companion.execution_kind is kind
            and (cutoff is None or item.companion.available_at <= cutoff)
        )
        if any(item.companion.artifact_reference != reference for item in relevant):
            raise PolygonCompletedDailyFreshnessHistoryConflictError(
                "artifact identity has conflicting retained freshness history"
            )
        return tuple(sorted(relevant, key=lambda item: item.companion.history_sequence))


class PolygonCompletedDailyProductionFreshnessApplicationService:
    """Execute the two closed freshness rules against trusted construction history."""

    __slots__ = ("_construction_service", "_execution_clock", "_history")

    def __init__(
        self,
        construction_service: (
            PolygonCompletedDailyProductionConstructionApplicationService
        ),
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            type(construction_service)
            is not PolygonCompletedDailyProductionConstructionApplicationService
        ):
            raise TypeError(
                "construction_service must be the exact trusted production "
                "construction service"
            )
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._construction_service = construction_service
        self._execution_clock = _utc_now if execution_clock is None else execution_clock
        self._history = _InMemoryPolygonCompletedDailyFreshnessHistory()

    def execute_admission(
        self,
        request: PolygonCompletedDailyAdmissionFreshnessRequest,
    ) -> PolygonCompletedDailyProductionFreshnessResult:
        """Execute and retain the approved admission-time freshness rule."""

        if type(request) is not PolygonCompletedDailyAdmissionFreshnessRequest:
            raise TypeError(
                "request must be an exact "
                "PolygonCompletedDailyAdmissionFreshnessRequest"
            )
        request._validate()
        started_at = _timestamp(self._execution_clock(), "execution_started_at")
        construction_result = self._resolve_construction(
            request.artifact_reference,
            request.construction_execution_id,
        )
        _require_construction_available_at_start(construction_result, started_at)
        evaluation_as_of = _timestamp(self._execution_clock(), "evaluation_as_of")
        if evaluation_as_of < started_at:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                "admission evaluation time precedes execution start",
            )
        return self._execute_resolved(
            execution_kind=PolygonCompletedDailyFreshnessExecutionKind.ADMISSION,
            construction_result=construction_result,
            evaluation_as_of=evaluation_as_of,
            execution_started_at=started_at,
        )

    def execute_task(
        self,
        request: PolygonCompletedDailyTaskFreshnessRequest,
    ) -> PolygonCompletedDailyProductionFreshnessResult:
        """Execute and retain the approved Daily Technical freshness rule."""

        if type(request) is not PolygonCompletedDailyTaskFreshnessRequest:
            raise TypeError(
                "request must be an exact PolygonCompletedDailyTaskFreshnessRequest"
            )
        request._validate()
        started_at = _timestamp(self._execution_clock(), "execution_started_at")
        construction_result = self._resolve_construction(
            request.artifact_reference,
            request.construction_execution_id,
        )
        _require_construction_available_at_start(construction_result, started_at)
        return self._execute_resolved(
            execution_kind=PolygonCompletedDailyFreshnessExecutionKind.DAILY_TECHNICAL,
            construction_result=construction_result,
            evaluation_as_of=request.evaluation_as_of,
            execution_started_at=started_at,
        )

    def _execute_resolved(
        self,
        *,
        execution_kind: PolygonCompletedDailyFreshnessExecutionKind,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        evaluation_as_of: datetime,
        execution_started_at: datetime,
    ) -> PolygonCompletedDailyProductionFreshnessResult:
        try:
            definition = _approved_definition(execution_kind)
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.POLICY_RULE_MISMATCH,
                "approved freshness definition cannot be resolved",
            ) from error
        try:
            support = _derive_support(
                construction_result.material,
                evaluation_as_of=evaluation_as_of,
            )
            freshness_record = create_evidence_freshness_evaluation_record(
                artifact=construction_result.artifact,
                freshness_rule=definition.rule,
                evaluation_as_of=evaluation_as_of,
                result=support.result,
                findings=_findings(support),
            )
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.ARTIFACT_MATERIAL_MISMATCH,
                "trusted construction material cannot support exact freshness "
                "execution",
            ) from error
        try:
            return self._history._retain(
                execution_id=_issue_execution_id(),
                execution_kind=execution_kind,
                construction_result=construction_result,
                freshness_definition=definition,
                freshness_record=freshness_record,
                support=support,
                execution_started_at=execution_started_at,
                completion_clock=self._execution_clock,
                availability_clock=self._execution_clock,
                seal=_HISTORY_SEAL,
            )
        except PolygonCompletedDailyFreshnessExecutionRefused:
            raise
        except PolygonCompletedDailyFreshnessHistoryError as error:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "trusted freshness history cannot publish the result",
            ) from error
        except (TypeError, ValueError, RuntimeError) as error:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "trusted freshness publication failed",
            ) from error

    def _resolve_construction(
        self,
        artifact_reference: EvidenceArtifactReference,
        construction_execution_id: str,
    ) -> PolygonCompletedDailyProductionConstructionResult:
        try:
            history = self._construction_service.get_construction_history(
                artifact_reference
            )
        except PolygonCompletedDailyConstructionHistoryError as error:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "trusted construction history is incomplete or conflicting",
            ) from error
        matches = tuple(
            item
            for item in history
            if item.receipt.execution_id == construction_execution_id
        )
        if not matches:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.TRUSTED_CONSTRUCTION_UNAVAILABLE,
                "exact trusted construction occurrence is unavailable",
            )
        if len(matches) != 1:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "construction occurrence identity is ambiguous",
            )
        result = matches[0]
        try:
            result._validate()
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.ARTIFACT_MATERIAL_MISMATCH,
                "trusted construction result correspondence is invalid",
            ) from error
        if result.receipt.artifact_reference != artifact_reference:
            raise PolygonCompletedDailyFreshnessExecutionRefused(
                PolygonCompletedDailyFreshnessRefusalReason.ARTIFACT_MATERIAL_MISMATCH,
                "requested artifact does not match the construction occurrence",
            )
        return result

    def get_admission_freshness_history(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        construction_execution_id: str,
    ) -> tuple[PolygonCompletedDailyProductionFreshnessResult, ...]:
        """Return every authentic admission freshness execution for one occurrence."""

        return self._history._history(
            artifact_reference,
            construction_execution_id,
            execution_kind=PolygonCompletedDailyFreshnessExecutionKind.ADMISSION,
            knowledge_as_of=None,
        )

    def get_admission_freshness_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        construction_execution_id: str,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyProductionFreshnessResult, ...]:
        """Return admission freshness available by the inclusive knowledge cutoff."""

        return self._history._history(
            artifact_reference,
            construction_execution_id,
            execution_kind=PolygonCompletedDailyFreshnessExecutionKind.ADMISSION,
            knowledge_as_of=knowledge_as_of,
        )

    def get_task_freshness_history(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        construction_execution_id: str,
    ) -> tuple[PolygonCompletedDailyProductionFreshnessResult, ...]:
        """Return every authentic task freshness execution for one occurrence."""

        return self._history._history(
            artifact_reference,
            construction_execution_id,
            execution_kind=(
                PolygonCompletedDailyFreshnessExecutionKind.DAILY_TECHNICAL
            ),
            knowledge_as_of=None,
        )

    def get_task_freshness_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        construction_execution_id: str,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyProductionFreshnessResult, ...]:
        """Return task freshness available by the inclusive knowledge cutoff."""

        return self._history._history(
            artifact_reference,
            construction_execution_id,
            execution_kind=(
                PolygonCompletedDailyFreshnessExecutionKind.DAILY_TECHNICAL
            ),
            knowledge_as_of=knowledge_as_of,
        )


def _operation(
    execution_kind: PolygonCompletedDailyFreshnessExecutionKind,
) -> EvidenceIdentityReference:
    kind = _execution_kind(execution_kind)
    definition = _approved_definition(kind)
    operation_id = (
        "polygon_completed_daily_freshness_admission"
        if kind is PolygonCompletedDailyFreshnessExecutionKind.ADMISSION
        else "polygon_completed_daily_freshness_daily_technical"
    )
    return EvidenceIdentityReference(
        namespace="market_platform.application.operation",
        identity_id=operation_id,
        identity_version=_VERSION,
        identity_fingerprint=canonical_fingerprint(
            {
                "schema_version": _OPERATION_SCHEMA,
                "operation_id": operation_id,
                "operation_version": _VERSION,
                "freshness_rule": definition.rule.to_dict(),
                "freshness_definition_fingerprint": definition.fingerprint,
                "production_profile_fingerprint": _PROFILE.fingerprint,
            }
        ),
    )


def _approved_definition(
    execution_kind: PolygonCompletedDailyFreshnessExecutionKind,
) -> _FreshnessRuleDefinition:
    kind = _execution_kind(execution_kind)
    resolved = _resolve_approved_polygon_completed_daily_production_profile(_PROFILE)
    definition = (
        resolved.admission_freshness
        if kind is PolygonCompletedDailyFreshnessExecutionKind.ADMISSION
        else resolved.task_freshness
    )
    expected = (
        _ADMISSION_DEFINITION
        if kind is PolygonCompletedDailyFreshnessExecutionKind.ADMISSION
        else _TASK_DEFINITION
    )
    definition._validate()
    if definition != expected or definition.fingerprint != expected.fingerprint:
        raise ValueError("freshness definition is not an exact approved member")
    configuration = definition._configuration_payload()
    if (
        configuration.get("market_timezone") != _MARKET_TIMEZONE_NAME
        or configuration.get("expected_session_calendar") is not None
        or configuration.get("publication_time_inference") != "prohibited"
        or configuration.get("holiday_exception_extension") is not None
        or configuration.get("minimum_calendar_lag_days") != _MINIMUM_LAG_DAYS
        or configuration.get("maximum_calendar_lag_days") != _MAXIMUM_LAG_DAYS
        or configuration.get("maximum_lag_inclusive") is not True
    ):
        raise ValueError("freshness definition configuration is not approved")
    return definition


def _derive_support(
    material: PolygonCompletedDailyOhlcvMaterial,
    *,
    evaluation_as_of: datetime,
) -> _FreshnessSupport:
    if type(material) is not PolygonCompletedDailyOhlcvMaterial:
        raise TypeError("material must be exact Polygon completed-daily material")
    expected_fingerprint = canonical_fingerprint(material._fingerprint_payload())
    if material.fingerprint != expected_fingerprint:
        raise ValueError("retained material fingerprint does not match content")
    instant = _timestamp(evaluation_as_of, "evaluation_as_of")
    evaluation_date = instant.astimezone(_MARKET_TIMEZONE).date()
    dates: list[date] = []
    prior: date | None = None
    for row in material.rows:
        if type(row) is not PolygonCompletedDailyOhlcvMaterialRow:
            raise TypeError("retained material contains an invalid row type")
        session_date = _session_date(row.session_date)
        if prior is not None and session_date <= prior:
            raise ValueError("retained session dates must be strictly increasing")
        dates.append(session_date)
        prior = session_date
    if material.row_count != len(dates):
        raise ValueError("retained material row_count does not match rows")
    eligible = tuple(item for item in dates if item < evaluation_date)
    latest_eligible = eligible[-1] if eligible else None
    lag = None if latest_eligible is None else (evaluation_date - latest_eligible).days
    if latest_eligible is None:
        outcome = (
            PolygonCompletedDailyFreshnessOutcome.NO_ELIGIBLE_RETAINED_COMPLETED_SESSION
        )
        result = False
    elif lag is not None and _MINIMUM_LAG_DAYS <= lag <= _MAXIMUM_LAG_DAYS:
        outcome = PolygonCompletedDailyFreshnessOutcome.FRESH
        result = True
    else:
        outcome = PolygonCompletedDailyFreshnessOutcome.STALE_CALENDAR_LAG
        result = False
    return _FreshnessSupport(
        new_york_evaluation_date=evaluation_date,
        retained_material_row_count=len(dates),
        first_retained_session_date=dates[0] if dates else None,
        latest_retained_session_date=dates[-1] if dates else None,
        eligible_completed_session_count=len(eligible),
        latest_eligible_completed_session_date=latest_eligible,
        calendar_lag_days=lag,
        outcome=outcome,
        result=result,
    )


def _findings(support: _FreshnessSupport) -> tuple[str, ...]:
    if support.outcome is PolygonCompletedDailyFreshnessOutcome.FRESH:
        return (
            "Latest eligible retained completed session satisfies the approved "
            "inclusive 1-4 calendar-day recency window.",
        )
    if support.outcome is PolygonCompletedDailyFreshnessOutcome.STALE_CALENDAR_LAG:
        return (
            "Latest eligible retained completed session is outside the approved "
            "inclusive 1-4 calendar-day recency window.",
        )
    return (
        "No eligible retained completed session exists strictly before the "
        "New York evaluation date.",
    )


def _validate_prepublication(
    *,
    execution_kind: PolygonCompletedDailyFreshnessExecutionKind,
    construction_result: PolygonCompletedDailyProductionConstructionResult,
    freshness_definition: _FreshnessRuleDefinition,
    freshness_record: EvidenceFreshnessEvaluationRecord,
    support: _FreshnessSupport,
) -> None:
    kind = _execution_kind(execution_kind)
    construction_result._validate()
    expected_definition = _approved_definition(kind)
    freshness_definition._validate()
    if (
        freshness_definition != expected_definition
        or freshness_definition.fingerprint != expected_definition.fingerprint
    ):
        raise ValueError("freshness definition does not match approved operation")
    freshness_record._validate()
    expected_support = _derive_support(
        construction_result.material,
        evaluation_as_of=freshness_record.evaluation_as_of,
    )
    if support != expected_support:
        raise ValueError("freshness support does not match retained material")
    if freshness_record.freshness_rule != expected_definition.rule:
        raise ValueError("freshness record rule does not match approved operation")
    if freshness_record.result is not support.result:
        raise ValueError("freshness record result does not match predicate")
    if freshness_record.findings != _findings(support):
        raise ValueError("freshness record findings do not match predicate outcome")
    _validate_artifact_temporal_anchor(
        construction_result.artifact,
        freshness_record,
    )


def _validate_result_correspondence(
    construction_result: PolygonCompletedDailyProductionConstructionResult,
    freshness_record: EvidenceFreshnessEvaluationRecord,
    companion: PolygonCompletedDailyFreshnessExecutionCompanion,
) -> None:
    if (
        type(construction_result)
        is not PolygonCompletedDailyProductionConstructionResult
    ):
        raise TypeError("construction_result type is invalid")
    construction_result._validate()
    if type(freshness_record) is not EvidenceFreshnessEvaluationRecord:
        raise TypeError("freshness_record type is invalid")
    freshness_record._validate()
    if type(companion) is not PolygonCompletedDailyFreshnessExecutionCompanion:
        raise TypeError("companion type is invalid")
    companion._validate()
    receipt = construction_result.receipt
    material = construction_result.material
    artifact = construction_result.artifact
    if (
        companion.construction_history_namespace_id != receipt.history_namespace_id
        or companion.construction_history_sequence != receipt.history_sequence
        or companion.construction_execution_id != receipt.execution_id
        or companion.construction_receipt_fingerprint != receipt.fingerprint
    ):
        raise ValueError("companion does not bind exact construction occurrence")
    if companion.artifact_reference != artifact.reference():
        raise ValueError("companion does not bind exact Candidate artifact")
    if companion.material_fingerprint != material.fingerprint:
        raise ValueError("companion does not bind exact governed material")
    if companion.production_profile_fingerprint != (
        receipt.production_profile_fingerprint
    ):
        raise ValueError("companion and construction profile do not correspond")
    if companion.freshness_evaluation_reference != freshness_record.reference():
        raise ValueError("companion does not bind exact lifecycle record")
    if companion.freshness_rule != freshness_record.freshness_rule:
        raise ValueError("companion and lifecycle freshness rules differ")
    if companion.evaluation_as_of != freshness_record.evaluation_as_of:
        raise ValueError("companion and lifecycle evaluation instants differ")
    if companion.result is not freshness_record.result:
        raise ValueError("companion and lifecycle results differ")
    temporal = artifact.temporal_identity
    if (
        companion.observation_period_start != temporal.observation_period_start
        or companion.observation_period_end != temporal.observation_period_end
    ):
        raise ValueError("companion does not retain exact observation interval")
    support = _derive_support(
        material,
        evaluation_as_of=freshness_record.evaluation_as_of,
    )
    if _support_from_companion(companion) != support:
        raise ValueError("companion support does not match exact retained material")
    if freshness_record.findings != _findings(support):
        raise ValueError("lifecycle findings do not match material-derived outcome")
    _validate_artifact_temporal_anchor(artifact, freshness_record)


def _validate_artifact_temporal_anchor(
    artifact: EvidenceArtifact,
    freshness_record: EvidenceFreshnessEvaluationRecord,
) -> None:
    expected = create_evidence_freshness_evaluation_record(
        artifact=artifact,
        freshness_rule=freshness_record.freshness_rule,
        evaluation_as_of=freshness_record.evaluation_as_of,
        result=freshness_record.result,
        findings=freshness_record.findings,
    )
    if freshness_record != expected:
        raise ValueError("lifecycle temporal anchor does not match exact artifact")


def _support_from_companion(
    companion: PolygonCompletedDailyFreshnessExecutionCompanion,
) -> _FreshnessSupport:
    return _FreshnessSupport(
        new_york_evaluation_date=companion.new_york_evaluation_date,
        retained_material_row_count=companion.retained_material_row_count,
        first_retained_session_date=companion.first_retained_session_date,
        latest_retained_session_date=companion.latest_retained_session_date,
        eligible_completed_session_count=companion.eligible_completed_session_count,
        latest_eligible_completed_session_date=(
            companion.latest_eligible_completed_session_date
        ),
        calendar_lag_days=companion.calendar_lag_days,
        outcome=companion.outcome,
        result=companion.result,
    )


def _validate_support_fields(
    *,
    new_york_evaluation_date: object,
    retained_material_row_count: object,
    first_retained_session_date: object,
    latest_retained_session_date: object,
    eligible_completed_session_count: object,
    latest_eligible_completed_session_date: object,
    calendar_lag_days: object,
    outcome: object,
    result: object,
) -> None:
    evaluation_date = _exact_date(new_york_evaluation_date, "new_york_evaluation_date")
    row_count = _nonnegative_integer(
        retained_material_row_count, "retained_material_row_count"
    )
    first = _optional_exact_date(
        first_retained_session_date, "first_retained_session_date"
    )
    latest = _optional_exact_date(
        latest_retained_session_date, "latest_retained_session_date"
    )
    eligible_count = _nonnegative_integer(
        eligible_completed_session_count, "eligible_completed_session_count"
    )
    eligible_latest = _optional_exact_date(
        latest_eligible_completed_session_date,
        "latest_eligible_completed_session_date",
    )
    if type(result) is not bool:
        raise TypeError("result must be an exact bool")
    if type(outcome) is not PolygonCompletedDailyFreshnessOutcome:
        raise TypeError("outcome must be an exact freshness outcome")
    if row_count == 0:
        if first is not None or latest is not None:
            raise ValueError("empty material cannot retain a session range")
    elif first is None or latest is None or first > latest:
        raise ValueError("retained material session range is incomplete")
    if eligible_count > row_count:
        raise ValueError("eligible session count exceeds retained row count")
    if eligible_count == 0:
        if eligible_latest is not None or calendar_lag_days is not None:
            raise ValueError("absent eligible session cannot retain a lag")
        if (
            outcome
            is not (
                PolygonCompletedDailyFreshnessOutcome.NO_ELIGIBLE_RETAINED_COMPLETED_SESSION
            )
            or result is not False
        ):
            raise ValueError("no-session freshness outcome is inconsistent")
        return
    if eligible_latest is None:
        raise ValueError("eligible session count requires a latest session")
    if latest is None or first is None or not first <= eligible_latest <= latest:
        raise ValueError("latest eligible session is outside retained material")
    if eligible_latest >= evaluation_date:
        raise ValueError("eligible session must be before evaluation date")
    expected_lag = (evaluation_date - eligible_latest).days
    if type(calendar_lag_days) is not int or calendar_lag_days != expected_lag:
        raise ValueError("calendar lag does not match material support")
    if _MINIMUM_LAG_DAYS <= expected_lag <= _MAXIMUM_LAG_DAYS:
        expected_outcome = PolygonCompletedDailyFreshnessOutcome.FRESH
        expected_result = True
    else:
        expected_outcome = PolygonCompletedDailyFreshnessOutcome.STALE_CALENDAR_LAG
        expected_result = False
    if outcome is not expected_outcome or result is not expected_result:
        raise ValueError("freshness outcome does not match approved predicate")


def _validate_retained_entries(
    entries: tuple[PolygonCompletedDailyProductionFreshnessResult, ...],
    *,
    expected_namespace_id: str,
) -> None:
    if type(entries) is not tuple:
        raise TypeError("freshness history must be an exact tuple")
    namespace_id = _history_namespace_id(expected_namespace_id)
    execution_ids: set[str] = set()
    sequences: set[int] = set()
    records: dict[str, EvidenceFreshnessEvaluationRecord] = {}
    prior_sequence = 0
    prior_availability: datetime | None = None
    for item in entries:
        if type(item) is not PolygonCompletedDailyProductionFreshnessResult:
            raise TypeError("freshness history contains an invalid result type")
        item._validate()
        companion = item.companion
        if companion.history_namespace_id != namespace_id:
            raise ValueError("freshness history namespace does not correspond")
        if companion.execution_id in execution_ids:
            raise ValueError("freshness history duplicates an execution identity")
        if companion.history_sequence in sequences:
            raise ValueError("freshness history duplicates a sequence")
        if companion.history_sequence <= prior_sequence:
            raise ValueError("freshness history sequence is not increasing")
        if (
            prior_availability is not None
            and companion.available_at < prior_availability
        ):
            raise ValueError("freshness history availability moves backward")
        retained_record = records.get(item.freshness_record.fingerprint)
        if retained_record is not None and retained_record != item.freshness_record:
            raise ValueError(
                "freshness record identity resolves to conflicting content"
            )
        records[item.freshness_record.fingerprint] = item.freshness_record
        execution_ids.add(companion.execution_id)
        sequences.add(companion.history_sequence)
        prior_sequence = companion.history_sequence
        prior_availability = companion.available_at


def _require_construction_available_at_start(
    construction_result: PolygonCompletedDailyProductionConstructionResult,
    execution_started_at: datetime,
) -> None:
    if construction_result.receipt.available_at > execution_started_at:
        raise PolygonCompletedDailyFreshnessExecutionRefused(
            PolygonCompletedDailyFreshnessRefusalReason.TEMPORAL_EXECUTION_FAILURE,
            "freshness execution started before construction became available",
        )


def _copy_artifact_reference(value: object) -> EvidenceArtifactReference:
    if type(value) is not EvidenceArtifactReference:
        raise TypeError("artifact_reference must be an EvidenceArtifactReference")
    value._validate()
    return EvidenceArtifactReference(
        artifact_id=value.artifact_id,
        artifact_version=value.artifact_version,
        artifact_fingerprint=value.artifact_fingerprint,
        information_class=value.information_class,
        authority=value.authority,
    )


def _copy_identity_reference(value: object) -> EvidenceIdentityReference:
    if type(value) is not EvidenceIdentityReference:
        raise TypeError("identity must be an EvidenceIdentityReference")
    value._validate()
    return EvidenceIdentityReference(
        namespace=value.namespace,
        identity_id=value.identity_id,
        identity_version=value.identity_version,
        identity_fingerprint=value.identity_fingerprint,
    )


def _copy_freshness_rule(value: object) -> EvidenceFreshnessRule:
    if type(value) is not EvidenceFreshnessRule:
        raise TypeError("freshness_rule must be an EvidenceFreshnessRule")
    value._validate()
    return EvidenceFreshnessRule(
        rule_id=value.rule_id,
        rule_version=value.rule_version,
        declared_temporal_anchor=value.declared_temporal_anchor,
        evaluation_scope=value.evaluation_scope,
    )


def _copy_evaluation_reference(
    value: object,
) -> EvidenceFreshnessEvaluationReference:
    if type(value) is not EvidenceFreshnessEvaluationReference:
        raise TypeError(
            "freshness reference must be an EvidenceFreshnessEvaluationReference"
        )
    value._validate()
    return EvidenceFreshnessEvaluationReference(
        artifact_reference=value.artifact_reference,
        freshness_rule_fingerprint=value.freshness_rule_fingerprint,
        evaluation_scope=value.evaluation_scope,
        evaluation_as_of=value.evaluation_as_of,
        result=value.result,
        evaluation_fingerprint=value.evaluation_fingerprint,
    )


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be an exact datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{field_name} is outside supported range") from error


def _require_canonical_timestamp(value: object, field_name: str) -> datetime:
    canonical = _timestamp(value, field_name)
    if (
        type(value) is not datetime
        or value.tzinfo is not UTC
        or value.isoformat() != canonical.isoformat()
    ):
        raise ValueError(f"{field_name} must retain canonical UTC state")
    return canonical


def _session_date(value: object) -> date:
    if type(value) is not str:
        raise TypeError("session_date must be an exact string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("session_date must be exact YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError("session_date must be exact YYYY-MM-DD")
    return parsed


def _exact_date(value: object, field_name: str) -> date:
    if type(value) is not date:
        raise TypeError(f"{field_name} must be an exact date")
    return value


def _optional_exact_date(value: object, field_name: str) -> date | None:
    if value is None:
        return None
    return _exact_date(value, field_name)


def _optional_date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _positive_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a positive exact integer")
    return value


def _nonnegative_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative exact integer")
    return value


def _execution_kind(value: object) -> PolygonCompletedDailyFreshnessExecutionKind:
    if type(value) is not PolygonCompletedDailyFreshnessExecutionKind:
        raise TypeError("execution_kind must be an exact freshness execution kind")
    return value


def _scope(value: object) -> str:
    if type(value) is not str or value != _PROFILE.scope:
        raise ValueError("governance_scope is not the approved exact scope")
    return value


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


def _execution_id(value: object) -> str:
    if type(value) is not str or _EXECUTION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("execution_id is not a platform-issued canonical identity")
    return value


def _construction_execution_id(value: object) -> str:
    if (
        type(value) is not str
        or _CONSTRUCTION_EXECUTION_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("construction_execution_id is not a canonical identity")
    return value


def _history_namespace_id(value: object) -> str:
    if type(value) is not str or _HISTORY_NAMESPACE_PATTERN.fullmatch(value) is None:
        raise ValueError("history_namespace_id is not a canonical identity")
    return value


def _construction_history_namespace_id(value: object) -> str:
    if (
        type(value) is not str
        or _CONSTRUCTION_HISTORY_NAMESPACE_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            "construction_history_namespace_id is not a canonical identity"
        )
    return value


def _issue_execution_id() -> str:
    return f"polygon_completed_daily_freshness:{uuid4().hex}"


def _issue_history_namespace_id() -> str:
    return f"polygon_completed_daily_freshness_history:{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "PolygonCompletedDailyAdmissionFreshnessRequest",
    "PolygonCompletedDailyFreshnessExecutionCompanion",
    "PolygonCompletedDailyFreshnessExecutionKind",
    "PolygonCompletedDailyFreshnessExecutionRefused",
    "PolygonCompletedDailyFreshnessHistoryConflictError",
    "PolygonCompletedDailyFreshnessHistoryError",
    "PolygonCompletedDailyFreshnessOutcome",
    "PolygonCompletedDailyFreshnessRefusalReason",
    "PolygonCompletedDailyProductionFreshnessApplicationService",
    "PolygonCompletedDailyProductionFreshnessResult",
    "PolygonCompletedDailyTaskFreshnessRequest",
]
