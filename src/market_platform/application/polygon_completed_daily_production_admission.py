"""Trusted admission issuance for governed Polygon completed-daily Evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
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
from market_platform.application.polygon_completed_daily_production_construction import (  # noqa: E501
    _validate_retained_entries as _validate_constructions,
)
from market_platform.application.polygon_completed_daily_production_freshness import (
    PolygonCompletedDailyFreshnessExecutionCompanion,
    PolygonCompletedDailyFreshnessExecutionKind,
    PolygonCompletedDailyFreshnessHistoryError,
    PolygonCompletedDailyProductionFreshnessApplicationService,
    PolygonCompletedDailyProductionFreshnessResult,
)
from market_platform.application.polygon_completed_daily_production_freshness import (
    _validate_retained_entries as _validate_freshness_entries,
)
from market_platform.application.polygon_completed_daily_production_governance import (
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE,
    _resolve_approved_polygon_completed_daily_production_profile,
)
from market_platform.application.polygon_completed_daily_production_validation import (
    PolygonCompletedDailyProductionValidationApplicationService,
    PolygonCompletedDailyProductionValidationResult,
    PolygonCompletedDailyValidationExecutionCompanion,
    PolygonCompletedDailyValidationHistoryError,
)
from market_platform.application.polygon_completed_daily_production_validation import (
    _validate_retained_entries as _validate_validation_entries,
)
from market_platform.evidence.admission import (
    EvidenceAdmissionDisposition,
    EvidenceAdmissionRecord,
    EvidenceAdmissionRecordReference,
    create_evidence_admission_record,
)
from market_platform.evidence.evaluation import (
    _resolve_admission,
    _resolve_validation_concern,
)
from market_platform.evidence.policy import EvidenceAdmissionRuleSetReference
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)
from market_platform.evidence.temporal import (
    EvidenceFreshnessEvaluationRecord,
    EvidenceFreshnessEvaluationReference,
)
from market_platform.evidence.validation import (
    EvidenceValidationDisposition,
    EvidenceValidationRecord,
    EvidenceValidationRecordReference,
)

_VERSION = "1.0.0"
_PACKAGE_VERSION = "0.1.0"
_SCOPE = "research.daily_technical.completed_daily"
_SCHEMA = "polygon_completed_daily_admission_execution/v1"
_VALIDATION_EXECUTION_REFERENCE_SCHEMA = (
    "polygon_completed_daily_validation_execution_reference/v1"
)
_FRESHNESS_EXECUTION_REFERENCE_SCHEMA = (
    "polygon_completed_daily_freshness_execution_reference/v1"
)
_ADMISSION_EXECUTION_REFERENCE_SCHEMA = (
    "polygon_completed_daily_admission_execution_reference/v1"
)
_PREREQUISITE_CONTEXT_SCHEMA = (
    "polygon_completed_daily_admission_prerequisite_history/v1"
)
_RECORD_ID_SCHEMA = "polygon_completed_daily_admission_record_identity/v1"
_OPERATION_SCHEMA = "polygon_completed_daily_admission_operation/v1"
_ACTOR_SCHEMA = "polygon_completed_daily_admission_actor/v1"
_CAPABILITY_SCHEMA = "polygon_completed_daily_admission_capability/v1"
_EXECUTOR_SCHEMA = "market_platform_software_executor/v1"
_EXECUTION_ID_PATTERN = re.compile(
    r"polygon_completed_daily_admission:[0-9a-f]{32}", flags=re.ASCII
)
_CONSTRUCTION_EXECUTION_ID_PATTERN = re.compile(
    r"polygon_completed_daily_construction:[0-9a-f]{32}", flags=re.ASCII
)
_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_admission_history:[0-9a-f]{32}", flags=re.ASCII
)
_VALIDATION_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_validation_history:[0-9a-f]{32}", flags=re.ASCII
)
_FRESHNESS_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_freshness_history:[0-9a-f]{32}", flags=re.ASCII
)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_MARKET_TIMEZONE = ZoneInfo("America/New_York")
_COMPANION_SEAL = object()
_RESULT_SEAL = object()
_HISTORY_SEAL = object()

_PROFILE = _resolve_approved_polygon_completed_daily_production_profile(
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE
)
_RULESET = _PROFILE.admission_ruleset
_PROFILE_REFERENCE = EvidenceIdentityReference(
    namespace="market_platform.production_governance_profile",
    identity_id=_PROFILE.profile_id,
    identity_version=_PROFILE.profile_version,
    identity_fingerprint=_PROFILE.fingerprint,
)
_OPERATION = EvidenceIdentityReference(
    namespace="market_platform.application.operation",
    identity_id="production.polygon_completed_daily.admission.issue",
    identity_version=_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _OPERATION_SCHEMA,
            "operation_id": "production.polygon_completed_daily.admission.issue",
            "operation_version": _VERSION,
            "admission_ruleset": _RULESET.reference().to_dict(),
            "production_profile_fingerprint": _PROFILE.fingerprint,
        }
    ),
)
_ACTOR = EvidenceIdentityReference(
    namespace="market_platform.evidence_admission_authority",
    identity_id="polygon_completed_daily_production_admission",
    identity_version=_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _ACTOR_SCHEMA,
            "actor_id": "polygon_completed_daily_production_admission",
            "actor_version": _VERSION,
            "production_profile_fingerprint": _PROFILE.fingerprint,
        }
    ),
)
_CAPABILITY = EvidenceIdentityReference(
    namespace="market_platform.application.capability",
    identity_id="issue_polygon_completed_daily_evidence_admission",
    identity_version=_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _CAPABILITY_SCHEMA,
            "capability_id": "issue_polygon_completed_daily_evidence_admission",
            "capability_version": _VERSION,
            "scope": _SCOPE,
            "production_profile_fingerprint": _PROFILE.fingerprint,
        }
    ),
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


class PolygonCompletedDailyAdmissionRefusalReason(StrEnum):
    """Stable reasons why no trusted ADMITTED record was published."""

    TRUSTED_CONSTRUCTION_UNAVAILABLE = "trusted_construction_unavailable"
    ARTIFACT_TARGET_MISMATCH = "artifact_target_mismatch"
    POLICY_RULESET_MISMATCH = "policy_ruleset_mismatch"
    VALIDATION_UNAVAILABLE = "validation_unavailable"
    VALIDATION_REJECTED = "validation_rejected"
    VALIDATION_UNABLE_TO_VALIDATE = "validation_unable_to_validate"
    FRESHNESS_UNAVAILABLE = "freshness_unavailable"
    FRESHNESS_FAILED = "freshness_failed"
    TEMPORAL_PREREQUISITE_FAILURE = "temporal_prerequisite_failure"
    TEMPORAL_EXECUTION_FAILURE = "temporal_execution_failure"
    HISTORY_CONFLICT_OR_CORRUPTION = "history_conflict_or_corruption"


class PolygonCompletedDailyAdmissionIssuanceRefused(RuntimeError):
    """The production operation refused to publish an admission record."""

    reason: PolygonCompletedDailyAdmissionRefusalReason

    def __init__(
        self, reason: PolygonCompletedDailyAdmissionRefusalReason, message: str
    ) -> None:
        if type(reason) is not PolygonCompletedDailyAdmissionRefusalReason:
            raise TypeError("reason must be an admission refusal reason")
        self.reason = reason
        super().__init__(message)


class PolygonCompletedDailyAdmissionHistoryError(RuntimeError):
    """Trusted admission history is incomplete or internally inconsistent."""


class PolygonCompletedDailyAdmissionHistoryConflictError(
    PolygonCompletedDailyAdmissionHistoryError
):
    """Retained admission facts conflict for one exact history query."""


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyAdmissionRequest:
    """Permitted intent; prerequisite lifecycle records are never caller input."""

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
class PolygonCompletedDailyValidationExecutionReference:
    """Exact occurrence provenance supporting one validation lifecycle record."""

    validation_record_reference: EvidenceValidationRecordReference
    execution_id: str
    history_namespace_id: str
    history_sequence: int
    available_at: datetime
    companion_fingerprint: str
    schema_version: str = field(
        init=False, default=_VALIDATION_EXECUTION_REFERENCE_SCHEMA
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self.validation_record_reference._validate()
        _visible_ascii(self.execution_id, "execution_id", 256)
        if (
            _VALIDATION_HISTORY_NAMESPACE_PATTERN.fullmatch(self.history_namespace_id)
            is None
        ):
            raise ValueError("validation history namespace is not canonical")
        _positive_integer(self.history_sequence, "history_sequence")
        _require_canonical_timestamp(self.available_at, "available_at")
        _fingerprint(self.companion_fingerprint, "companion_fingerprint")
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "validation_record_reference": self.validation_record_reference.to_dict(),
            "execution_id": self.execution_id,
            "history_namespace_id": self.history_namespace_id,
            "history_sequence": self.history_sequence,
            "available_at": self.available_at.isoformat(),
            "companion_fingerprint": self.companion_fingerprint,
        }

    def to_dict(self) -> dict[str, object]:
        if self != replace(self):
            raise ValueError("validation execution reference fingerprint is invalid")
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyFreshnessExecutionReference:
    """Exact occurrence provenance supporting one freshness lifecycle record."""

    freshness_evaluation_reference: EvidenceFreshnessEvaluationReference
    execution_id: str
    history_namespace_id: str
    history_sequence: int
    available_at: datetime
    companion_fingerprint: str
    schema_version: str = field(
        init=False, default=_FRESHNESS_EXECUTION_REFERENCE_SCHEMA
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self.freshness_evaluation_reference._validate()
        _visible_ascii(self.execution_id, "execution_id", 256)
        if (
            _FRESHNESS_HISTORY_NAMESPACE_PATTERN.fullmatch(self.history_namespace_id)
            is None
        ):
            raise ValueError("freshness history namespace is not canonical")
        _positive_integer(self.history_sequence, "history_sequence")
        _require_canonical_timestamp(self.available_at, "available_at")
        _fingerprint(self.companion_fingerprint, "companion_fingerprint")
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "freshness_evaluation_reference": (
                self.freshness_evaluation_reference.to_dict()
            ),
            "execution_id": self.execution_id,
            "history_namespace_id": self.history_namespace_id,
            "history_sequence": self.history_sequence,
            "available_at": self.available_at.isoformat(),
            "companion_fingerprint": self.companion_fingerprint,
        }

    def to_dict(self) -> dict[str, object]:
        if self != replace(self):
            raise ValueError("freshness execution reference fingerprint is invalid")
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyAdmissionExecutionReference:
    """Exact occurrence provenance for one source-issued admission record."""

    admission_record_reference: EvidenceAdmissionRecordReference
    execution_id: str
    history_namespace_id: str
    history_sequence: int
    construction_execution_id: str
    available_at: datetime
    companion_fingerprint: str
    schema_version: str = field(
        init=False, default=_ADMISSION_EXECUTION_REFERENCE_SCHEMA
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self.admission_record_reference._validate()
        _execution_id(self.execution_id)
        _history_namespace_id(self.history_namespace_id)
        _positive_integer(self.history_sequence, "history_sequence")
        _construction_execution_id(self.construction_execution_id)
        _require_canonical_timestamp(self.available_at, "available_at")
        _fingerprint(self.companion_fingerprint, "companion_fingerprint")
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "admission_record_reference": self.admission_record_reference.to_dict(),
            "execution_id": self.execution_id,
            "history_namespace_id": self.history_namespace_id,
            "history_sequence": self.history_sequence,
            "construction_execution_id": self.construction_execution_id,
            "available_at": self.available_at.isoformat(),
            "companion_fingerprint": self.companion_fingerprint,
        }

    def to_dict(self) -> dict[str, object]:
        if self != replace(self):
            raise ValueError("admission execution reference fingerprint is invalid")
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyAdmissionExecutionCompanion:
    """Actual source-specific provenance for one admission issuance."""

    execution_id: str
    history_sequence: int
    history_namespace_id: str
    operation: EvidenceIdentityReference
    deciding_actor: EvidenceIdentityReference
    deciding_capability: EvidenceIdentityReference
    executor: EvidenceIdentityReference
    production_profile_reference: EvidenceIdentityReference
    production_profile_fingerprint: str
    artifact_reference: EvidenceArtifactReference
    material_fingerprint: str
    construction_history_namespace_id: str
    construction_history_sequence: int
    construction_execution_id: str
    construction_receipt_fingerprint: str
    admission_ruleset_reference: EvidenceAdmissionRuleSetReference
    selected_validation_record_references: tuple[EvidenceValidationRecordReference, ...]
    selected_validation_execution_references: tuple[
        PolygonCompletedDailyValidationExecutionReference, ...
    ]
    admission_freshness_evaluation_reference: EvidenceFreshnessEvaluationReference
    admission_freshness_execution_references: tuple[
        PolygonCompletedDailyFreshnessExecutionReference, ...
    ]
    prerequisite_knowledge_as_of: datetime
    prerequisite_history_fingerprint: str
    admission_record_reference: EvidenceAdmissionRecordReference
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyAdmissionExecutionCompanion is issued only by "
            "trusted admission history"
        )

    @classmethod
    def _create(
        cls,
        *,
        execution_id: str,
        history_sequence: int,
        history_namespace_id: str,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        prerequisites: _AdmissionPrerequisites,
        admission_record: EvidenceAdmissionRecord,
        execution_started_at: datetime,
        execution_completed_at: datetime,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyAdmissionExecutionCompanion:
        if seal is not _COMPANION_SEAL:
            raise TypeError("admission execution companion issuance is private")
        construction_result._validate()
        companion = object.__new__(cls)
        receipt = construction_result.receipt
        values: dict[str, object] = {
            "execution_id": _execution_id(execution_id),
            "history_sequence": _positive_integer(history_sequence, "history_sequence"),
            "history_namespace_id": _history_namespace_id(history_namespace_id),
            "operation": _OPERATION,
            "deciding_actor": _ACTOR,
            "deciding_capability": _CAPABILITY,
            "executor": _EXECUTOR,
            "production_profile_reference": _PROFILE_REFERENCE,
            "production_profile_fingerprint": _PROFILE.fingerprint,
            "artifact_reference": construction_result.artifact.reference(),
            "material_fingerprint": construction_result.material.fingerprint,
            "construction_history_namespace_id": receipt.history_namespace_id,
            "construction_history_sequence": receipt.history_sequence,
            "construction_execution_id": receipt.execution_id,
            "construction_receipt_fingerprint": receipt.fingerprint,
            "admission_ruleset_reference": _RULESET.reference(),
            "selected_validation_record_references": tuple(
                record.reference() for record in prerequisites.validation_records
            ),
            "selected_validation_execution_references": (
                prerequisites.validation_execution_references
            ),
            "admission_freshness_evaluation_reference": (
                prerequisites.freshness_record.reference()
            ),
            "admission_freshness_execution_references": (
                prerequisites.freshness_execution_references
            ),
            "prerequisite_knowledge_as_of": prerequisites.knowledge_as_of,
            "prerequisite_history_fingerprint": prerequisites.history_fingerprint,
            "admission_record_reference": admission_record.reference(),
            "execution_started_at": execution_started_at,
            "execution_completed_at": execution_completed_at,
            "available_at": available_at,
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
        staged: PolygonCompletedDailyAdmissionExecutionCompanion,
        *,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyAdmissionExecutionCompanion:
        if seal is not _COMPANION_SEAL:
            raise TypeError("admission execution publication is private")
        companion = object.__new__(cls)
        for name in cls.__slots__:
            if name not in {"available_at", "fingerprint"}:
                object.__setattr__(companion, name, getattr(staged, name))
        object.__setattr__(companion, "available_at", _timestamp(available_at))
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
            "operation": self.operation.to_dict(),
            "deciding_actor": self.deciding_actor.to_dict(),
            "deciding_capability": self.deciding_capability.to_dict(),
            "executor": self.executor.to_dict(),
            "production_profile_reference": self.production_profile_reference.to_dict(),
            "production_profile_fingerprint": self.production_profile_fingerprint,
            "artifact_reference": self.artifact_reference.to_dict(),
            "material_fingerprint": self.material_fingerprint,
            "construction_history_namespace_id": (
                self.construction_history_namespace_id
            ),
            "construction_history_sequence": self.construction_history_sequence,
            "construction_execution_id": self.construction_execution_id,
            "construction_receipt_fingerprint": self.construction_receipt_fingerprint,
            "admission_ruleset_reference": self.admission_ruleset_reference.to_dict(),
            "selected_validation_record_references": [
                item.to_dict() for item in self.selected_validation_record_references
            ],
            "selected_validation_execution_references": [
                item.to_dict() for item in self.selected_validation_execution_references
            ],
            "admission_freshness_evaluation_reference": (
                self.admission_freshness_evaluation_reference.to_dict()
            ),
            "admission_freshness_execution_references": [
                item.to_dict() for item in self.admission_freshness_execution_references
            ],
            "prerequisite_knowledge_as_of": (
                self.prerequisite_knowledge_as_of.isoformat()
            ),
            "prerequisite_history_fingerprint": self.prerequisite_history_fingerprint,
            "admission_record_reference": self.admission_record_reference.to_dict(),
            "execution_started_at": self.execution_started_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    def _validate(self) -> None:
        if self.schema_version != _SCHEMA:
            raise ValueError("admission companion schema is invalid")
        _execution_id(self.execution_id)
        _positive_integer(self.history_sequence, "history_sequence")
        _history_namespace_id(self.history_namespace_id)
        for retained, approved, name in (
            (self.operation, _OPERATION, "operation"),
            (self.deciding_actor, _ACTOR, "deciding actor"),
            (self.deciding_capability, _CAPABILITY, "deciding capability"),
            (self.executor, _EXECUTOR, "executor"),
            (self.production_profile_reference, _PROFILE_REFERENCE, "profile"),
        ):
            retained._validate()
            if retained != approved:
                raise ValueError(f"admission {name} identity is not approved")
        if self.production_profile_fingerprint != _PROFILE.fingerprint:
            raise ValueError("admission production profile fingerprint is not approved")
        self.artifact_reference._validate()
        _fingerprint(self.material_fingerprint, "material_fingerprint")
        _visible_ascii(
            self.construction_history_namespace_id,
            "construction_history_namespace_id",
            256,
        )
        _positive_integer(
            self.construction_history_sequence, "construction_history_sequence"
        )
        _construction_execution_id(self.construction_execution_id)
        _fingerprint(
            self.construction_receipt_fingerprint,
            "construction_receipt_fingerprint",
        )
        self.admission_ruleset_reference._validate()
        if self.admission_ruleset_reference != _RULESET.reference():
            raise ValueError("admission ruleset reference is not approved")
        validation_references = self.selected_validation_record_references
        if type(validation_references) is not tuple:
            raise TypeError("selected validation references must remain a tuple")
        if tuple(item.concern for item in validation_references) != (
            _RULESET.mandatory_validation_concerns
        ):
            raise ValueError("selected validation concern set is not exact")
        requirements = {
            item.concern: item for item in _RULESET.mandatory_validation_requirements
        }
        for reference in validation_references:
            reference._validate()
            requirement = requirements[reference.concern]
            if (
                reference.artifact_reference != self.artifact_reference
                or reference.scope != _SCOPE
                or reference.disposition is not EvidenceValidationDisposition.PASSED
                or reference.ruleset_id != requirement.ruleset_id
                or reference.ruleset_version != requirement.ruleset_version
            ):
                raise ValueError("selected validation reference is not admissible")
        validation_executions = self.selected_validation_execution_references
        if type(validation_executions) is not tuple:
            raise TypeError("validation execution references must remain a tuple")
        for execution_reference in validation_executions:
            execution_reference.to_dict()
        if any(
            not any(
                occurrence.validation_record_reference == lifecycle
                for occurrence in validation_executions
            )
            for lifecycle in validation_references
        ):
            raise ValueError("selected validation lacks authentic execution provenance")
        freshness = self.admission_freshness_evaluation_reference
        freshness._validate()
        rule = _RULESET.admission_freshness_rule
        assert rule is not None
        if (
            freshness.artifact_reference != self.artifact_reference
            or freshness.freshness_rule_fingerprint != rule.fingerprint
            or freshness.evaluation_scope != _SCOPE
            or not freshness.result
        ):
            raise ValueError("admission freshness reference is not admissible")
        freshness_executions = self.admission_freshness_execution_references
        if type(freshness_executions) is not tuple or not freshness_executions:
            raise ValueError("admission freshness execution provenance is missing")
        for occurrence in freshness_executions:
            occurrence.to_dict()
            if occurrence.freshness_evaluation_reference != freshness:
                raise ValueError("freshness execution provenance does not correspond")
        knowledge = _require_canonical_timestamp(
            self.prerequisite_knowledge_as_of, "prerequisite_knowledge_as_of"
        )
        _fingerprint(
            self.prerequisite_history_fingerprint,
            "prerequisite_history_fingerprint",
        )
        self.admission_record_reference._validate()
        admission = self.admission_record_reference
        if (
            admission.artifact_reference != self.artifact_reference
            or admission.admission_scope != _SCOPE
            or admission.admission_ruleset_reference != _RULESET.reference()
            or admission.disposition is not EvidenceAdmissionDisposition.ADMITTED
        ):
            raise ValueError("admission lifecycle reference does not correspond")
        started = _require_canonical_timestamp(
            self.execution_started_at, "execution_started_at"
        )
        completed = _require_canonical_timestamp(
            self.execution_completed_at, "execution_completed_at"
        )
        available = _require_canonical_timestamp(self.available_at, "available_at")
        if not started <= completed <= available or knowledge != completed:
            raise ValueError("admission execution chronology is incoherent")
        if any(item.available_at > completed for item in validation_executions):
            raise ValueError("validation prerequisite was unavailable at issuance")
        if any(item.available_at > completed for item in freshness_executions):
            raise ValueError("freshness prerequisite was unavailable at issuance")
        if freshness.evaluation_as_of > completed:
            raise ValueError("freshness evaluation is later than admission")
        if _new_york_date(freshness.evaluation_as_of) != _new_york_date(completed):
            raise ValueError("admission freshness crossed the New York date boundary")
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("admission companion fingerprint is invalid")

    def execution_reference(self) -> PolygonCompletedDailyAdmissionExecutionReference:
        """Return exact provenance suitable for the separate validity operation."""

        self._validate()
        return PolygonCompletedDailyAdmissionExecutionReference(
            admission_record_reference=self.admission_record_reference,
            execution_id=self.execution_id,
            history_namespace_id=self.history_namespace_id,
            history_sequence=self.history_sequence,
            construction_execution_id=self.construction_execution_id,
            available_at=self.available_at,
            companion_fingerprint=self.fingerprint,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the immutable admission execution projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyProductionAdmissionResult:
    """One ADMITTED lifecycle record with authentic issuance provenance."""

    construction_result: PolygonCompletedDailyProductionConstructionResult
    admission_record: EvidenceAdmissionRecord
    companion: PolygonCompletedDailyAdmissionExecutionCompanion
    _prerequisites: _AdmissionPrerequisites

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyProductionAdmissionResult is created only by "
            "trusted admission history"
        )

    @classmethod
    def _create(
        cls,
        *,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        admission_record: EvidenceAdmissionRecord,
        companion: PolygonCompletedDailyAdmissionExecutionCompanion,
        prerequisites: _AdmissionPrerequisites,
        seal: object,
    ) -> PolygonCompletedDailyProductionAdmissionResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production admission result creation is private")
        result = object.__new__(cls)
        object.__setattr__(result, "construction_result", construction_result)
        object.__setattr__(result, "admission_record", admission_record)
        object.__setattr__(result, "companion", companion)
        object.__setattr__(result, "_prerequisites", prerequisites)
        result._validate()
        return result

    @classmethod
    def _with_companion(
        cls,
        staged: PolygonCompletedDailyProductionAdmissionResult,
        *,
        companion: PolygonCompletedDailyAdmissionExecutionCompanion,
        seal: object,
    ) -> PolygonCompletedDailyProductionAdmissionResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production admission result publication is private")
        return cls._create(
            construction_result=staged.construction_result,
            admission_record=staged.admission_record,
            companion=companion,
            prerequisites=staged._prerequisites,
            seal=seal,
        )

    def _validate(self) -> None:
        self.construction_result._validate()
        self.admission_record._validate()
        self.companion._validate()
        support = self._prerequisites
        if (
            support.construction_result != self.construction_result
            or support.history_fingerprint
            != self.companion.prerequisite_history_fingerprint
            or support.history_fingerprint
            != _prerequisite_history_fingerprint(
                self.construction_result,
                support.validation_histories,
                support.freshness_history,
                support.knowledge_as_of,
            )
        ):
            raise ValueError("admission prerequisite context is corrupt")
        receipt = self.construction_result.receipt
        if (
            self.admission_record.recorded_at != self.companion.execution_completed_at
            or self.admission_record.effective_at
            != self.companion.execution_completed_at
            or receipt.available_at > self.companion.execution_started_at
            or receipt.history_namespace_id
            != self.companion.construction_history_namespace_id
            or receipt.history_sequence != self.companion.construction_history_sequence
        ):
            raise ValueError("admission lifecycle time or construction does not bind")
        if (
            self.admission_record.reference()
            != self.companion.admission_record_reference
            or self.admission_record.artifact_reference
            != self.construction_result.artifact.reference()
            or self.companion.artifact_reference
            != self.construction_result.artifact.reference()
            or self.companion.material_fingerprint
            != self.construction_result.material.fingerprint
            or self.companion.construction_execution_id != receipt.execution_id
            or self.companion.construction_receipt_fingerprint != receipt.fingerprint
            or self.admission_record.deciding_actor_identity != _ACTOR
            or self.admission_record.deciding_capability_identity != _CAPABILITY
            or self.admission_record.selected_validation_record_references
            != self.companion.selected_validation_record_references
            or self.admission_record.admission_freshness_evaluation_reference
            != self.companion.admission_freshness_evaluation_reference
        ):
            raise ValueError("admission result correspondence is invalid")


@dataclass(frozen=True, slots=True)
class _AdmissionPrerequisites:
    construction_result: PolygonCompletedDailyProductionConstructionResult
    validation_records: tuple[EvidenceValidationRecord, ...]
    validation_execution_references: tuple[
        PolygonCompletedDailyValidationExecutionReference, ...
    ]
    freshness_record: EvidenceFreshnessEvaluationRecord
    freshness_execution_references: tuple[
        PolygonCompletedDailyFreshnessExecutionReference, ...
    ]
    knowledge_as_of: datetime
    history_fingerprint: str
    validation_histories: tuple[
        tuple[PolygonCompletedDailyProductionValidationResult, ...], ...
    ]
    freshness_history: tuple[PolygonCompletedDailyProductionFreshnessResult, ...]


class _InMemoryPolygonCompletedDailyAdmissionHistory:
    """Private complete history for the exact production admission operation."""

    __slots__ = ("_lock", "_namespace_id", "_pending", "_state")

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = _issue_history_namespace_id()
        self._pending: PolygonCompletedDailyProductionAdmissionResult | None = None
        self._state: tuple[
            int, tuple[PolygonCompletedDailyProductionAdmissionResult, ...]
        ] = (1, ())

    def _retain(
        self,
        *,
        execution_id: str,
        prerequisites: _AdmissionPrerequisites,
        predecessor: EvidenceAdmissionRecord | None,
        execution_started_at: datetime,
        execution_completed_at: datetime,
        prerequisite_verifier: Callable[[], _AdmissionPrerequisites],
        availability_clock: Callable[[], datetime],
        seal: object,
    ) -> PolygonCompletedDailyProductionAdmissionResult:
        if seal is not _HISTORY_SEAL:
            raise TypeError("trusted admission history retention is private")
        if not callable(prerequisite_verifier) or not callable(availability_clock):
            raise TypeError("admission publication callbacks must be callable")
        started = _timestamp(execution_started_at)
        completed = _timestamp(execution_completed_at)
        if completed < started:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                "admission completion precedes execution start",
            )
        if prerequisites.knowledge_as_of != completed:
            raise ValueError("admission prerequisite cutoff must equal issuance time")
        construction = prerequisites.construction_result
        construction._validate()
        if construction.receipt.available_at > started:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.TEMPORAL_PREREQUISITE_FAILURE,
                "construction was unavailable when admission execution started",
            )

        with self._lock:
            next_sequence, entries = self._state
            _require_complete_sequence(next_sequence, entries)
            _validate_retained_entries(entries, self._namespace_id)
            current, _ = _resolve_effective_admission_results(
                _relevant_admission_entries(
                    entries, construction.artifact.reference(), completed
                ),
                construction.artifact.reference(),
                completed,
                allow_empty=True,
            )
            if current != predecessor:
                raise PolygonCompletedDailyAdmissionHistoryConflictError(
                    "admission predecessor changed before publication"
                )
            verified = prerequisite_verifier()
            if (
                verified.history_fingerprint != prerequisites.history_fingerprint
                or verified.validation_records != prerequisites.validation_records
                or verified.freshness_record != prerequisites.freshness_record
            ):
                raise PolygonCompletedDailyAdmissionHistoryConflictError(
                    "admission prerequisite history changed before publication"
                )
            record = _create_admission_record(
                prerequisites, predecessor=predecessor, issued_at=completed
            )
            staged_available_at = max(
                completed,
                entries[-1].companion.available_at if entries else completed,
            )
            staged_companion = PolygonCompletedDailyAdmissionExecutionCompanion._create(
                execution_id=execution_id,
                history_sequence=next_sequence,
                history_namespace_id=self._namespace_id,
                construction_result=construction,
                prerequisites=prerequisites,
                admission_record=record,
                execution_started_at=started,
                execution_completed_at=completed,
                available_at=staged_available_at,
                seal=_COMPANION_SEAL,
            )
            staged = PolygonCompletedDailyProductionAdmissionResult._create(
                construction_result=construction,
                admission_record=record,
                companion=staged_companion,
                prerequisites=prerequisites,
                seal=_RESULT_SEAL,
            )
            try:
                self._stage_publication(staged)
                available = _timestamp(availability_clock())
                if available < completed:
                    raise PolygonCompletedDailyAdmissionIssuanceRefused(
                        PolygonCompletedDailyAdmissionRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                        "admission availability precedes execution completion",
                    )
                if entries and available < entries[-1].companion.available_at:
                    raise PolygonCompletedDailyAdmissionIssuanceRefused(
                        PolygonCompletedDailyAdmissionRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                        "admission availability must not move backward",
                    )
                companion = (
                    PolygonCompletedDailyAdmissionExecutionCompanion._with_available_at(
                        staged.companion,
                        available_at=available,
                        seal=_COMPANION_SEAL,
                    )
                )
                retained = (
                    PolygonCompletedDailyProductionAdmissionResult._with_companion(
                        staged, companion=companion, seal=_RESULT_SEAL
                    )
                )
                if prerequisite_verifier() != prerequisites:
                    raise PolygonCompletedDailyAdmissionHistoryConflictError(
                        "prerequisite history changed during final publication"
                    )
                if self._state != (next_sequence, entries):
                    raise PolygonCompletedDailyAdmissionHistoryConflictError(
                        "admission history changed during final publication"
                    )
                _validate_retained_entries(entries, self._namespace_id)
                self._state = (next_sequence + 1, (*entries, retained))
                return retained
            finally:
                self._pending = None

    def _stage_publication(
        self, staged: PolygonCompletedDailyProductionAdmissionResult
    ) -> None:
        staged._validate()
        self._pending = staged

    def _history(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime | None,
    ) -> tuple[PolygonCompletedDailyProductionAdmissionResult, ...]:
        reference = _copy_artifact_reference(artifact_reference)
        cutoff = None if knowledge_as_of is None else _timestamp(knowledge_as_of)
        with self._lock:
            entries = self._state[1]
            next_sequence = self._state[0]
        try:
            _require_complete_sequence(next_sequence, entries)
            _validate_retained_entries(entries, self._namespace_id)
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyAdmissionHistoryError(
                "retained admission history is incomplete or corrupt"
            ) from error
        relevant = _relevant_admission_entries(entries, reference, cutoff)
        if any(item.companion.artifact_reference != reference for item in relevant):
            raise PolygonCompletedDailyAdmissionHistoryConflictError(
                "artifact identity has conflicting retained admission history"
            )
        if relevant:
            semantic_cutoff = (
                cutoff
                if cutoff is not None
                else max(item.companion.available_at for item in relevant)
            )
            _resolve_effective_admission_results(
                relevant, reference, semantic_cutoff, allow_empty=False
            )
        return relevant


class PolygonCompletedDailyProductionAdmissionApplicationService:
    """Resolve trusted prerequisites and issue ADMITTED without activation."""

    __slots__ = (
        "_construction_service",
        "_validation_service",
        "_freshness_service",
        "_execution_clock",
        "_history",
    )

    def __init__(
        self,
        construction_service: (
            PolygonCompletedDailyProductionConstructionApplicationService
        ),
        validation_service: PolygonCompletedDailyProductionValidationApplicationService,
        freshness_service: PolygonCompletedDailyProductionFreshnessApplicationService,
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            type(construction_service)
            is not PolygonCompletedDailyProductionConstructionApplicationService
        ):
            raise TypeError("construction_service must be the exact trusted service")
        if (
            type(validation_service)
            is not PolygonCompletedDailyProductionValidationApplicationService
        ):
            raise TypeError("validation_service must be the exact trusted service")
        if (
            type(freshness_service)
            is not PolygonCompletedDailyProductionFreshnessApplicationService
        ):
            raise TypeError("freshness_service must be the exact trusted service")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        if (
            validation_service._construction_service is not construction_service
            or freshness_service._construction_service is not construction_service
        ):
            raise ValueError("prerequisite services must share construction history")
        self._construction_service = construction_service
        self._validation_service = validation_service
        self._freshness_service = freshness_service
        self._execution_clock = _utc_now if execution_clock is None else execution_clock
        self._history = _InMemoryPolygonCompletedDailyAdmissionHistory()

    def issue_admission(
        self, request: PolygonCompletedDailyAdmissionRequest
    ) -> PolygonCompletedDailyProductionAdmissionResult:
        """Issue one governed ADMITTED record from complete trusted histories."""

        if type(request) is not PolygonCompletedDailyAdmissionRequest:
            raise TypeError("request must be an exact admission request")
        request._validate()
        # One fixed lock order prevents prerequisite publication during issuance.
        # The independent admission history takes its own lock only after these.
        with ExitStack() as stack:
            for history in (
                self._construction_service._history,
                self._validation_service._history,
                self._freshness_service._history,
            ):
                stack.enter_context(history._lock)
            try:
                return self._issue_locked(request)
            except PolygonCompletedDailyAdmissionIssuanceRefused:
                raise
            except (TypeError, ValueError, RuntimeError, AttributeError) as error:
                raise PolygonCompletedDailyAdmissionIssuanceRefused(
                    PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                    "admission execution could not authenticate its context",
                ) from error

    def _issue_locked(
        self, request: PolygonCompletedDailyAdmissionRequest
    ) -> PolygonCompletedDailyProductionAdmissionResult:
        approved = _resolve_approved_polygon_completed_daily_production_profile(
            _PROFILE
        )
        if approved.admission_ruleset != _RULESET:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.POLICY_RULESET_MISMATCH,
                "admission ruleset is not the approved policy",
            )
        started = _timestamp(self._execution_clock())
        construction = self._resolve_construction(request, started)
        # Resolve before capturing issuance; then recheck the exact issuance cutoff.
        self._resolve_prerequisites(construction, started)
        completed = _timestamp(self._execution_clock())
        if completed < started:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                "admission completion precedes execution start",
            )
        prerequisites = self._resolve_prerequisites(construction, completed)
        try:
            existing = self.get_admission_history_as_of(
                request.artifact_reference, knowledge_as_of=completed
            )
            predecessor, _ = _resolve_effective_admission_results(
                existing,
                request.artifact_reference,
                completed,
                allow_empty=True,
            )

            def verify() -> _AdmissionPrerequisites:
                return self._resolve_prerequisites(construction, completed)

            return self._history._retain(
                execution_id=_issue_execution_id(),
                prerequisites=prerequisites,
                predecessor=predecessor,
                execution_started_at=started,
                execution_completed_at=completed,
                prerequisite_verifier=verify,
                availability_clock=self._execution_clock,
                seal=_HISTORY_SEAL,
            )
        except PolygonCompletedDailyAdmissionIssuanceRefused:
            raise
        except PolygonCompletedDailyAdmissionHistoryError as error:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "trusted admission history cannot publish the decision",
            ) from error
        except (TypeError, ValueError, RuntimeError) as error:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "trusted admission publication failed",
            ) from error

    def _resolve_construction(
        self, request: PolygonCompletedDailyAdmissionRequest, started: datetime
    ) -> PolygonCompletedDailyProductionConstructionResult:
        try:
            store = self._construction_service._history
            history = store._state[1]
            _validate_constructions(history, expected_namespace_id=store._namespace_id)
            _require_complete_sequence(store._state[0], history, "receipt")
        except (
            PolygonCompletedDailyConstructionHistoryError,
            TypeError,
            ValueError,
        ) as error:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "trusted construction history is incomplete or conflicting",
            ) from error
        matches = tuple(
            item
            for item in history
            if item.receipt.execution_id == request.construction_execution_id
            and item.receipt.available_at <= started
        )
        if not matches:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.TRUSTED_CONSTRUCTION_UNAVAILABLE,
                "exact trusted construction occurrence is unavailable",
            )
        if len(matches) != 1:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "construction occurrence identity is ambiguous",
            )
        result = matches[0]
        try:
            result._validate()
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.ARTIFACT_TARGET_MISMATCH,
                "trusted construction result does not bind the requested artifact",
            ) from error
        if result.artifact.reference() != request.artifact_reference:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.ARTIFACT_TARGET_MISMATCH,
                "requested artifact does not match the construction occurrence",
            )
        return result

    def _resolve_prerequisites(
        self,
        construction: PolygonCompletedDailyProductionConstructionResult,
        knowledge_as_of: datetime,
    ) -> _AdmissionPrerequisites:
        store = self._construction_service._history
        _validate_constructions(
            store._state[1], expected_namespace_id=store._namespace_id
        )
        _require_complete_sequence(store._state[0], store._state[1], "receipt")
        if not any(item is construction for item in store._state[1]):
            raise PolygonCompletedDailyAdmissionHistoryError(
                "construction occurrence is no longer retained"
            )
        return _resolve_admission_prerequisites(
            construction=construction,
            validation_service=self._validation_service,
            freshness_service=self._freshness_service,
            knowledge_as_of=knowledge_as_of,
        )

    def get_admission_history(
        self, artifact_reference: EvidenceArtifactReference
    ) -> tuple[PolygonCompletedDailyProductionAdmissionResult, ...]:
        """Return complete authentic admission issuance history for one version."""

        return self._history._history(artifact_reference, knowledge_as_of=None)

    def get_admission_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyProductionAdmissionResult, ...]:
        """Return admission history available by the inclusive knowledge cutoff."""

        return self._history._history(
            artifact_reference, knowledge_as_of=knowledge_as_of
        )


def _resolve_admission_prerequisites(
    *,
    construction: PolygonCompletedDailyProductionConstructionResult,
    validation_service: PolygonCompletedDailyProductionValidationApplicationService,
    freshness_service: PolygonCompletedDailyProductionFreshnessApplicationService,
    knowledge_as_of: datetime,
) -> _AdmissionPrerequisites:
    cutoff = _timestamp(knowledge_as_of)
    construction._validate()
    construction_id = construction.receipt.execution_id
    try:
        validation_store = validation_service._history
        validation_entries = validation_store._state[1]
        _validate_validation_entries(
            validation_entries, expected_namespace_id=validation_store._namespace_id
        )
        _require_complete_sequence(validation_store._state[0], validation_entries)
        freshness_store = freshness_service._history
        freshness_entries = freshness_store._state[1]
        _validate_freshness_entries(
            freshness_entries, expected_namespace_id=freshness_store._namespace_id
        )
        _require_complete_sequence(freshness_store._state[0], freshness_entries)
        validation_histories = tuple(
            tuple(
                item
                for item in validation_entries
                if item.companion.construction_execution_id == construction_id
                and item.validation_record.concern is requirement.concern
                and item.companion.available_at <= cutoff
            )
            for requirement in _RULESET.mandatory_validation_requirements
        )
        freshness_history = tuple(
            item
            for item in freshness_entries
            if item.companion.construction_execution_id == construction_id
            and item.companion.execution_kind
            is PolygonCompletedDailyFreshnessExecutionKind.ADMISSION
            and item.companion.available_at <= cutoff
        )
    except (
        PolygonCompletedDailyValidationHistoryError,
        PolygonCompletedDailyFreshnessHistoryError,
        TypeError,
        ValueError,
    ) as error:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
            "trusted prerequisite history is incomplete or conflicting",
        ) from error

    selected_validations: list[EvidenceValidationRecord] = []
    selected_validation_executions: list[
        PolygonCompletedDailyValidationExecutionReference
    ] = []
    for requirement, history in zip(
        _RULESET.mandatory_validation_requirements,
        validation_histories,
        strict=True,
    ):
        records_by_id: dict[str, EvidenceValidationRecord] = {}
        for result in history:
            _validate_validation_result(result, construction, requirement)
            record = result.validation_record
            retained = records_by_id.get(record.validation_record_id)
            if retained is not None and retained != record:
                raise PolygonCompletedDailyAdmissionIssuanceRefused(
                    PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                    "validation lifecycle identity resolves to conflicting content",
                )
            records_by_id[record.validation_record_id] = record
        eligible = tuple(
            item
            for item in records_by_id.values()
            if item.recorded_at <= cutoff and item.effective_at <= cutoff
        )
        winner, _, failure = _resolve_validation_concern(eligible, requirement.concern)
        if winner is None:
            reason = (
                PolygonCompletedDailyAdmissionRefusalReason.VALIDATION_UNAVAILABLE
                if not eligible
                else (
                    PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION
                )
            )
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                reason, failure or "required validation could not be resolved"
            )
        if (
            failure is not None
            or winner.disposition is not EvidenceValidationDisposition.PASSED
        ):
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                (
                    PolygonCompletedDailyAdmissionRefusalReason.VALIDATION_REJECTED
                    if winner.disposition is EvidenceValidationDisposition.REJECTED
                    else (
                        PolygonCompletedDailyAdmissionRefusalReason.VALIDATION_UNABLE_TO_VALIDATE
                        if winner.disposition
                        is EvidenceValidationDisposition.UNABLE_TO_VALIDATE
                        else (
                            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION
                        )
                    )
                ),
                "selected mandatory validation prerequisite did not pass",
            )
        occurrences = tuple(
            _validation_execution_reference(result)
            for result in history
            if result.validation_record == winner
        )
        if not occurrences:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "selected validation lacks authentic execution provenance",
            )
        selected_validations.append(winner)
        selected_validation_executions.extend(occurrences)

    freshness_by_fingerprint: dict[str, EvidenceFreshnessEvaluationRecord] = {}
    for freshness_result in freshness_history:
        _validate_freshness_result(freshness_result, construction)
        freshness_record = freshness_result.freshness_record
        retained_freshness = freshness_by_fingerprint.get(freshness_record.fingerprint)
        if retained_freshness is not None and retained_freshness != freshness_record:
            raise PolygonCompletedDailyAdmissionIssuanceRefused(
                PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "freshness lifecycle identity resolves to conflicting content",
            )
        if freshness_record.evaluation_as_of <= cutoff:
            freshness_by_fingerprint[freshness_record.fingerprint] = freshness_record
    freshness_records = tuple(freshness_by_fingerprint.values())
    if not freshness_records:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.FRESHNESS_UNAVAILABLE,
            "required admission freshness execution is missing",
        )
    precedence = max(record.evaluation_as_of for record in freshness_records)
    co_precedent = tuple(
        record for record in freshness_records if record.evaluation_as_of == precedence
    )
    if len(co_precedent) != 1:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
            "conflicting admission freshness records fail closed",
        )
    selected_freshness = co_precedent[0]
    if not selected_freshness.result:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.FRESHNESS_FAILED,
            "selected admission freshness prerequisite did not pass",
        )
    if _new_york_date(selected_freshness.evaluation_as_of) != _new_york_date(cutoff):
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.TEMPORAL_PREREQUISITE_FAILURE,
            "admission freshness is from a different New York civil date",
        )
    freshness_occurrences = tuple(
        _freshness_execution_reference(result)
        for result in freshness_history
        if result.freshness_record == selected_freshness
    )
    if not freshness_occurrences:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
            "selected freshness lacks authentic execution provenance",
        )
    context_fingerprint = _prerequisite_history_fingerprint(
        construction,
        validation_histories,
        freshness_history,
        cutoff,
    )
    return _AdmissionPrerequisites(
        construction_result=construction,
        validation_records=tuple(selected_validations),
        validation_execution_references=tuple(selected_validation_executions),
        freshness_record=selected_freshness,
        freshness_execution_references=freshness_occurrences,
        knowledge_as_of=cutoff,
        history_fingerprint=context_fingerprint,
        validation_histories=validation_histories,
        freshness_history=freshness_history,
    )


def _validate_validation_result(
    result: PolygonCompletedDailyProductionValidationResult,
    construction: PolygonCompletedDailyProductionConstructionResult,
    requirement: object,
) -> None:
    if type(result) is not PolygonCompletedDailyProductionValidationResult:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
            "trusted validation history returned an invalid result type",
        )
    try:
        result._validate()
        companion = result.companion
        expected = next(
            item
            for item in _RULESET.mandatory_validation_requirements
            if item.concern is result.validation_record.concern
        )
    except (TypeError, ValueError, StopIteration) as error:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
            "trusted validation result is corrupt",
        ) from error
    if (
        requirement != expected
        or companion.validation_requirement != expected
        or companion.production_profile_fingerprint != _PROFILE.fingerprint
        or companion.construction_execution_id != construction.receipt.execution_id
        or companion.construction_receipt_fingerprint
        != construction.receipt.fingerprint
        or result.validation_record.artifact_reference
        != construction.artifact.reference()
    ):
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.POLICY_RULESET_MISMATCH,
            "validation prerequisite does not match the exact production context",
        )


def _validate_freshness_result(
    result: PolygonCompletedDailyProductionFreshnessResult,
    construction: PolygonCompletedDailyProductionConstructionResult,
) -> None:
    if type(result) is not PolygonCompletedDailyProductionFreshnessResult:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
            "trusted freshness history returned an invalid result type",
        )
    try:
        result._validate()
    except (TypeError, ValueError) as error:
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
            "trusted freshness result is corrupt",
        ) from error
    companion = result.companion
    rule = _RULESET.admission_freshness_rule
    assert rule is not None
    if (
        result.freshness_record.artifact_reference != construction.artifact.reference()
        or result.freshness_record.freshness_rule != rule
        or companion.freshness_rule != rule
        or companion.production_profile_fingerprint != _PROFILE.fingerprint
        or companion.construction_execution_id != construction.receipt.execution_id
        or companion.construction_receipt_fingerprint
        != construction.receipt.fingerprint
    ):
        raise PolygonCompletedDailyAdmissionIssuanceRefused(
            PolygonCompletedDailyAdmissionRefusalReason.POLICY_RULESET_MISMATCH,
            "freshness prerequisite does not match the admission policy context",
        )


def _validation_execution_reference(
    result: PolygonCompletedDailyProductionValidationResult,
) -> PolygonCompletedDailyValidationExecutionReference:
    companion: PolygonCompletedDailyValidationExecutionCompanion = result.companion
    return PolygonCompletedDailyValidationExecutionReference(
        validation_record_reference=result.validation_record.reference(),
        execution_id=companion.execution_id,
        history_namespace_id=companion.history_namespace_id,
        history_sequence=companion.history_sequence,
        available_at=companion.available_at,
        companion_fingerprint=companion.fingerprint,
    )


def _freshness_execution_reference(
    result: PolygonCompletedDailyProductionFreshnessResult,
) -> PolygonCompletedDailyFreshnessExecutionReference:
    companion: PolygonCompletedDailyFreshnessExecutionCompanion = result.companion
    return PolygonCompletedDailyFreshnessExecutionReference(
        freshness_evaluation_reference=result.freshness_record.reference(),
        execution_id=companion.execution_id,
        history_namespace_id=companion.history_namespace_id,
        history_sequence=companion.history_sequence,
        available_at=companion.available_at,
        companion_fingerprint=companion.fingerprint,
    )


def _prerequisite_history_fingerprint(
    construction: PolygonCompletedDailyProductionConstructionResult,
    validation_histories: tuple[
        tuple[PolygonCompletedDailyProductionValidationResult, ...], ...
    ],
    freshness_history: tuple[PolygonCompletedDailyProductionFreshnessResult, ...],
    knowledge_as_of: datetime,
) -> str:
    return canonical_fingerprint(
        {
            "schema_version": _PREREQUISITE_CONTEXT_SCHEMA,
            "artifact_reference": construction.artifact.reference().to_dict(),
            "construction_receipt_fingerprint": construction.receipt.fingerprint,
            "knowledge_as_of": knowledge_as_of.isoformat(),
            "validation_histories": [
                [
                    {
                        "record_reference": (
                            item.validation_record.reference().to_dict()
                        ),
                        "execution_reference": _validation_execution_reference(
                            item
                        ).to_dict(),
                    }
                    for item in history
                ]
                for history in validation_histories
            ],
            "admission_freshness_history": [
                {
                    "record_reference": item.freshness_record.reference().to_dict(),
                    "execution_reference": _freshness_execution_reference(
                        item
                    ).to_dict(),
                }
                for item in freshness_history
            ],
        }
    )


def _create_admission_record(
    prerequisites: _AdmissionPrerequisites,
    *,
    predecessor: EvidenceAdmissionRecord | None,
    issued_at: datetime,
) -> EvidenceAdmissionRecord:
    artifact_reference = prerequisites.construction_result.artifact.reference()
    selected = tuple(record.reference() for record in prerequisites.validation_records)
    record_identity = canonical_fingerprint(
        {
            "schema_version": _RECORD_ID_SCHEMA,
            "artifact_reference": artifact_reference.to_dict(),
            "admission_ruleset_reference": _RULESET.reference().to_dict(),
            "selected_validation_record_references": [
                item.to_dict() for item in selected
            ],
            "admission_freshness_evaluation_reference": (
                prerequisites.freshness_record.reference().to_dict()
            ),
            "predecessor": None
            if predecessor is None
            else predecessor.reference().to_dict(),
            "recorded_at": issued_at.isoformat(),
            "effective_at": issued_at.isoformat(),
        }
    ).removeprefix("sha256:")
    return create_evidence_admission_record(
        admission_record_id=f"admission.polygon_completed_daily:{record_identity}",
        artifact_reference=artifact_reference,
        admission_ruleset=_RULESET,
        selected_validation_record_references=selected,
        admission_freshness_evaluation_reference=(
            prerequisites.freshness_record.reference()
        ),
        deciding_actor_identity=_ACTOR,
        deciding_capability_identity=_CAPABILITY,
        disposition=EvidenceAdmissionDisposition.ADMITTED,
        recorded_at=issued_at,
        effective_at=issued_at,
        findings=("All exact trusted production admission prerequisites passed.",),
        predecessor=predecessor,
    )


def _resolve_effective_admission_results(
    entries: tuple[PolygonCompletedDailyProductionAdmissionResult, ...],
    artifact_reference: EvidenceArtifactReference,
    cutoff: datetime,
    *,
    allow_empty: bool,
) -> tuple[
    EvidenceAdmissionRecord | None,
    tuple[PolygonCompletedDailyProductionAdmissionResult, ...],
]:
    if not entries:
        if allow_empty:
            return None, ()
        raise PolygonCompletedDailyAdmissionHistoryConflictError(
            "admission history unexpectedly has no lifecycle record"
        )
    records_by_id: dict[str, EvidenceAdmissionRecord] = {}
    for item in entries:
        item._validate()
        record = item.admission_record
        retained = records_by_id.get(record.admission_record_id)
        if retained is not None and retained != record:
            raise PolygonCompletedDailyAdmissionHistoryConflictError(
                "admission lifecycle identity resolves to conflicting content"
            )
        records_by_id[record.admission_record_id] = record
    selected, _, failure = _resolve_admission(
        artifact_reference,
        _SCOPE,
        tuple(records_by_id.values()),
        cutoff,
        cutoff,
    )
    if failure is not None or selected is None:
        raise PolygonCompletedDailyAdmissionHistoryConflictError(
            "admission lifecycle history cannot be resolved canonically"
        )
    occurrences = tuple(item for item in entries if item.admission_record == selected)
    if not occurrences:
        raise PolygonCompletedDailyAdmissionHistoryConflictError(
            "selected admission lacks execution provenance"
        )
    return selected, occurrences


def _relevant_admission_entries(
    entries: tuple[PolygonCompletedDailyProductionAdmissionResult, ...],
    reference: EvidenceArtifactReference,
    cutoff: datetime | None,
) -> tuple[PolygonCompletedDailyProductionAdmissionResult, ...]:
    return tuple(
        sorted(
            (
                item
                for item in entries
                if item.companion.artifact_reference.artifact_id
                == reference.artifact_id
                and item.companion.artifact_reference.artifact_version
                == reference.artifact_version
                and (cutoff is None or item.companion.available_at <= cutoff)
            ),
            key=lambda item: item.companion.history_sequence,
        )
    )


def _validate_retained_entries(
    entries: tuple[PolygonCompletedDailyProductionAdmissionResult, ...],
    expected_namespace_id: str,
) -> None:
    if type(entries) is not tuple:
        raise TypeError("admission history must be an exact tuple")
    namespace_id = _history_namespace_id(expected_namespace_id)
    execution_ids: set[str] = set()
    sequences: set[int] = set()
    records: dict[str, EvidenceAdmissionRecord] = {}
    prior_sequence = 0
    prior_availability: datetime | None = None
    for item in entries:
        if type(item) is not PolygonCompletedDailyProductionAdmissionResult:
            raise TypeError("admission history contains an invalid result type")
        item._validate()
        companion = item.companion
        if companion.history_namespace_id != namespace_id:
            raise ValueError("admission history namespace does not correspond")
        if companion.execution_id in execution_ids:
            raise ValueError("admission history duplicates an execution identity")
        if companion.history_sequence in sequences:
            raise ValueError("admission history duplicates a sequence")
        if companion.history_sequence <= prior_sequence:
            raise ValueError("admission history sequence is not increasing")
        if (
            prior_availability is not None
            and companion.available_at < prior_availability
        ):
            raise ValueError("admission history availability moves backward")
        record = item.admission_record
        retained = records.get(record.admission_record_id)
        if retained is not None and retained != record:
            raise ValueError(
                "admission record identity resolves to conflicting content"
            )
        records[record.admission_record_id] = record
        execution_ids.add(companion.execution_id)
        sequences.add(companion.history_sequence)
        prior_sequence = companion.history_sequence
        prior_availability = companion.available_at


def _visible_ascii(value: object, field_name: str, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or not value.isascii()
        or not value.isprintable()
    ):
        raise ValueError(f"{field_name} must be visible ASCII")
    return value


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


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _execution_id(value: object) -> str:
    if type(value) is not str or _EXECUTION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("execution_id is not canonical")
    return value


def _construction_execution_id(value: object) -> str:
    if (
        type(value) is not str
        or _CONSTRUCTION_EXECUTION_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("construction_execution_id is not canonical")
    return value


def _history_namespace_id(value: object) -> str:
    if type(value) is not str or _HISTORY_NAMESPACE_PATTERN.fullmatch(value) is None:
        raise ValueError("history_namespace_id is not canonical")
    return value


def _timestamp(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _require_canonical_timestamp(value: object, field_name: str) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not UTC
        or value.utcoffset() is None
    ):
        raise ValueError(f"{field_name} must be a canonical UTC datetime")
    return value


def _new_york_date(value: datetime) -> date:
    return value.astimezone(_MARKET_TIMEZONE).date()


def _issue_execution_id() -> str:
    return f"polygon_completed_daily_admission:{uuid4().hex}"


def _issue_history_namespace_id() -> str:
    return f"polygon_completed_daily_admission_history:{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_complete_sequence(
    next_sequence: int, entries: tuple[object, ...], attribute: str = "companion"
) -> None:
    if type(entries) is not tuple:
        raise ValueError("history must retain an exact tuple")
    if any(not hasattr(item, attribute) for item in entries):
        raise ValueError("history contains an invalid occurrence")
    if type(next_sequence) is not int or next_sequence != len(entries) + 1:
        raise ValueError("history sequence count is incomplete")
    if tuple(getattr(item, attribute).history_sequence for item in entries) != tuple(
        range(1, next_sequence)
    ):
        raise ValueError("history contains a missing occurrence")


__all__ = [
    "PolygonCompletedDailyAdmissionExecutionCompanion",
    "PolygonCompletedDailyAdmissionExecutionReference",
    "PolygonCompletedDailyAdmissionHistoryConflictError",
    "PolygonCompletedDailyAdmissionHistoryError",
    "PolygonCompletedDailyAdmissionIssuanceRefused",
    "PolygonCompletedDailyAdmissionRefusalReason",
    "PolygonCompletedDailyAdmissionRequest",
    "PolygonCompletedDailyFreshnessExecutionReference",
    "PolygonCompletedDailyProductionAdmissionApplicationService",
    "PolygonCompletedDailyProductionAdmissionResult",
    "PolygonCompletedDailyValidationExecutionReference",
]
